"""Lugares útiles alrededor de un punto: dónde comer, dormir, cargar gasolina, farmacias y cajeros.

La ubicación de "Cerca de mí" llega por POST, para que no quede en los registros del servidor como parte
de la dirección, y se usa solo para calcular distancias: no se guarda en ningún lado.
"""
from math import cos, radians

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.geo import distancia_km
from .models import Lugar

KM_POR_GRADO = 111.32
RADIO_CERCA_KM = 5
RADIO_MAXIMO_KM = 25
MAXIMO_EN_ZONA = 300
MAXIMO_CERCA = 50
# Más grande que esto, una zona devolvería miles de marcadores; el mapa pide acercarse antes.
GRADOS_MAXIMOS_DE_ZONA = 2


class ZonaThrottle(AnonRateThrottle):
    # Mover el mapa pide una zona cada vez: el límite debe permitir explorar con calma.
    rate = '240/min'
    scope = 'lugares_zona'


class CercaThrottle(AnonRateThrottle):
    rate = '30/min'
    scope = 'lugares_cerca'


def activos():
    return Lugar.objects.filter(es_activo=True).select_related('municipio')


def cerca_de(latitud, longitud, radio_km=RADIO_CERCA_KM, tipo='', limite=MAXIMO_CERCA):
    """Los lugares más próximos, con `distancia_km`. El recuadro evita calcular la distancia a todos."""
    grados_lat = radio_km / KM_POR_GRADO
    grados_lng = radio_km / (KM_POR_GRADO * max(cos(radians(latitud)), 0.01))
    candidatos = activos().filter(
        latitud__range=(latitud - grados_lat, latitud + grados_lat),
        longitud__range=(longitud - grados_lng, longitud + grados_lng),
    )
    if tipo:
        candidatos = candidatos.filter(tipo=tipo)
    resultados = []
    for lugar in candidatos:
        lugar.distancia_km = round(distancia_km(latitud, longitud, float(lugar.latitud), float(lugar.longitud)), 2)
        if lugar.distancia_km <= radio_km:
            resultados.append(lugar)
    resultados.sort(key=lambda lugar: (lugar.distancia_km, lugar.pk))
    return resultados[:limite]


def cercanos_de_destino(destino):
    """Para la ficha: unos cuantos de cada tipo, del más próximo al más lejano. Vacíos si no hay ninguno."""
    latitud, longitud = float(destino.latitud), float(destino.longitud)
    grupos = [('Dónde comer', 'comer', 5), ('Dónde dormir', 'dormir', 5), ('Gasolina', 'gasolina', 2),
              ('Farmacias', 'farmacia', 2), ('Cajeros y bancos', 'cajero', 2)]
    cerca = [{'titulo': titulo, 'lugares': cerca_de(latitud, longitud, tipo=tipo, limite=limite)}
             for titulo, tipo, limite in grupos]
    return [grupo for grupo in cerca if grupo['lugares']]


class LugarSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source='get_tipo_display', read_only=True)
    subtipo_nombre = serializers.CharField(source='get_subtipo_display', read_only=True)
    municipio = serializers.CharField(source='municipio.nombre', read_only=True, default='')
    distancia_km = serializers.FloatField(read_only=True, default=None)
    osm_url = serializers.SerializerMethodField()
    atribucion = serializers.SerializerMethodField()

    class Meta:
        model = Lugar
        fields = ['id', 'nombre', 'tipo', 'tipo_nombre', 'subtipo_nombre', 'municipio', 'latitud', 'longitud',
                  'direccion', 'telefono', 'sitio_web', 'horario', 'distancia_km', 'osm_url', 'atribucion']

    def get_osm_url(self, lugar) -> str:
        return f'https://www.openstreetmap.org/{lugar.osm_id}' if lugar.osm_id else ''

    def get_atribucion(self, lugar) -> str | None:
        return '© colaboradores de OpenStreetMap, ODbL' if lugar.osm_id else None


class ZonaSerializer(serializers.Serializer):
    sur = serializers.FloatField(min_value=-90, max_value=90)
    oeste = serializers.FloatField(min_value=-180, max_value=180)
    norte = serializers.FloatField(min_value=-90, max_value=90)
    este = serializers.FloatField(min_value=-180, max_value=180)
    tipo = serializers.ChoiceField(choices=Lugar.TIPOS, required=False)

    def validate(self, datos):
        alto, ancho = datos['norte'] - datos['sur'], datos['este'] - datos['oeste']
        if alto < 0 or ancho < 0:
            raise serializers.ValidationError('La zona no es válida.')
        if alto > GRADOS_MAXIMOS_DE_ZONA or ancho > GRADOS_MAXIMOS_DE_ZONA:
            raise serializers.ValidationError('La zona es demasiado grande: acércate en el mapa.')
        return datos


class BusquedaCercanaSerializer(serializers.Serializer):
    latitud = serializers.FloatField(min_value=-90, max_value=90)
    longitud = serializers.FloatField(min_value=-180, max_value=180)
    radio_km = serializers.FloatField(min_value=0.1, max_value=RADIO_MAXIMO_KM, default=RADIO_CERCA_KM)
    tipo = serializers.ChoiceField(choices=Lugar.TIPOS, required=False)


class LugaresZonaView(APIView):
    """GET: lugares dentro de la parte visible del mapa."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ZonaThrottle]

    @extend_schema(parameters=[ZonaSerializer], responses={200: inline_serializer('LugaresDeZona', fields={
        'resultados': LugarSerializer(many=True), 'truncado': serializers.BooleanField(),
    })})
    def get(self, request):
        zona = ZonaSerializer(data=request.query_params)
        zona.is_valid(raise_exception=True)
        datos = zona.validated_data
        lugares = activos().filter(latitud__range=(datos['sur'], datos['norte']),
                                   longitud__range=(datos['oeste'], datos['este']))
        if datos.get('tipo'):
            lugares = lugares.filter(tipo=datos['tipo'])
        # Uno de más, para saber si quedaron fuera sin contar toda la zona.
        encontrados = list(lugares.order_by('pk')[:MAXIMO_EN_ZONA + 1])
        return Response({'resultados': LugarSerializer(encontrados[:MAXIMO_EN_ZONA], many=True).data,
                         'truncado': len(encontrados) > MAXIMO_EN_ZONA})


class LugaresCercaView(APIView):
    """POST: lo más próximo a una ubicación, ordenado por distancia. La ubicación no se guarda."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [CercaThrottle]

    @extend_schema(request=BusquedaCercanaSerializer, responses={200: inline_serializer('LugaresCercanos', fields={
        'resultados': LugarSerializer(many=True), 'radio_km': serializers.FloatField(),
    })})
    def post(self, request):
        ubicacion = BusquedaCercanaSerializer(data=request.data)
        ubicacion.is_valid(raise_exception=True)
        datos = ubicacion.validated_data
        lugares = cerca_de(datos['latitud'], datos['longitud'], datos['radio_km'], datos.get('tipo', ''))
        return Response({'resultados': LugarSerializer(lugares, many=True).data, 'radio_km': datos['radio_km']})
