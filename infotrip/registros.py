"""Filtros del registro (LOGGING en settings/base.py)."""
import logging
import re

CONSULTA = re.compile(r'\?\S*')


class SinConsulta(logging.Filter):
    """Quita la cadena de consulta de las líneas de acceso de `runserver` (logger django.server).

    Ahí van búsquedas de direcciones (`?q=`), coordenadas (`?lat=&lon=`) y enlaces con token (`?t=`).
    En producción gunicorn y nginx ya las omiten (gunicorn.conf.py, docker/nginx*.conf).
    """

    def filter(self, registro):
        if registro.args and isinstance(registro.args, tuple) and isinstance(registro.args[0], str):
            registro.args = (CONSULTA.sub('', registro.args[0]), *registro.args[1:])
        return True
