"""Propuestas de lugares que faltan en el mapa. Nada se publica hasta que el equipo lo aprueba."""
from difflib import SequenceMatcher
from math import cos, radians

from django.db import transaction
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.geo import distancia_km
from apps.destinos.models import Lugar
from apps.metricas.models import registrar
from .models import PropuestaLugar
from .views import AporteThrottle

METROS_DE_DUPLICADO = 150
MAXIMO_PENDIENTES = 10
SIMILITUD_MINIMA = 0.75
# Jalisco con un pequeño margen: una propuesta fuera es casi seguro un error al marcar el mapa.
LATITUDES_JALISCO = (18.8, 22.9)
LONGITUDES_JALISCO = (-105.8, -101.4)


def se_parecen(uno, otro):
    a, b = slugify(uno), slugify(otro)
    if not a or not b:
        return uno.strip().lower() == otro.strip().lower()
    return a in b or b in a or SequenceMatcher(None, a, b).ratio() >= SIMILITUD_MINIMA


def lugares_parecidos(nombre, latitud, longitud):
    """Lugares publicados muy cerca y con un nombre parecido, del más próximo al más lejano."""
    grados_lat = METROS_DE_DUPLICADO / 1000 / 111.32
    grados_lng = METROS_DE_DUPLICADO / 1000 / (111.32 * max(cos(radians(latitud)), 0.01))
    cercanos = Lugar.objects.filter(
        es_activo=True, latitud__range=(latitud - grados_lat, latitud + grados_lat),
        longitud__range=(longitud - grados_lng, longitud + grados_lng),
    )
    encontrados = []
    for lugar in cercanos:
        metros = distancia_km(latitud, longitud, float(lugar.latitud), float(lugar.longitud)) * 1000
        if metros <= METROS_DE_DUPLICADO and se_parecen(nombre, lugar.nombre):
            encontrados.append((metros, lugar))
    encontrados.sort(key=lambda fila: (fila[0], fila[1].pk))
    return [lugar for _, lugar in encontrados]


class PropuestaLugarSerializer(serializers.ModelSerializer):
    estado_nombre = serializers.CharField(source='get_estado_display', read_only=True)
    sitio_web = serializers.URLField(required=False, allow_blank=True, max_length=300)
    confirmar_distinto = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = PropuestaLugar
        fields = ['id', 'nombre', 'subtipo', 'latitud', 'longitud', 'direccion', 'telefono', 'sitio_web', 'horario',
                  'nota', 'estado', 'estado_nombre', 'lugar', 'creado', 'confirmar_distinto']
        read_only_fields = ['estado', 'lugar', 'creado']

    def validate_nombre(self, nombre):
        return nombre.strip()

    def validate_sitio_web(self, sitio):
        # El valor termina en un enlace público: solo http y https, nunca ftp ni otros esquemas.
        if sitio and not sitio.startswith(('http://', 'https://')):
            raise serializers.ValidationError('Escribe una dirección que empiece con http:// o https://.')
        return sitio

    def validate(self, datos):
        latitud, longitud = float(datos['latitud']), float(datos['longitud'])
        if not (LATITUDES_JALISCO[0] <= latitud <= LATITUDES_JALISCO[1]
                and LONGITUDES_JALISCO[0] <= longitud <= LONGITUDES_JALISCO[1]):
            raise serializers.ValidationError({'latitud': 'El punto marcado está fuera de Jalisco.'})
        return datos


class PropuestasLugarView(generics.ListCreateAPIView):
    """GET: mis propuestas. POST: envía una a revisión; si ya existe algo parecido, primero lo pregunta."""
    permission_classes = [IsAuthenticated]
    serializer_class = PropuestaLugarSerializer
    throttle_classes = [AporteThrottle]

    def get_throttles(self):
        return super().get_throttles() if self.request.method == 'POST' else []

    def get_queryset(self):
        return PropuestaLugar.objects.filter(autor=self.request.user)

    @extend_schema(request=PropuestaLugarSerializer, responses={
        201: PropuestaLugarSerializer,
        409: inline_serializer('LugaresParecidos', fields={
            'parecidos': inline_serializer('LugarParecido', fields={
                'id': serializers.IntegerField(), 'nombre': serializers.CharField(), 'url': serializers.CharField(),
            }, many=True),
        }),
    })
    def post(self, request, *args, **kwargs):
        datos = self.get_serializer(data=request.data)
        datos.is_valid(raise_exception=True)
        validos = datos.validated_data
        confirmado = validos.pop('confirmar_distinto')
        parecidos = lugares_parecidos(validos['nombre'], float(validos['latitud']), float(validos['longitud']))
        if parecidos and not confirmado:
            return Response({'parecidos': [
                {'id': lugar.pk, 'nombre': lugar.nombre, 'url': f'/lugares/{lugar.pk}/'} for lugar in parecidos[:5]
            ]}, status=409)
        with transaction.atomic():
            propias = PropuestaLugar.objects.select_for_update().filter(autor=request.user, estado='pendiente')
            if len(propias) >= MAXIMO_PENDIENTES:
                raise serializers.ValidationError(
                    f'Tienes {MAXIMO_PENDIENTES} propuestas en revisión. Podrás enviar más cuando las revisemos.')
            propuesta = datos.save(autor=request.user, estado='pendiente')
            registrar('lugar_propuesto', usuario=request.user)
        return Response(self.get_serializer(propuesta).data, status=201)
