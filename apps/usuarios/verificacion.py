"""Inicio de sesión en dos pasos: contraseña y código enviado al buzón."""
import hashlib
import logging
import secrets
import uuid
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import APIException, AuthenticationFailed, Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from .authentication import CorreoJWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import aware_utcnow, datetime_from_epoch
from .sesion import COOKIE_REFRESH, borrar_cookie_refresh, exigir_csrf, guardar_cookie_refresh
from rest_framework_simplejwt.views import TokenRefreshView

from .models import CodigoAcceso, Usuario
from .serializers import UsuarioPerfilSerializer


class CorreoNoDisponible(APIException):
    status_code = 503
    default_detail = 'No pudimos enviar el código. Intenta de nuevo más tarde.'


class LoginThrottle(AnonRateThrottle):
    rate = '10/min'
    scope = 'login_correo'


class VerificacionThrottle(AnonRateThrottle):
    rate = '30/min'
    scope = 'verificacion_correo'


class CredencialesSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=1024)


class CodigoSerializer(serializers.Serializer):
    desafio = serializers.UUIDField()
    codigo = serializers.RegexField(r'\A[0-9]{6}\Z', max_length=6, min_length=6, trim_whitespace=True)


def hash_codigo(desafio, codigo):
    return salted_hmac('infotrip.login.codigo', f'{desafio}:{codigo}', algorithm='sha256').hexdigest()


def hash_credencial(usuario):
    return salted_hmac('infotrip.login.credencial', usuario.password, algorithm='sha256').hexdigest()


registro_seguridad = logging.getLogger('infotrip.seguridad')
registro_correo = logging.getLogger('infotrip.correo')

# Límite por cuenta, independiente de la IP: frena la prueba de contraseñas distribuida.
LOGIN_MAX_FALLOS = 5
LOGIN_BLOQUEO_SEGUNDOS = 15 * 60


def clave_fallos(email):
    return 'login_fallos:' + hashlib.sha256(email.strip().lower().encode()).hexdigest()


def registrar_fallo(clave):
    # La ventana empieza en el primer fallo; incr conserva la caducidad original.
    cache.add(clave, 0, LOGIN_BLOQUEO_SEGUNDOS)
    try:
        fallos = cache.incr(clave)
    except ValueError:
        cache.set(clave, 1, LOGIN_BLOQUEO_SEGUNDOS)
        fallos = 1
    if fallos == LOGIN_MAX_FALLOS:
        # La huella identifica la cuenta en los registros sin escribir el correo.
        registro_seguridad.warning('Cuenta bloqueada %s min tras %s contraseñas incorrectas (huella %s)',
                                   LOGIN_BLOQUEO_SEGUNDOS // 60, LOGIN_MAX_FALLOS, clave[-12:])


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginThrottle]

    @extend_schema(request=CredencialesSerializer, responses={200: inline_serializer('DesafioLogin', fields={
        'requiere_codigo': serializers.BooleanField(), 'desafio': serializers.UUIDField(),
        'expira_en': serializers.IntegerField(), 'reenviar_en': serializers.IntegerField(),
        'modo_prueba': serializers.BooleanField(), 'mensaje': serializers.CharField(),
    })})
    def post(self, request):
        datos = CredencialesSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        fallos = clave_fallos(datos.validated_data['email'])
        if cache.get(fallos, 0) >= LOGIN_MAX_FALLOS:
            raise Throttled(wait=LOGIN_BLOQUEO_SEGUNDOS,
                            detail='Demasiados intentos fallidos para esta cuenta. Espera unos minutos.')
        usuario = authenticate(request=request, **datos.validated_data)
        if usuario is None:
            registrar_fallo(fallos)
            raise AuthenticationFailed('Correo o contraseña incorrectos.')
        cache.delete(fallos)
        # Bloquear siempre primero al usuario: serializa envío y verificación en PostgreSQL.
        with transaction.atomic():
            usuario = Usuario.objects.select_for_update().get(pk=usuario.pk)
            if not usuario.es_activo or not usuario.check_password(datos.validated_data['password']):
                raise AuthenticationFailed('Correo o contraseña incorrectos.')
            anterior = CodigoAcceso.objects.filter(usuario=usuario).first()
            ahora = timezone.now()
            if anterior:
                restante = 60 - (ahora - anterior.enviado).total_seconds()
                if restante > 0:
                    raise Throttled(wait=int(restante) + 1, detail='Espera un minuto entre envíos.')
            if settings.EMAIL_BACKEND.endswith('smtp.EmailBackend') and not settings.EMAIL_HOST:
                raise CorreoNoDisponible()
            codigo = f'{secrets.randbelow(1000000):06d}'
            desafio = uuid.uuid4()
            CodigoAcceso.objects.update_or_create(usuario=usuario, defaults={
                'desafio': desafio, 'codigo_hash': hash_codigo(desafio, codigo),
                'credencial_hash': hash_credencial(usuario), 'email': usuario.email,
                'enviado': ahora, 'expira': ahora + timedelta(minutes=10),
                'intentos': 0, 'consumido': False,
            })
        # El envío ocurre ya confirmada la transacción: el SMTP puede tardar hasta EMAIL_TIMEOUT
        # y no debe retener el bloqueo de la fila. La marca 'enviado' ya impide reenvíos simultáneos.
        try:
            enviados = send_mail(
                'Tu código de acceso a InfoTrip',
                f'Tu código para iniciar sesión en InfoTrip es: {codigo}\n\n'
                'Caduca en 10 minutos y solo puede utilizarse una vez.\n'
                'No lo compartas. Si no solicitaste este acceso, ignora este mensaje.',
                settings.DEFAULT_FROM_EMAIL, [usuario.email], fail_silently=False,
            )
            if enviados != 1:
                raise CorreoNoDisponible()
        except (SMTPException, OSError, CorreoNoDisponible) as error:
            registro_correo.error('No se pudo enviar el código de acceso al usuario %s: %r', usuario.pk, error)
            # Sin correo entregado el desafío no sirve; se retira para permitir reintentar.
            CodigoAcceso.objects.filter(usuario=usuario, desafio=desafio).delete()
            if isinstance(error, CorreoNoDisponible):
                raise
            raise CorreoNoDisponible() from error
        return Response({'requiere_codigo': True, 'desafio': str(desafio), 'expira_en': 600,
                         'reenviar_en': 60,
                         'modo_prueba': settings.EMAIL_BACKEND.endswith('console.EmailBackend'),
                         'mensaje': 'Código de acceso generado.'})


class VerificarCodigoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [VerificacionThrottle]

    @extend_schema(request=CodigoSerializer, responses={200: inline_serializer('SesionIniciada', fields={
        'access': serializers.CharField(), 'usuario': UsuarioPerfilSerializer(),
    })})
    def post(self, request):
        datos = CodigoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        desafio = datos.validated_data['desafio']
        propietario = CodigoAcceso.objects.filter(desafio=desafio).values_list('usuario_id', flat=True).first()
        error = {'detail': 'Código incorrecto, vencido o no disponible. Solicita uno nuevo si es necesario.'}
        if propietario is None:
            return Response(error, status=400)
        with transaction.atomic():
            usuario = Usuario.objects.select_for_update().get(pk=propietario)
            registro = CodigoAcceso.objects.filter(usuario=usuario, desafio=desafio).first()
            if (not registro or registro.consumido or registro.expira <= timezone.now()
                    or registro.intentos >= 5 or not usuario.es_activo
                    or registro.email != usuario.email
                    or not constant_time_compare(registro.credencial_hash, hash_credencial(usuario))):
                return Response(error, status=400)
            if not constant_time_compare(registro.codigo_hash, hash_codigo(desafio, datos.validated_data['codigo'])):
                registro.intentos += 1
                registro.save(update_fields=['intentos'])
                return Response(error, status=400)
            registro.consumido = True
            registro.save(update_fields=['consumido'])
            usuario.es_verificado = True
            usuario.ultimo_acceso = timezone.now()
            usuario.save(update_fields=['es_verificado', 'ultimo_acceso'])
            refresh = RefreshToken.for_user(usuario)
            refresh['correo_confirmado'] = True
            respuesta = Response({'access': str(refresh.access_token),
                                  'usuario': UsuarioPerfilSerializer(usuario, context={'request': request}).data})
            guardar_cookie_refresh(request, respuesta, refresh)
            return respuesta


# La sesión se extiende con el uso, pero el refresh token cambia como mucho una vez al día.
ROTAR_REFRESH_CADA = timedelta(days=1)


class CorreoRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        token = self.token_class(attrs['refresh'])
        CorreoJWTAuthentication().get_user(token)
        datos = super().validate(attrs)
        if aware_utcnow() - datetime_from_epoch(token['iat']) >= ROTAR_REFRESH_CADA:
            token.blacklist()
            token.set_jti()
            token.set_exp()
            token.set_iat()
            token.outstand()
            datos['refresh'] = str(token)
        return datos


class CorreoRefreshView(TokenRefreshView):
    """Entrega un access token nuevo a partir de la cookie de sesión; no recibe el token en el cuerpo."""
    serializer_class = CorreoRefreshSerializer
    authentication_classes = []

    @extend_schema(request=None, responses={200: inline_serializer('AccessRenovado', fields={
        'access': serializers.CharField(),
    })})
    def post(self, request, *args, **kwargs):
        exigir_csrf(request)
        refresh = request.COOKIES.get(COOKIE_REFRESH)
        if not refresh:
            return Response({'detail': 'No hay una sesión activa.'}, status=401)
        serializador = self.get_serializer(data={'refresh': refresh})
        try:
            serializador.is_valid(raise_exception=True)
        except (TokenError, AuthenticationFailed):
            respuesta = Response({'detail': 'Tu sesión terminó. Inicia sesión nuevamente.'}, status=401)
            borrar_cookie_refresh(respuesta)
            return respuesta
        datos = serializador.validated_data
        respuesta = Response({'access': datos['access']})
        if 'refresh' in datos:
            guardar_cookie_refresh(request, respuesta, datos['refresh'])
        return respuesta
