from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class CorreoJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        usuario = super().get_user(validated_token)
        if not usuario.es_verificado or validated_token.get('correo_confirmado') is not True:
            raise AuthenticationFailed('Inicia sesión y confirma el código enviado a tu correo.')
        return usuario


