"""Pruebas contra PostgreSQL real (bloqueos, restricciones y concurrencia).

Usa las variables DB_* (Django crea y borra la base test_<DB_NAME>; el usuario necesita
permiso CREATEDB). Ejemplo: python manage.py test --settings=infotrip.settings.test_postgres
"""
from .test import *  # noqa: F403
from .base import DATABASES  # noqa: F401  PostgreSQL desde DB_*, en lugar de SQLite en memoria.
