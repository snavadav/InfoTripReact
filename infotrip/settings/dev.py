"""Desarrollo con PostgreSQL local. No usar para producción."""
from .base import *  # noqa: F403
from .base import config

DEBUG = config('DEBUG', default=True, cast=bool)
SECRET_KEY = SECRET_KEY or 'django-insecure-solo-para-desarrollo-local'  # noqa: F405
ALLOWED_HOSTS = ALLOWED_HOSTS or ['localhost', '127.0.0.1', '[::1]']  # noqa: F405
