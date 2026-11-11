"""Planeador de rutas: la página y la API que arma el itinerario."""
from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.destinos.models import Destino
from apps.metricas.models import registrar
from .escapada import crear_escapada, despues_de_guardar, url_del_editor
from .exportar import con_enlaces
from .servicio import (
    MODOS, RITMOS, RADIO_KM, alternativas, intereses_disponibles, municipios_de_salida, planear, regresa,
    resolver_destino,
)

HORA = r'^([01][0-9]|2[0-3]):[0-5][0-9]$'
HORAS_MINIMAS = 3
# Un año hacia adelante basta para planear; más lejos, los horarios ya no dirían nada.
DIAS_HACIA_ADELANTE = 365


class PlaneadorAnonimoThrottle(AnonRateThrottle):
    # Cada plan tarda uno o dos segundos de cálculo.
    rate = '10/min'
    scope = 'planeador_anonimo'


class PlaneadorThrottle(UserRateThrottle):
    rate = '20/min'
    scope = 'planeador'


class AlternativasAnonimoThrottle(AnonRateThrottle):
    # Más ligero que un plan, pero recorre todos los destinos.
    rate = '20/min'
    scope = 'alternativas_anonimo'


class AlternativasThrottle(UserRateThrottle):
    rate = '40/min'
    scope = 'alternativas'


def _minutos(hora):
    horas, minutos = hora.split(':')
    return int(horas) * 60 + int(minutos)


# Ruta editada. Los días cuentan desde 0, como la lista `dias` del plan.
MAXIMO_FIJADOS = 30
MAXIMO_EXCLUIDOS = 100
MAXIMO_DESCANSOS = 6
DESCANSO_MINUTOS = (15, 240)


class FijadoSerializer(serializers.Serializer):
    destino = serializers.IntegerField(min_value=1)
    dia = serializers.IntegerField(min_value=0, max_value=max(RADIO_KM) - 1)
    # Hora a la que estaba en el plan anterior: solo orienta el acomodo; puede moverse.
    hora = serializers.RegexField(HORA, required=False)


class DescansoSerializer(serializers.Serializer):
    dia = serializers.IntegerField(min_value=0, max_value=max(RADIO_KM) - 1)
    inicio = serializers.RegexField(HORA)
    duracion = serializers.IntegerField(min_value=DESCANSO_MINUTOS[0], max_value=DESCANSO_MINUTOS[1])


class PeticionRutaSerializer(serializers.Serializer):
    # Desde un municipio o desde un punto; el punto se usa para calcular y no se guarda.
    municipio = serializers.SlugField(required=False)
    latitud = serializers.FloatField(required=False, min_value=14, max_value=33)
    longitud = serializers.FloatField(required=False, min_value=-118, max_value=-86)
    fecha = serializers.DateField()
    dias = serializers.ChoiceField(choices=sorted(RADIO_KM))
    hora_inicio = serializers.RegexField(HORA)
    hora_fin = serializers.RegexField(HORA)
    intereses = serializers.ListField(child=serializers.SlugField(), min_length=1, max_length=10)
    ritmo = serializers.ChoiceField(choices=list(RITMOS), default='normal')
    personas = serializers.IntegerField(min_value=1, max_value=20, default=1)
    # Solo para entradas: es lo único cuyo precio conocemos.
    presupuesto = serializers.DecimalField(max_digits=9, decimal_places=2, min_value=0, required=False,
                                           allow_null=True)
    regresar = serializers.BooleanField(default=True)
    # A dónde va (opcional): 'destino:<slug>' o 'municipio:<slug>', como los propone el buscador.
    destino = serializers.RegexField(r'^(destino|municipio):[-a-z0-9]{1,200}$', required=False, allow_blank=True,
                                     error_messages={'invalid': 'Elige el destino de la lista de sugerencias.'})
    # Sin destino es 'circulo'; con destino y sin modo, ida y vuelta.
    modo = serializers.ChoiceField(choices=list(MODOS), required=False)
    # Ruta editada: paradas fijadas en un día, sitios que no deben entrar y ratos de tiempo libre.
    fijados = serializers.ListField(child=FijadoSerializer(), max_length=MAXIMO_FIJADOS, default=list)
    excluidos = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=MAXIMO_EXCLUIDOS,
                                      default=list)
    descansos = serializers.ListField(child=DescansoSerializer(), max_length=MAXIMO_DESCANSOS, default=list)

    def validate_fecha(self, fecha):
        hoy = timezone.localdate()
        if not hoy - timedelta(days=1) <= fecha <= hoy + timedelta(days=DIAS_HACIA_ADELANTE):
            raise serializers.ValidationError('Elige una fecha entre hoy y dentro de un año.')
        return fecha

    def validate_intereses(self, intereses):
        validos = set(intereses_disponibles().values_list('slug', flat=True))
        if not set(intereses) <= validos:
            raise serializers.ValidationError('Uno de los intereses no existe.')
        return intereses

    def validate(self, datos):
        if 'municipio' in datos:
            municipio = municipios_de_salida().filter(slug=datos['municipio']).first()
            if not municipio:
                raise serializers.ValidationError({'municipio': 'Ese municipio no tiene destinos.'})
            datos['origen'], datos['origen_nombre'] = (float(municipio.lat), float(municipio.lng)), municipio.nombre
        elif 'latitud' in datos and 'longitud' in datos:
            datos['origen'], datos['origen_nombre'] = (datos['latitud'], datos['longitud']), 'Tu ubicación'
        else:
            raise serializers.ValidationError({'municipio': 'Elige desde dónde sales.'})
        if _minutos(datos['hora_fin']) - _minutos(datos['hora_inicio']) < HORAS_MINIMAS * 60:
            raise serializers.ValidationError({'hora_fin': f'Deja al menos {HORAS_MINIMAS} horas para recorrer.'})
        self._validar_destino(datos)
        self._validar_edicion(datos)
        return datos

    @staticmethod
    def _validar_edicion(datos):
        """Deja `fijados_por_clave` ({pk: {'dia', 'hora'}}) y los descansos en minutos, dentro del viaje."""
        dias, inicio, fin = datos['dias'], _minutos(datos['hora_inicio']), _minutos(datos['hora_fin'])
        fijados = {}
        for fijado in datos['fijados']:
            if fijado['dia'] >= dias:
                raise serializers.ValidationError({'fijados': 'Una parada fijada queda fuera de los días del viaje.'})
            if fijado['destino'] in fijados:
                raise serializers.ValidationError({'fijados': 'Fijaste dos veces la misma parada.'})
            hora = _minutos(fijado['hora']) if fijado.get('hora') else None
            fijados[fijado['destino']] = {'dia': fijado['dia'], 'hora': hora}
        if set(fijados) & set(datos['excluidos']):
            raise serializers.ValidationError({'excluidos': 'Una parada no puede estar fijada y quitada a la vez.'})
        activos = set(Destino.objects.filter(pk__in=fijados, es_activo=True).values_list('pk', flat=True))
        if set(fijados) - activos:
            raise serializers.ValidationError({'fijados': 'Uno de los sitios fijados ya no está disponible.'})
        descansos = []
        for descanso in datos['descansos']:
            minuto = _minutos(descanso['inicio'])
            if descanso['dia'] >= dias or not inicio <= minuto < fin:
                raise serializers.ValidationError({'descansos': 'Un descanso queda fuera de tu horario.'})
            descansos.append({'dia': descanso['dia'], 'inicio': minuto, 'duracion': descanso['duracion']})
        datos['fijados_por_clave'] = fijados
        datos['descansos_en_minutos'] = descansos

    @staticmethod
    def _validar_destino(datos):
        """Resuelve el destino y deja `regresar` como lo pide el tipo de viaje."""
        if not datos.get('destino'):
            datos.pop('destino', None)
            if datos.setdefault('modo', 'circulo') != 'circulo':
                raise serializers.ValidationError({'destino': 'Elige a dónde vas o marca «Sin destino».'})
            datos['destino_info'] = None
            return
        if datos.setdefault('modo', 'ida_vuelta') == 'circulo':
            raise serializers.ValidationError({'modo': 'Elige el tipo de viaje: ida y vuelta, solo ida o quedarte.'})
        info = resolver_destino(datos['destino'])
        if info is None:
            raise serializers.ValidationError({'destino': 'No encontramos ese destino. Elígelo de la lista.'})
        if datos['modo'] == 'base' and datos['dias'] < 2:
            raise serializers.ValidationError({'modo': 'Para quedarte en el destino elige al menos 2 días.'})
        datos['destino_info'] = info
        datos['regresar'] = regresa(datos['modo'], datos['regresar'])


class PlanearRutaView(APIView):
    """POST: arma un itinerario de 1 a 3 días con los intereses, el horario y el presupuesto dados."""
    permission_classes = [AllowAny]
    throttle_classes = [PlaneadorAnonimoThrottle, PlaneadorThrottle]

    @extend_schema(request=PeticionRutaSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        peticion = PeticionRutaSerializer(data=request.data)
        peticion.is_valid(raise_exception=True)
        datos = peticion.validated_data
        plan = con_enlaces(armar_plan(datos), datos['regresar'], origen_publico='municipio' in datos)
        registrar('ruta_planeada', usuario=request.user if request.user.is_authenticated else None)
        return Response(plan)


class PuntoSerializer(serializers.Serializer):
    latitud = serializers.FloatField(min_value=14, max_value=33)
    longitud = serializers.FloatField(min_value=-118, max_value=-86)


class PeticionAlternativasSerializer(serializers.Serializer):
    """Un hueco del itinerario: de dónde y a qué hora se sale, y a dónde y a qué hora hay que llegar."""
    fecha = serializers.DateField()
    desde = serializers.RegexField(HORA)
    hasta = serializers.RegexField(HORA)
    # Se usan una vez para calcular y no se guardan (el anterior puede ser la ubicación de la persona).
    anterior = PuntoSerializer()
    siguiente = PuntoSerializer(required=False, allow_null=True)
    intereses = serializers.ListField(child=serializers.SlugField(), min_length=1, max_length=10)
    ritmo = serializers.ChoiceField(choices=list(RITMOS), default='normal')
    # Lo que ya está en la ruta y lo que la persona quitó: no se vuelve a proponer.
    excluidos = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=MAXIMO_EXCLUIDOS,
                                      default=list)

    def validate(self, datos):
        if _minutos(datos['hasta']) <= _minutos(datos['desde']):
            raise serializers.ValidationError({'hasta': 'El hueco termina antes de empezar.'})
        return datos


class AlternativasView(APIView):
    """POST: tres sitios que caben en el hueco de una parada, del mejor al peor."""
    permission_classes = [AllowAny]
    throttle_classes = [AlternativasAnonimoThrottle, AlternativasThrottle]

    @extend_schema(request=PeticionAlternativasSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        peticion = PeticionAlternativasSerializer(data=request.data)
        peticion.is_valid(raise_exception=True)
        datos = peticion.validated_data

        def punto(valor):
            return (valor['latitud'], valor['longitud']) if valor else None

        opciones = alternativas(punto(datos['anterior']), punto(datos.get('siguiente')), datos['fecha'],
                                _minutos(datos['desde']), _minutos(datos['hasta']), datos['intereses'],
                                datos['ritmo'], datos['excluidos'])
        return Response({'alternativas': opciones})


def armar_plan(datos):
    """El plan para una petición ya validada, con su punto de salida."""
    plan = planear(
        datos['origen'], datos['fecha'], datos['dias'], _minutos(datos['hora_inicio']),
        _minutos(datos['hora_fin']), datos['intereses'], datos['ritmo'], datos['personas'],
        datos.get('presupuesto'), datos['regresar'], datos['modo'], datos['destino_info'], datos['origen_nombre'],
        datos.get('fijados_por_clave'), datos.get('excluidos', ()), datos.get('descansos_en_minutos', ()),
    )
    plan['origen'] = {'nombre': datos['origen_nombre'], 'latitud': datos['origen'][0],
                      'longitud': datos['origen'][1]}
    return plan


def pagina_planeador(request):
    hoy = timezone.localdate()
    manana = hoy + timedelta(days=1)
    return render(request, 'rutas/planeador.html', {
        'municipios': municipios_de_salida(),
        'intereses': intereses_disponibles().order_by('nombre'),
        'hoy': hoy,
        'manana': manana,
        # Atajo para la escapada de fin de semana: el próximo sábado desde mañana.
        'sabado': manana + timedelta(days=(5 - manana.weekday()) % 7),
        'limite': hoy + timedelta(days=DIAS_HACIA_ADELANTE),
        'dias_opciones': sorted(RADIO_KM),
        'modos': [(clave, nombre) for clave, nombre in MODOS.items() if clave != 'circulo'],
        'seo': {'titulo': 'Armar una ruta por Jalisco — InfoTrip',
                'descripcion': 'Dinos cuántos días tienes y qué te gusta: armamos un itinerario por Jalisco que '
                               'respeta horarios, distancias y tu presupuesto.'},
    })


class GuardarEscapadaSerializer(PeticionRutaSerializer):
    # Qué opción de comida eligió la persona en cada parada (ids de Lugar); solo cuentan las que el plan ofrece.
    comidas = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=20, default=list)


class GuardarEscapadaView(APIView):
    """POST (con sesión): vuelve a calcular la ruta y la guarda como escapada en Mis viajes."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [PlaneadorThrottle]

    @extend_schema(request=GuardarEscapadaSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        peticion = GuardarEscapadaSerializer(data=request.data)
        peticion.is_valid(raise_exception=True)
        datos = peticion.validated_data
        viaje = crear_escapada(request.user, armar_plan(datos), datos, datos['comidas'])
        despues_de_guardar(viaje, request, datos)
        registrar('viaje_guardado', usuario=request.user)
        return Response({'id': viaje.pk, 'nombre': viaje.nombre, 'url': url_del_editor(viaje)}, status=201)
