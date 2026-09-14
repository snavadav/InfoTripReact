from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from smtplib import SMTPException
from .models import Usuario
from .verificacion import CorreoNoDisponible


class RecuperacionThrottle(AnonRateThrottle):
    rate = '5/hour'
    scope = 'recuperacion'

class SolicitudSerializer(serializers.Serializer):
    email = serializers.EmailField()

class ConfirmacionSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=100)
    token = serializers.CharField(max_length=200)
    password = serializers.CharField(max_length=1024, trim_whitespace=False)
    password2 = serializers.CharField(max_length=1024, trim_whitespace=False)

class RecuperarView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RecuperacionThrottle]
    def post(self, request):
        datos = SolicitudSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        if settings.EMAIL_BACKEND.endswith('smtp.EmailBackend') and not settings.EMAIL_HOST:
            raise CorreoNoDisponible()
        usuario = Usuario.objects.filter(email__iexact=datos.validated_data['email'], es_activo=True).first()
        if usuario and usuario.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(usuario.pk))
            token = default_token_generator.make_token(usuario)
            url = f'{settings.PUBLIC_BASE_URL}/recuperar/?uid={uid}&token={token}'
            try:
                enviados = send_mail('Recupera tu acceso a InfoTrip',
                    f'Abre este enlace para elegir una contraseña nueva. Caduca en una hora:\n{url}\nSi no lo solicitaste, ignora este mensaje.',
                    settings.DEFAULT_FROM_EMAIL, [usuario.email], fail_silently=False)
                if enviados != 1: raise CorreoNoDisponible()
            except (SMTPException, OSError) as error:
                raise CorreoNoDisponible() from error
        return Response({'mensaje': 'Si existe una cuenta activa con ese correo, recibirás un enlace de recuperación.',
                         'modo_prueba': settings.EMAIL_BACKEND.endswith('console.EmailBackend')})

class RestablecerView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RecuperacionThrottle]
    def post(self, request):
        datos = ConfirmacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = datos.validated_data
        try:
            pk = int(force_str(urlsafe_base64_decode(campos['uid'])))
        except (ValueError, TypeError, UnicodeDecodeError, OverflowError):
            raise serializers.ValidationError('El enlace no es válido o ha caducado.')
        with transaction.atomic():
            usuario = Usuario.objects.select_for_update().filter(pk=pk, es_activo=True).first() if 0 < pk < 2**63 else None
            if not usuario or not default_token_generator.check_token(usuario, campos['token']):
                raise serializers.ValidationError('El enlace no es válido o ha caducado.')
            if campos['password'] != campos['password2']:
                raise serializers.ValidationError('Las contraseñas no coinciden.')
            try:
                validate_password(campos['password'], usuario)
            except DjangoValidationError as error:
                raise serializers.ValidationError(error.messages)
            usuario.set_password(campos['password'])
            usuario.save(update_fields=['password'])
        return Response({'mensaje': 'Contraseña actualizada. Inicia sesión y confirma tu código de correo.'})
