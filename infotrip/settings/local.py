"""Desarrollo local sin PostgreSQL. No usar para producción."""
from .dev import *  # noqa: F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}  # noqa: F405
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
