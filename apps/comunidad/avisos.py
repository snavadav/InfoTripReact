"""Avisos internos al usuario: la lista, marcarlos como leídos y elegir cuáles recibir."""
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Notificacion
from .notificar import OPCIONES_TIPO, TIPOS, datos_tipo, visibles

NO_LEIDAS = inline_serializer('AvisosLeidos', fields={'no_leidas': serializers.IntegerField()})


class NotificacionSerializer(serializers.ModelSerializer):
    accion = serializers.SerializerMethodField()

    class Meta:
        model = Notificacion
        fields = ['id', 'tipo', 'texto', 'enlace', 'accion', 'leida', 'creado']
        read_only_fields = fields

    def get_accion(self, aviso) -> str:
        return datos_tipo(aviso.tipo)['accion']


class NotificacionesView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificacionSerializer

    def get_queryset(self):
        return visibles(self.request.user)

    def list(self, request, *args, **kwargs):
        respuesta = super().list(request, *args, **kwargs)
        respuesta.data['no_leidas'] = self.get_queryset().filter(leida=False).count()
        return respuesta


class NotificacionesLeidasView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: NO_LEIDAS})
    def post(self, request):
        Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
        return Response({'no_leidas': 0})


class NotificacionLeidaView(APIView):
    """POST: marca un aviso como leído; lo usa el enlace ?aviso=<id> de cada correo (avisos-nav.js)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: NO_LEIDAS})
    def post(self, request, pk):
        get_object_or_404(Notificacion, pk=pk, usuario=request.user)
        Notificacion.objects.filter(pk=pk).update(leida=True)
        return Response({'no_leidas': visibles(request.user).filter(leida=False).count()})


class PreferenciasAvisosSerializer(serializers.Serializer):
    correo = serializers.BooleanField()
    silenciados = serializers.ListField(child=serializers.ChoiceField(choices=OPCIONES_TIPO), max_length=len(TIPOS))
    sin_correo = serializers.ListField(child=serializers.ChoiceField(choices=OPCIONES_TIPO), max_length=len(TIPOS))


class PreferenciasAvisosView(APIView):
    """GET: los tipos de aviso y cómo los recibe la persona. PUT {correo, silenciados, sin_correo}: los cambia."""
    permission_classes = [IsAuthenticated]

    def estado(self, usuario):
        return {
            'correo': usuario.avisos_correo,
            'silenciados': [tipo for tipo in TIPOS if tipo in (usuario.avisos_silenciados or [])],
            'sin_correo': [tipo for tipo in TIPOS if tipo in (usuario.avisos_sin_correo or [])],
            'tipos': [{'tipo': tipo, 'nombre': datos['nombre'], 'detalle': datos['detalle'],
                       'correo_posible': datos['correo']} for tipo, datos in TIPOS.items()],
        }

    @extend_schema(responses={200: inline_serializer('EstadoPreferenciasAvisos', fields={
        'correo': serializers.BooleanField(), 'silenciados': serializers.ListField(child=serializers.CharField()),
        'sin_correo': serializers.ListField(child=serializers.CharField()),
        'tipos': inline_serializer('TipoAviso', many=True, fields={
            'tipo': serializers.CharField(), 'nombre': serializers.CharField(), 'detalle': serializers.CharField(),
            'correo_posible': serializers.BooleanField(),
        }),
    })})
    def get(self, request):
        return Response(self.estado(request.user))

    @extend_schema(request=PreferenciasAvisosSerializer, responses={200: None})
    def put(self, request):
        datos = PreferenciasAvisosSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        usuario = request.user
        usuario.avisos_correo = datos.validated_data['correo']
        usuario.avisos_silenciados = sorted(set(datos.validated_data['silenciados']))
        usuario.avisos_sin_correo = sorted(set(datos.validated_data['sin_correo']))
        usuario.save(update_fields=['avisos_correo', 'avisos_silenciados', 'avisos_sin_correo'])
        # Lo que estaba por enviarse de un tipo que ahora no se quiere por correo ya no sale.
        apagados = set(usuario.avisos_silenciados) | set(usuario.avisos_sin_correo)
        pendientes = Notificacion.objects.filter(usuario=usuario, correo_pendiente=True)
        if not usuario.avisos_correo:
            pendientes.update(correo_pendiente=False)
        elif apagados:
            pendientes.filter(tipo__in=apagados).update(correo_pendiente=False)
        return Response(self.estado(usuario))
