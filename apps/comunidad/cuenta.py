"""Baja de cuenta: borra los datos personales y anonimiza lo que debe conservarse.

La cuenta no se elimina de la base: el historial de moderación y los reportes la referencian
(PROTECT) y deben seguir siendo auditables. Lo que identifica a la persona desaparece.
"""
import uuid

from django.db import transaction
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.metricas.models import Evento
from apps.usuarios.models import CodigoAcceso
from apps.usuarios.sesion import borrar_cookie_refresh
from .models import (
    Aporte, Colaboracion, Confirmacion, Favorito, GastoReal, Notificacion, Participante, PasaporteCompartido, Viaje,
    VisitaComprobada,
)

TEXTO_ELIMINADO = '[Eliminado por su autor]'


class ConfirmarBajaSerializer(serializers.Serializer):
    password = serializers.CharField()


def anonimizar_cuenta(usuario):
    """Debe ejecutarse en una transacción. Los archivos se borran solo si esta se confirma."""
    archivos = [archivo for aporte in Aporte.objects.filter(autor=usuario).exclude(imagen='')
                for archivo in (aporte.imagen, aporte.miniatura) if archivo]
    if usuario.foto_perfil:
        archivos.append(usuario.foto_perfil)
    Aporte.objects.filter(autor=usuario).update(
        estado='retirado', texto=TEXTO_ELIMINADO, imagen='', miniatura=''
    )
    Colaboracion.objects.filter(autor=usuario).update(estado='oculto', texto=TEXTO_ELIMINADO, fuente='')
    for modelo in (Viaje, Favorito, Confirmacion, VisitaComprobada):
        modelo.objects.filter(autor=usuario).delete()
    # En botes de otras personas su parte se queda, para que las cuentas del grupo sigan cuadrando.
    Participante.objects.filter(usuario=usuario).update(usuario=None)
    GastoReal.objects.filter(registrado_por=usuario).update(
        registrado_por=None, descripcion='Gasto de una cuenta eliminada'
    )
    Notificacion.objects.filter(usuario=usuario).delete()
    PasaporteCompartido.objects.filter(usuario=usuario).delete()
    CodigoAcceso.objects.filter(usuario=usuario).delete()
    Evento.objects.filter(usuario=usuario).update(usuario=None)
    for token in OutstandingToken.objects.filter(user=usuario):
        BlacklistedToken.objects.get_or_create(token=token)
    usuario.nombre = 'Cuenta'
    usuario.apellido = 'eliminada'
    usuario.email = f'eliminada-{uuid.uuid4().hex}@infotrip.invalid'
    usuario.foto_perfil = None
    usuario.ciudad_origen = ''
    usuario.bio = ''
    usuario.es_activo = False
    usuario.es_verificado = False
    usuario.avisos_correo = False
    usuario.set_unusable_password()
    usuario.save()
    transaction.on_commit(lambda: [archivo.storage.delete(archivo.name) for archivo in archivos])


class EliminarCuentaView(APIView):
    """POST: elimina la cuenta propia tras confirmar la contraseña. No se puede deshacer."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ConfirmarBajaSerializer, responses={200: inline_serializer('CuentaEliminada', fields={
        'mensaje': serializers.CharField(),
    })})
    def post(self, request):
        datos = ConfirmarBajaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        usuario = request.user
        if not usuario.check_password(datos.validated_data['password']):
            raise serializers.ValidationError({'password': 'La contraseña no es correcta.'})
        if usuario.es_staff or usuario.is_superuser:
            raise serializers.ValidationError('Una cuenta de administración debe darse de baja desde el equipo.')
        with transaction.atomic():
            anonimizar_cuenta(usuario)
        respuesta = Response({'mensaje': 'Tu cuenta y tus datos personales se eliminaron.'})
        borrar_cookie_refresh(respuesta)
        return respuesta
