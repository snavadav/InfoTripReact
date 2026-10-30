"""Recepción de eventos del navegador y panel de métricas para el personal."""
from datetime import timedelta

from django.contrib import admin
from django.db.models import Count, DurationField, ExpressionWrapper, F, Q
from django.shortcuts import render
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.comunidad.models import Reporte, ReporteColaboracion
from apps.destinos.models import Destino
from apps.usuarios.models import Usuario
from .models import Evento


class EventosThrottle(AnonRateThrottle):
    rate = '60/min'
    scope = 'eventos'


class EventoSerializer(serializers.Serializer):
    nombre = serializers.ChoiceField(choices=Evento.DEL_NAVEGADOR)
    destino = serializers.SlugField(max_length=220, required=False, allow_blank=True)


class EventosView(APIView):
    """POST: registra un evento anónimo del navegador. Sin sesión, sin IP y sin cookies."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [EventosThrottle]

    @extend_schema(request=EventoSerializer, responses={204: None})
    def post(self, request):
        datos = EventoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        Evento.objects.create(**datos.validated_data)
        return Response(status=204)


# Embudos: cada fila compara una etapa con la siguiente.
EMBUDOS = [
    ('Activación', ['ficha_vista', 'dato_practico_visto', 'registro_iniciado', 'registro_completado',
                    'login_completado', 'viaje_guardado']),
    ('Contribución', ['login_completado', 'aporte_enviado', 'aporte_publicado']),
    ('Referencia', ['enlace_compartido', 'visita_por_enlace']),
]


def conteos(desde):
    filas = Evento.objects.filter(creado__gte=desde).values('nombre').annotate(total=Count('pk'))
    return {fila['nombre']: fila['total'] for fila in filas}


def embudos(totales):
    resultado = []
    for titulo, etapas in EMBUDOS:
        filas = []
        anterior = None
        for etapa in etapas:
            total = totales.get(etapa, 0)
            filas.append({'etapa': etapa, 'total': total,
                          'conversion': round(100 * total / anterior) if anterior else None})
            anterior = total
        resultado.append({'titulo': titulo, 'filas': filas})
    return resultado


def retencion_30_dias(ahora):
    """De quienes se registraron hace 30 a 60 días, cuántos hicieron algo en los últimos 30."""
    cohorte = Usuario.objects.filter(fecha_registro__lt=ahora - timedelta(days=30),
                                     fecha_registro__gte=ahora - timedelta(days=60), es_activo=True)
    total = cohorte.count()
    activos = cohorte.filter(pk__in=Evento.objects.filter(creado__gte=ahora - timedelta(days=30),
                                                          usuario__isnull=False).values('usuario')).count()
    return {'cohorte': total, 'activos': activos, 'porcentaje': round(100 * activos / total) if total else None}


def fichas_utiles():
    """Destinos activos con al menos 3 datos prácticos distintos publicados: mide si hay qué consultar."""
    publicados = Q(colaboraciones__tipo='correccion', colaboraciones__estado='publicado')
    destinos = Destino.objects.filter(es_activo=True).annotate(
        datos=Count('colaboraciones__campo', filter=publicados, distinct=True))
    total = destinos.count()
    utiles = destinos.filter(datos__gte=3).count()
    return {'total': total, 'utiles': utiles, 'porcentaje': round(100 * utiles / total) if total else None}


def horas_para_resolver_reportes(desde):
    """Tiempo medio entre un reporte y su resolución; None si aún no se ha resuelto ninguno."""
    duraciones = []
    for modelo in (Reporte, ReporteColaboracion):
        duraciones += [fila['duracion'] for fila in modelo.objects.filter(resuelto_en__gte=desde).annotate(
            duracion=ExpressionWrapper(F('resuelto_en') - F('creado'), output_field=DurationField())
        ).values('duracion')]
    if not duraciones:
        return None
    return round(sum(duracion.total_seconds() for duracion in duraciones) / len(duraciones) / 3600, 1)


def panel(request):
    ahora = timezone.now()
    ultimos_30 = conteos(ahora - timedelta(days=30))
    ultimos_7 = conteos(ahora - timedelta(days=7))
    nombres = Evento.DEL_NAVEGADOR + Evento.DEL_SERVIDOR
    contexto = {
        **admin.site.each_context(request), 'title': 'Métricas de uso',
        'eventos': [{'nombre': nombre, 'dias_7': ultimos_7.get(nombre, 0), 'dias_30': ultimos_30.get(nombre, 0)}
                    for nombre in nombres],
        'embudos': embudos(ultimos_30), 'retencion': retencion_30_dias(ahora), 'fichas': fichas_utiles(),
        'horas_para_resolver': horas_para_resolver_reportes(ahora - timedelta(days=30)),
    }
    return render(request, 'admin/metricas.html', contexto)
