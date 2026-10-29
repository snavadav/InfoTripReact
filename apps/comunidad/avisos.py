"""Avisos internos al usuario (cambios de estado de sus aportes y colaboraciones)."""
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Notificacion


class NotificacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notificacion
        fields = ['id', 'texto', 'enlace', 'leida', 'creado']
        read_only_fields = fields


class NotificacionesView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificacionSerializer

    def get_queryset(self):
        return Notificacion.objects.filter(usuario=self.request.user)

    def list(self, request, *args, **kwargs):
        respuesta = super().list(request, *args, **kwargs)
        respuesta.data['no_leidas'] = self.get_queryset().filter(leida=False).count()
        return respuesta


class NotificacionesLeidasView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
        return Response({'no_leidas': 0})
