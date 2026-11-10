"""Guardar una ruta del planeador y compartirla por enlace, en Google Maps o en el calendario."""
import copy
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.metricas.models import registrar
from .exportar import calendario_ics, con_enlaces, duracion
from .models import RutaCompartida
from .optimizador import distancia_km
from .servicio import municipios_de_salida
from .views import PeticionRutaSerializer, armar_plan

PARAMETROS_GUARDADOS = ('municipio', 'fecha', 'dias', 'hora_inicio', 'hora_fin', 'intereses', 'ritmo', 'personas',
                        'presupuesto', 'regresar', 'destino', 'modo')


class CompartirAnonimoThrottle(AnonRateThrottle):
    # Cada ruta compartida vuelve a calcularse y ocupa espacio: sin cuenta, pocas por hora.
    rate = '10/hour'
    scope = 'rutas_compartidas_anonimo'


class CompartirThrottle(UserRateThrottle):
    rate = '30/hour'
    scope = 'rutas_compartidas'


# ── Privacidad: lo que se guarda ──────────────────────────────
def municipio_cercano(punto):
    """El municipio de salida más cercano a un punto, o None si no hay ninguno."""
    cercanos = sorted(municipios_de_salida(), key=lambda m: distancia_km(punto, (float(m.lat), float(m.lng))))
    return cercanos[0].nombre if cercanos else None


def para_guardar(plan, datos):
    """(parámetros, plan) sin coordenadas de quien la armó: si salió de su ubicación, solo el municipio cercano."""
    parametros = {clave: datos[clave] for clave in PARAMETROS_GUARDADOS if datos.get(clave) is not None}
    parametros['fecha'] = datos['fecha'].isoformat()
    if parametros.get('presupuesto') is not None:
        parametros['presupuesto'] = str(parametros['presupuesto'])
    guardado = copy.deepcopy(plan)
    if 'municipio' in datos:
        parametros['desde'] = 'municipio'
        return parametros, guardado
    cercano = municipio_cercano(datos['origen'])
    parametros['desde'] = 'ubicacion'
    guardado['origen'] = {'nombre': f'Cerca de {cercano}' if cercano else 'Tu ubicación'}
    return parametros, guardado


def titulo_de(plan):
    dias = len(plan['dias'])
    titulo = f'Ruta de {dias} {"día" if dias == 1 else "días"} desde {plan["origen"]["nombre"]}'
    destino = (plan.get('viaje') or {}).get('destino')
    if destino:
        titulo += f' a {destino["nombre"]}'
    return titulo[:160]


# ── API ───────────────────────────────────────────────────────
def resumen_ruta(ruta):
    return {'enlace': str(ruta.enlace), 'url': ruta.get_absolute_url(), 'titulo': ruta.titulo,
            'creada': ruta.creada, 'caduca': ruta.caduca,
            'sitios': ruta.plan['totales']['sitios'], 'fecha': ruta.parametros['fecha']}


class RutasCompartidasView(APIView):
    """POST: guarda la ruta que da esa petición y devuelve su enlace público. GET: las rutas de quien inició sesión."""
    permission_classes = [AllowAny]

    def get_throttles(self):
        if self.request.method == 'POST':
            return [CompartirAnonimoThrottle(), CompartirThrottle()]
        return super().get_throttles()

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Inicia sesión para ver tus rutas.'}, status=status.HTTP_401_UNAUTHORIZED)
        rutas = RutaCompartida.objects.filter(autor=request.user)
        return Response({'rutas': [resumen_ruta(r) for r in rutas]})

    @extend_schema(request=PeticionRutaSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        # La ruta se vuelve a calcular aquí: nadie puede publicar con nuestro nombre un plan inventado.
        peticion = PeticionRutaSerializer(data=request.data)
        peticion.is_valid(raise_exception=True)
        datos = peticion.validated_data
        parametros, plan = para_guardar(armar_plan(datos), datos)
        autor = request.user if request.user.is_authenticated else None
        with transaction.atomic():
            RutaCompartida.objects.caducadas().delete()
            ruta = RutaCompartida.objects.create(autor=autor, titulo=titulo_de(plan),
                                                 origen_nombre=plan['origen']['nombre'], parametros=parametros,
                                                 plan=plan)
        registrar('ruta_compartida', usuario=autor)
        return Response(resumen_ruta(ruta), status=status.HTTP_201_CREATED)


class RutaCompartidaView(APIView):
    """DELETE: quien la guardó con su cuenta la borra y el enlace deja de funcionar."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, enlace):
        ruta = get_object_or_404(RutaCompartida, enlace=enlace, autor=request.user)
        ruta.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Páginas públicas ──────────────────────────────────────────
def _ruta_vigente(request, enlace):
    ruta = get_object_or_404(RutaCompartida, enlace=enlace)
    if ruta.caducada:
        return ruta, render(request, 'rutas/ruta_caducada.html', status=410)
    return ruta, None


def _fecha_legible(iso):
    return datetime.strptime(iso, '%Y-%m-%d').date()


def precio_texto(precio):
    if precio is None:
        return 'Precio de entrada desconocido'
    return f'Entrada: ${Decimal(precio):,.0f} por persona' if Decimal(precio) else 'Entrada libre'


def pagina_ruta_compartida(request, enlace):
    ruta, caducada = _ruta_vigente(request, enlace)
    if caducada:
        return caducada
    plan = con_enlaces(copy.deepcopy(ruta.plan), ruta.parametros.get('regresar', True))
    viaje = plan.get('viaje') or {}
    for numero, dia in enumerate(plan['dias']):
        dia['numero'] = numero + 1
        dia['color'] = numero % 3
        dia['fecha_obj'] = _fecha_legible(dia['fecha'])
        for parada in dia['paradas']:
            parada['visita_texto'] = duracion(parada['visita_min'])
            parada['manejo_texto'] = duracion(parada['manejo_min']) if parada['manejo_min'] else ''
            parada['precio_texto'] = precio_texto(parada['precio'])
    nombres = [p['destino']['nombre'] for d in plan['dias'] for p in d['paradas']]
    descripcion = (f'{len(nombres)} sitios: {", ".join(nombres[:4])}{"…" if len(nombres) > 4 else ""}. '
                   'Armada con el planeador de InfoTrip.') if nombres else 'Una ruta por Jalisco armada con InfoTrip.'
    return render(request, 'rutas/ruta_compartida.html', {
        'ruta': ruta, 'plan': plan,
        'mapa': {'origen': plan['origen'], 'regresar': ruta.parametros.get('regresar', True),
                 'modo': viaje.get('modo', 'circulo'), 'destino': viaje.get('destino'),
                 'dias': [[{'nombre': p['destino']['nombre'], 'url': p['destino']['url'],
                            'latitud': p['destino']['latitud'], 'longitud': p['destino']['longitud']}
                           for p in d['paradas']] for d in plan['dias']]},
        'seo': {'titulo': f'{ruta.titulo} — InfoTrip', 'descripcion': descripcion},
    })


def calendario_ruta(request, enlace):
    ruta, caducada = _ruta_vigente(request, enlace)
    if caducada:
        raise Http404
    contenido = calendario_ics(ruta, settings.PUBLIC_BASE_URL + ruta.get_absolute_url())
    respuesta = HttpResponse(contenido, content_type='text/calendar; charset=utf-8')
    respuesta['Content-Disposition'] = f'attachment; filename="ruta-infotrip-{str(ruta.enlace)[:8]}.ics"'
    return respuesta
