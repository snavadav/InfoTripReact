"""Sesión del navegador: el refresh token vive en una cookie que JavaScript no puede leer.

Así, un XSS no puede llevarse la sesión. El access token no se guarda: el navegador lo pide al
cargar cada página privada y lo conserva solo en memoria. Como el navegador envía la cookie solo,
las rutas que la usan exigen además el token CSRF de Django.
"""
from django.conf import settings
from django.core import signing
from django.middleware.csrf import get_token
from django.utils.crypto import constant_time_compare
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


# ─── Dispositivo recordado ────────────────────────────────────
# Opcional: la contraseña se sigue pidiendo, pero no el código de correo. La cookie va firmada y
# ligada a la contraseña y al correo: cambiar cualquiera de los dos la invalida.
COOKIE_DISPOSITIVO = 'infotrip_dispositivo'
DIAS_DISPOSITIVO = 30
SAL_DISPOSITIVO = 'infotrip.dispositivo'


def guardar_cookie_dispositivo(respuesta, usuario, huella):
    valor = signing.dumps({'u': usuario.pk, 'h': huella, 'e': usuario.email}, salt=SAL_DISPOSITIVO)
    respuesta.set_cookie(
        COOKIE_DISPOSITIVO, valor, max_age=DIAS_DISPOSITIVO * 24 * 3600,
        path=RUTA_COOKIE, httponly=True, secure=settings.REFRESH_COOKIE_SECURE, samesite='Strict',
    )


def dispositivo_recordado(request, usuario, huella):
    valor = request.COOKIES.get(COOKIE_DISPOSITIVO)
    if not valor or not usuario.es_verificado:
        return False
    try:
        datos = signing.loads(valor, salt=SAL_DISPOSITIVO, max_age=DIAS_DISPOSITIVO * 24 * 3600)
    except signing.BadSignature:
        return False
    return (datos.get('u') == usuario.pk and datos.get('e') == usuario.email
            and constant_time_compare(datos.get('h', ''), huella))
