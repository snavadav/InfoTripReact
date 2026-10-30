"""Pruebas aisladas: no requieren ni modifican PostgreSQL local ni dependen del .env."""
from .base import *  # noqa: F403

SECRET_KEY = 'django-insecure-solo-para-pruebas'
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
# Las pruebas que provocan fallos (SMTP, bloqueos) no deben llenar la salida; assertLogs sigue funcionando.
LOGGING['loggers']['infotrip']['level'] = 'CRITICAL'  # noqa: F405
# El límite global no debe interferir entre pruebas; se prueba por separado en apps/core/tests.py.
REST_FRAMEWORK = {**REST_FRAMEWORK, 'DEFAULT_THROTTLE_CLASSES': ()}  # noqa: F405
