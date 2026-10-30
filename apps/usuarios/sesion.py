"""Sesión del navegador: el refresh token vive en una cookie que JavaScript no puede leer.

Así, un XSS no puede llevarse la sesión. El access token no se guarda: el navegador lo pide al
cargar cada página privada y lo conserva solo en memoria. Como el navegador envía la cookie solo,
las rutas que la usan exigen además el token CSRF de Django.
"""
from django.conf import settings
from django.middleware.csrf import get_token
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied

COOKIE_REFRESH = 'infotrip_refresh'
# La cookie solo viaja a las rutas de autenticación, no en cada petición del sitio.
RUTA_COOKIE = '/api/v1/auth/'


def guardar_cookie_refresh(request, respuesta, refresh):
    respuesta.set_cookie(
        COOKIE_REFRESH, str(refresh),
        max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        path=RUTA_COOKIE, httponly=True, secure=settings.REFRESH_COOKIE_SECURE, samesite='Strict',
    )
    # Asegura la cookie csrftoken que el navegador debe devolver al refrescar y al cerrar sesión.
    get_token(request._request)


def borrar_cookie_refresh(respuesta):
    respuesta.delete_cookie(COOKIE_REFRESH, path=RUTA_COOKIE, samesite='Strict')


def exigir_csrf(request):
    """Mismo chequeo que SessionAuthentication de DRF; las vistas de la API están exentas por defecto."""
    comprobador = CSRFCheck(lambda _: None)
    comprobador.process_request(request._request)
    motivo = comprobador.process_view(request._request, None, (), {})
    if motivo:
        raise PermissionDenied(f'Verificación CSRF fallida: {motivo}')
