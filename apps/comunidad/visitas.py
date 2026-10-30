"""Visita comprobada: la persona confirma con su ubicación que está cerca de un destino.

Las coordenadas solo se comparan y se descartan: se guarda el resultado, nunca dónde estaba.
Una ubicación se puede falsear, por eso la etiqueta dice "comprobó su ubicación" y no "verificado".
"""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.geo import distancia_km
from apps.destinos.models import Destino
from apps.metricas.models import registrar
from .models import VisitaComprobada
from .views import AporteThrottle

# Las coordenadas del catálogo son orientativas, de la localidad: un radio menor rechazaría visitas reales.
RADIO_KM = 5


class UbicacionSerializer(serializers.Serializer):
    latitud = serializers.FloatField(min_value=-90, max_value=90)
    longitud = serializers.FloatField(min_value=-180, max_value=180)


ESTADO_VISITA = inline_serializer('EstadoVisita', fields={
    'comprobada': serializers.BooleanField(), 'fecha': serializers.DateField(allow_null=True),
})


class VisitaView(APIView):
    """GET: si ya comprobaste tu visita. POST: compara tu ubicación con la del destino."""
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        return [AporteThrottle()] if self.request.method == 'POST' else []

    @extend_schema(responses={200: ESTADO_VISITA})
    def get(self, request, slug):
        destino = get_object_or_404(Destino, slug=slug, es_activo=True)
        visita = VisitaComprobada.objects.filter(autor=request.user, destino=destino).first()
        return Response({'comprobada': bool(visita), 'fecha': visita.fecha if visita else None})

    @extend_schema(request=UbicacionSerializer, responses={200: ESTADO_VISITA})
    def post(self, request, slug):
        destino = get_object_or_404(Destino, slug=slug, es_activo=True)
        ubicacion = UbicacionSerializer(data=request.data)
        ubicacion.is_valid(raise_exception=True)
        distancia = distancia_km(ubicacion.validated_data['latitud'], ubicacion.validated_data['longitud'],
                                 float(destino.latitud), float(destino.longitud))
        if distancia > RADIO_KM:
            raise serializers.ValidationError(f'Para comprobar tu visita debes estar a menos de {RADIO_KM} km.')
        hoy = timezone.localdate()
        _, creada = VisitaComprobada.objects.update_or_create(
            autor=request.user, destino=destino, defaults={'fecha': hoy}
        )
        if creada:
            registrar('visita_comprobada', usuario=request.user, destino=destino.slug)
        return Response({'comprobada': True, 'fecha': hoy})
