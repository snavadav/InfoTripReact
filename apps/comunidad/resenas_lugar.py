"""Opiniones sobre lugares útiles: reseñas con moderación y "¿Sigue abierto?".

Son aparte de los aportes sobre destinos porque un lugar no tiene gastos, fotos ni datos prácticos.
Las coordenadas solo se comparan al enviar: se guarda el resultado, nunca dónde estaba la persona.
"""
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.geo import distancia_km
from apps.destinos.models import Lugar
from apps.metricas.models import registrar
from .models import ConfirmacionLugar, ReporteResenaLugar, ResenaLugar
from .selectors import estado_de_lugar, resenas_publicas_de_lugar
from .views import AporteThrottle

# Las coordenadas de un negocio son precisas; 300 m admiten el error normal de un teléfono.
METROS_PARA_COMPROBAR = 300


def lugar_activo(pk):
    return get_object_or_404(Lugar, pk=pk, es_activo=True)


class ResenaLugarSerializer(serializers.ModelSerializer):
    autor_nombre = serializers.CharField(source='autor.nombre', read_only=True)
    estado_nombre = serializers.CharField(source='get_estado_display', read_only=True)
    lugar_nombre = serializers.CharField(source='lugar.nombre', read_only=True)
    latitud = serializers.FloatField(write_only=True, required=False, min_value=-90, max_value=90)
    longitud = serializers.FloatField(write_only=True, required=False, min_value=-180, max_value=180)

    class Meta:
        model = ResenaLugar
        fields = ['id', 'lugar', 'lugar_nombre', 'calificacion', 'texto', 'fecha_visita', 'ubicacion_comprobada',
                  'estado', 'estado_nombre', 'creado', 'autor_nombre', 'latitud', 'longitud']
        read_only_fields = ['lugar', 'ubicacion_comprobada', 'estado', 'creado']
        validators = []

    def validate_fecha_visita(self, fecha):
        if fecha > timezone.localdate():
            raise serializers.ValidationError('La fecha no puede estar en el futuro.')
        return fecha

    def validate(self, datos):
        latitud, longitud = datos.pop('latitud', None), datos.pop('longitud', None)
        if (latitud is None) != (longitud is None):
            raise serializers.ValidationError('Envía la ubicación completa o no envíes ninguna.')
        if latitud is not None:
            lugar = self.context['lugar']
            distancia = distancia_km(latitud, longitud, float(lugar.latitud), float(lugar.longitud))
            datos['ubicacion_comprobada'] = distancia * 1000 <= METROS_PARA_COMPROBAR
        return datos


class ResenasLugarView(generics.ListCreateAPIView):
    """GET: reseñas publicadas. POST: envía una a revisión; una por persona y lugar."""
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = ResenaLugarSerializer
    throttle_classes = [AporteThrottle]

    def get_throttles(self):
        return super().get_throttles() if self.request.method == 'POST' else []

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'lugar': lugar_activo(self.kwargs['pk'])}

    def get_queryset(self):
        return resenas_publicas_de_lugar(lugar_activo(self.kwargs['pk']))

    def perform_create(self, serializer):
        lugar = serializer.context['lugar']
        try:
            with transaction.atomic():
                serializer.save(autor=self.request.user, lugar=lugar, estado='pendiente')
                registrar('resena_lugar_enviada', usuario=self.request.user, destino=f'lugar-{lugar.pk}')
        except IntegrityError:
            raise serializers.ValidationError('Ya tienes una reseña de este lugar. Puedes editarla.')


OPINION = inline_serializer('MiOpinionDeLugar', fields={
    'resena': ResenaLugarSerializer(allow_null=True),
    'abierto': serializers.BooleanField(allow_null=True),
})


class MiOpinionLugarView(APIView):
    """GET: lo que la persona ya dijo de este lugar. PATCH edita su reseña; DELETE la retira."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [AporteThrottle]

    def get_throttles(self):
        return [] if self.request.method == 'GET' else super().get_throttles()

    def resena(self, request, pk):
        return ResenaLugar.objects.filter(autor=request.user, lugar_id=pk).exclude(estado='retirado').first()

    @extend_schema(responses={200: OPINION})
    def get(self, request, pk):
        lugar = lugar_activo(pk)
        resena = self.resena(request, pk)
        confirmacion = ConfirmacionLugar.objects.filter(autor=request.user, lugar=lugar).first()
        return Response({'resena': ResenaLugarSerializer(resena).data if resena else None,
                         'abierto': confirmacion.abierto if confirmacion else None})

    @extend_schema(request=ResenaLugarSerializer, responses={200: ResenaLugarSerializer})
    def patch(self, request, pk):
        lugar = lugar_activo(pk)
        resena = self.resena(request, pk)
        if not resena:
            raise serializers.ValidationError('Todavía no tienes una reseña de este lugar.')
        datos = ResenaLugarSerializer(resena, data=request.data, partial=True, context={'lugar': lugar})
        datos.is_valid(raise_exception=True)
        datos.save(estado='pendiente')
        return Response(datos.data)

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        # Retirar conserva la autoría y el historial de moderación, como en los aportes.
        ResenaLugar.objects.filter(autor=request.user, lugar_id=pk).exclude(estado='retirado').update(estado='retirado')
        return Response(status=204)


ESTADO = inline_serializer('EstadoDeLugar', fields={
    'abiertos': serializers.IntegerField(), 'cerrados': serializers.IntegerField(),
    'ultima': serializers.DateField(allow_null=True), 'posible_cierre': serializers.BooleanField(),
})


class EstadoLugarView(APIView):
    """POST: "¿Sigue abierto?". Sin moderación porque no añade texto; repetir solo actualiza la respuesta."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [AporteThrottle]

    @extend_schema(
        request=inline_serializer('RespuestaSigueAbierto', fields={'abierto': serializers.BooleanField()}),
        responses={200: ESTADO},
    )
    def post(self, request, pk):
        lugar = lugar_activo(pk)
        abierto = serializers.BooleanField().run_validation(request.data.get('abierto'))
        _, creada = ConfirmacionLugar.objects.update_or_create(
            lugar=lugar, autor=request.user, defaults={'abierto': abierto, 'fecha': timezone.localdate()},
        )
        if creada:
            registrar('lugar_confirmado', usuario=request.user, destino=f'lugar-{lugar.pk}')
        return Response(estado_de_lugar(lugar))


class ReporteResenaLugarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReporteResenaLugar
        fields = ['id', 'motivo', 'resuelto', 'creado']
        read_only_fields = ['resuelto', 'creado']


class ReportarResenaLugarView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ReporteResenaLugarSerializer
    throttle_classes = [AporteThrottle]

    def perform_create(self, serializer):
        publicadas = ResenaLugar.objects.filter(estado='publicado', lugar__es_activo=True)
        resena = get_object_or_404(publicadas, pk=self.kwargs['pk'])
        if resena.autor_id == self.request.user.pk:
            raise serializers.ValidationError('Puedes editar o retirar tu propia reseña.')
        try:
            with transaction.atomic():
                serializer.save(autor=self.request.user, resena=resena)
                registrar('reporte_enviado', usuario=self.request.user, destino=f'lugar-{resena.lugar_id}')
        except IntegrityError:
            raise serializers.ValidationError('Ya reportaste esta reseña.')


class MisResenasLugarView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ResenaLugarSerializer

    def get_queryset(self):
        return (ResenaLugar.objects.filter(autor=self.request.user).exclude(estado='retirado')
                .select_related('autor', 'lugar'))
