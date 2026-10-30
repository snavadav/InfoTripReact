from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from apps.destinos.models import Destino
from apps.metricas.models import registrar
from .models import Aporte
from .serializers import AporteSerializer, ReporteSerializer
from .selectors import aportes_publicos, publicados


class AporteThrottle(UserRateThrottle):
    rate = '30/hour'
    scope = 'aportes'


class PublicarView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = AporteSerializer
    throttle_classes = [AporteThrottle]
    def get_throttles(self):
        return super().get_throttles() if self.request.method == 'POST' else []
    def get_queryset(self):
        destino = get_object_or_404(Destino, slug=self.kwargs['slug'], es_activo=True)
        return aportes_publicos(destino).select_related('destino')
    def perform_create(self, serializer):
        destino = get_object_or_404(Destino, slug=self.kwargs['slug'], es_activo=True)
        try:
            with transaction.atomic():
                serializer.save(autor=self.request.user, destino=destino, estado='pendiente')
                registrar('aporte_enviado', usuario=self.request.user, destino=destino.slug)
        except IntegrityError:
            raise serializers.ValidationError('Ya tienes una reseña de este destino. Edítala desde tu perfil.')


class MisAportesView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AporteSerializer
    def get_queryset(self):
        return (
            Aporte.objects.filter(autor=self.request.user).exclude(estado='retirado').select_related('autor', 'destino')
        )


class EditarAporteView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AporteSerializer
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']
    def get_queryset(self):
        return (
            Aporte.objects.filter(autor=self.request.user).exclude(estado='retirado').select_related('autor', 'destino')
        )

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            aporte = get_object_or_404(self.get_queryset().select_for_update(), pk=kwargs['pk'])
            if not aporte.destino.es_activo:
                raise serializers.ValidationError('Este destino no está disponible. Puedes retirar el aporte.')
            serializer = self.get_serializer(aporte, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save(estado='pendiente')
            return Response(serializer.data)
    def perform_destroy(self, instance):
        # Retirar conserva la autoría y el historial de moderación.
        Aporte.objects.filter(pk=instance.pk, autor=self.request.user).update(estado='retirado')


class ReportarView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ReporteSerializer
    throttle_classes = [AporteThrottle]
    def perform_create(self, serializer):
        aporte = get_object_or_404(publicados(), pk=self.kwargs['pk'])
        if aporte.autor_id == self.request.user.pk:
            raise serializers.ValidationError('Puedes editar o retirar tus propios aportes desde tu perfil.')
        try:
            with transaction.atomic():
                serializer.save(autor=self.request.user, aporte=aporte)
                registrar('reporte_enviado', usuario=self.request.user, destino=aporte.destino.slug)
        except IntegrityError:
            raise serializers.ValidationError('Ya reportaste este aporte.')
