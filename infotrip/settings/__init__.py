"""
Configuración por entorno. Selecciona el módulo con DJANGO_SETTINGS_MODULE o --settings:

- infotrip.settings.dev    desarrollo con PostgreSQL (predeterminado de manage.py)
- infotrip.settings.local  desarrollo con SQLite, sin PostgreSQL
- infotrip.settings.test   pruebas aisladas
- infotrip.settings.prod   producción (predeterminado de wsgi.py y asgi.py)
"""
