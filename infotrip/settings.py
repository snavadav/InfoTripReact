"""
InfoTrip — settings.py
Configuración principal del proyecto Django
"""

from pathlib import Path
from decouple import config
from datetime import timedelta

# ─── RUTAS BASE ───────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ─── SEGURIDAD ────────────────────────────────────────────────
SECRET_KEY = config('SECRET_KEY', default='django-insecure-cambia-esto-en-produccion')
DEBUG      = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

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

    # InfoTrip apps
    'apps.usuarios',
    'apps.destinos',
    'apps.comunidad',
]

# ─── MIDDLEWARE ───────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
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
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.usuarios.authentication.CorreoJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

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
