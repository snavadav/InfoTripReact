"""Producción: falla al arrancar si falta configuración crítica en lugar de usar valores inseguros."""
import sentry_sdk
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import config

DEBUG = False

if len(SECRET_KEY) < 50 or SECRET_KEY.startswith('django-insecure'):  # noqa: F405
    raise ImproperlyConfigured(
        'Define SECRET_KEY con al menos 50 caracteres aleatorios. Genera una con: '
        'python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
    )
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured('Define ALLOWED_HOSTS con los dominios públicos, separados por comas.')
if not REDIS_URL:  # noqa: F405
    raise ImproperlyConfigured(
        'Define REDIS_URL (por ejemplo redis://localhost:6379/0): con varios procesos, una caché '
        'local por proceso multiplica los límites de intentos de login.'
    )

# ─── MONITOREO DE ERRORES (opcional; compatible con Sentry y GlitchTip) ────
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, send_default_pii=False, traces_sample_rate=0)

# ─── ARCHIVOS ESTÁTICOS ───────────────────────────────────────
# WhiteNoise con nombres con hash y compresión: caché de larga duración sin servir versiones viejas.
# Requiere `collectstatic` (lo hace el Dockerfile al construir la imagen).
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

# ─── HTTPS ────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
# El chequeo de salud de Docker o del balanceador llega por HTTP desde dentro de la red.
SECURE_REDIRECT_EXEMPT = [r'^health/$']
# Solo si un proxy de confianza termina TLS y fija X-Forwarded-Proto (por ejemplo nginx).
if config('DETRAS_DE_PROXY_HTTPS', default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS: los navegadores recordarán usar solo HTTPS durante este tiempo. Empieza con un valor
# bajo (3600) al publicar por primera vez y súbelo a un año cuando todo funcione por HTTPS.
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True, cast=bool)
# La cabecera 'preload' no tiene efecto hasta registrar el dominio en hstspreload.org.
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=True, cast=bool)

# ─── COOKIES Y CABECERAS ──────────────────────────────────────
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
REFRESH_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
