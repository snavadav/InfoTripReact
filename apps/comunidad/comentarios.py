"""Comentarios sobre el sitio: problemas e ideas de quienes lo prueban. Solo los lee el equipo."""
from django.shortcuts import render
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.metricas.models import registrar
from .models import Comentario


class ComentarioAnonimoThrottle(AnonRateThrottle):
    rate = '10/hour'
    scope = 'comentarios_anonimos'


class ComentarioThrottle(UserRateThrottle):
    rate = '30/hour'
    scope = 'comentarios'


class ComentarioSerializer(serializers.ModelSerializer):
    # Campo trampa: invisible para las personas; los robots que llenan todo se delatan.
    sitio_web = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Comentario
        fields = ['tipo', 'texto', 'pagina', 'sitio_web']

    def validate_pagina(self, pagina):
        # Solo rutas del propio sitio: la página de origen ayuda a reproducir el problema, nada más.
        return pagina if pagina.startswith('/') and not pagina.startswith('//') else ''


class ComentariosView(APIView):
    """POST: envía un problema o una idea. Con sesión se asocia a la cuenta para poder responder."""
    permission_classes = [AllowAny]
    throttle_classes = [ComentarioAnonimoThrottle, ComentarioThrottle]

    @extend_schema(request=ComentarioSerializer, responses={201: inline_serializer('ComentarioRecibido', fields={
        'mensaje': serializers.CharField(),
    })})
    def post(self, request):
        datos = ComentarioSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = dict(datos.validated_data)
        if not campos.pop('sitio_web', ''):
            usuario = request.user if request.user.is_authenticated else None
            Comentario.objects.create(usuario=usuario, **campos)
            registrar('comentario_enviado', usuario=usuario)
        return Response({'mensaje': 'Gracias. Lo leeremos para mejorar InfoTrip.'}, status=201)


def pagina_comentarios(request):
    desde = request.GET.get('desde', '')
    return render(request, 'comunidad/comentarios.html', {
        'desde': desde if desde.startswith('/') and not desde.startswith('//') else '',
    })
