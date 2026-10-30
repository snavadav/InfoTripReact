"""
InfoTrip — settings/base.py
Configuración común. No se usa directamente: elige dev, local, test o prod.
"""

from pathlib import Path
from decouple import Csv, config
from datetime import timedelta
from django.utils.csp import CSP

# ─── RUTAS BASE ───────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ─── SEGURIDAD ────────────────────────────────────────────────
# Sin valores inseguros por defecto: cada entorno decide qué hacer si faltan.
SECRET_KEY = config('SECRET_KEY', default='')
DEBUG      = False
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='', cast=Csv())

# Content Security Policy (S6): solo se ejecutan scripts de archivos propios y de Leaflet en
# unpkg, así que un XSS no puede inyectar <script> en línea ni cargar código de otros dominios.
# Los estilos admiten 'unsafe-inline' porque las plantillas usan bloques <style> y style="".
SECURE_CSP = {
    'default-src': [CSP.SELF],
    'script-src': [CSP.SELF, 'https://unpkg.com'],
    'style-src': [CSP.SELF, CSP.UNSAFE_INLINE, 'https://fonts.googleapis.com', 'https://unpkg.com'],
    'font-src': [CSP.SELF, 'https://fonts.gstatic.com'],
    'img-src': [CSP.SELF, 'data:', 'https://tile.openstreetmap.org', 'https://unpkg.com'],
    # unpkg: las herramientas de desarrollo del navegador descargan el source map de Leaflet.
    'connect-src': [CSP.SELF, 'https://unpkg.com'],
    'object-src': [CSP.NONE],
    'base-uri': [CSP.SELF],
    'form-action': [CSP.SELF],
    'frame-ancestors': [CSP.NONE],
}

# ─── APLICACIONES ─────────────────────────────────────────────
INSTALLED_APPS = [
    # Django
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Terceros
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'drf_spectacular_sidecar',

    # InfoTrip apps
    'apps.usuarios',
    'apps.destinos',
    'apps.comunidad',
]

# ─── MIDDLEWARE ───────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Sirve /static/ desde gunicorn en producción (los archivos de usuarios, /media/, los sirve nginx).
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.csp.ContentSecurityPolicyMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'infotrip.urls'

# ─── TEMPLATES ────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'infotrip.wsgi.application'

# ─── BASE DE DATOS ────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     config('DB_NAME',     default='infotrip'),
        'USER':     config('DB_USER',     default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST':     config('DB_HOST',     default='localhost'),
        'PORT':     config('DB_PORT',     default='5432'),
    }
}

# ─── MODELO DE USUARIO PERSONALIZADO ─────────────────────────
AUTH_USER_MODEL = 'usuarios.Usuario'

# ─── VALIDACIÓN DE CONTRASEÑAS ───────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── DJANGO REST FRAMEWORK ───────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'API de InfoTrip',
    'DESCRIPTION': 'Información turística de Jalisco verificada por la comunidad.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    # Swagger UI desde archivos propios: la CSP no permite cargarlo de un CDN.
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
}

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.usuarios.authentication.CorreoJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # Proxies inversos de confianza delante de Django. Con 0 se ignora X-Forwarded-For
    # y los límites usan REMOTE_ADDR; detrás de nginx/balanceador usar 1.
    'NUM_PROXIES': config('NUM_PROXIES', default=0, cast=int),
}

# ─── CACHÉ ────────────────────────────────────────────────────
# Los límites de intentos (throttles y bloqueo por cuenta) viven en la caché: con varios
# procesos debe ser compartida (Redis). LocMem solo sirve con un único proceso.
def configurar_cache(redis_url):
    if redis_url:
        return {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': redis_url}}
    return {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'infotrip'}}


REDIS_URL = config('REDIS_URL', default='')
CACHES = configurar_cache(REDIS_URL)

# ─── JWT ──────────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'CHECK_REVOKE_TOKEN': True,
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ─── INTERNACIONALIZACIÓN ─────────────────────────────────────
LANGUAGE_CODE = 'es-mx'
TIME_ZONE     = 'America/Mexico_City'
USE_I18N      = True
USE_TZ        = True

# ─── ARCHIVOS ESTÁTICOS ───────────────────────────────────────
STATIC_URL  = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ─── ARCHIVOS MEDIA (fotos subidas por usuarios) ─────────────
MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ─── PRIMARY KEY DEFAULT ─────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Correo: SMTP real por defecto. Sin host, el login informa que no puede enviar.
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='InfoTrip <no-reply@localhost>')

PUBLIC_BASE_URL = config('PUBLIC_BASE_URL', default='http://127.0.0.1:8000').rstrip('/')
PASSWORD_RESET_TIMEOUT = 3600

# ─── REGISTRO (LOGGING) ───────────────────────────────────────
# Todo va a la salida estándar (12-factor): Docker, systemd o la plataforma lo recogen.
# Los registros de InfoTrip nunca incluyen correos ni contraseñas: solo ids o huellas.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'simple': {'format': '{asctime} {levelname} {name}: {message}', 'style': '{'}},
    'handlers': {'consola': {'class': 'logging.StreamHandler', 'formatter': 'simple'}},
    'root': {'handlers': ['consola'], 'level': 'WARNING'},
    'loggers': {
        # infotrip.correo, infotrip.moderacion, infotrip.seguridad…
        'infotrip': {'handlers': ['consola'], 'level': config('LOG_LEVEL', default='INFO'), 'propagate': False},
    },
}
