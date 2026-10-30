from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class CorreoJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        usuario = super().get_user(validated_token)
        if not usuario.es_verificado or validated_token.get('correo_confirmado') is not True:
            raise AuthenticationFailed('Inicia sesión y confirma el código enviado a tu correo.')
        return usuario




class CorreoJWTEsquema(OpenApiAuthenticationExtension):
    """Documenta la autenticación en OpenAPI: token Bearer de la verificación por correo."""
    target_class = CorreoJWTAuthentication
    name = 'jwt'

    def get_security_definition(self, auto_schema):
        return {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'}
