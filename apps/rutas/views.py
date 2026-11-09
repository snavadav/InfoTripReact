"""Planeador de rutas: la página y la API que arma el itinerario."""
from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.metricas.models import registrar
from .servicio import RITMOS, RADIO_KM, intereses_disponibles, municipios_de_salida, planear

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


def _minutos(hora):
    horas, minutos = hora.split(':')
    return int(horas) * 60 + int(minutos)


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
        return datos


class PlanearRutaView(APIView):
    """POST: arma un itinerario de 1 a 3 días con los intereses, el horario y el presupuesto dados."""
    permission_classes = [AllowAny]
    throttle_classes = [PlaneadorAnonimoThrottle, PlaneadorThrottle]

    @extend_schema(request=PeticionRutaSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        peticion = PeticionRutaSerializer(data=request.data)
        peticion.is_valid(raise_exception=True)
        datos = peticion.validated_data
        plan = planear(
            datos['origen'], datos['fecha'], datos['dias'], _minutos(datos['hora_inicio']),
            _minutos(datos['hora_fin']), datos['intereses'], datos['ritmo'], datos['personas'],
            datos.get('presupuesto'), datos['regresar'],
        )
        plan['origen'] = {'nombre': datos['origen_nombre'], 'latitud': datos['origen'][0],
                          'longitud': datos['origen'][1]}
        registrar('ruta_planeada', usuario=request.user if request.user.is_authenticated else None)
        return Response(plan)


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
        'seo': {'titulo': 'Armar una ruta por Jalisco — InfoTrip',
                'descripcion': 'Dinos cuántos días tienes y qué te gusta: armamos un itinerario por Jalisco que '
                               'respeta horarios, distancias y tu presupuesto.'},
    })
