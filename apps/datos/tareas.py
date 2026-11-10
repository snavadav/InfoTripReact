"""Tareas programadas que mantienen los datos al día. Las corre el servicio `tareas` de docker-compose.yml.

Calendario: DENUE cada mes, OpenStreetMap y sitios oficiales cada semana. Cada corrida queda en EjecucionTarea.
Si falta una clave, la tarea se salta con un aviso (no falla) y se vuelve a intentar al día siguiente.
"""
import logging
from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from .models import EjecucionTarea

logger = logging.getLogger('infotrip.datos')

PERIODOS = {'denue': timedelta(days=30), 'osm': timedelta(days=7), 'fuentes_oficiales': timedelta(days=7)}
# Tras un error o una tarea saltada (falta una clave) no se espera el periodo completo.
REINTENTO = timedelta(days=1)


class TareaSaltada(Exception):
    """Falta una clave o algo que la tarea necesita: se registra como saltada, no como error."""


def _importar(comando):
    salida = StringIO()
    call_command(comando, marcar_ausentes=True, stdout=salida, stderr=salida)
    return comando.conteos


def denue():
    if not settings.DENUE_TOKEN:
        raise TareaSaltada('Falta DENUE_TOKEN: no se consultó el DENUE.')
    from apps.destinos.management.commands.importar_denue import Command
    return _importar(Command())


def osm():
    from apps.destinos.management.commands.importar_lugares import Command
    return _importar(Command())


def fuentes_oficiales():
    if not settings.ANTHROPIC_API_KEY:
        raise TareaSaltada('Falta ANTHROPIC_API_KEY: no se revisaron los sitios oficiales.')
    from .lector import revisar_fuentes
    return revisar_fuentes()


TAREAS = {'denue': denue, 'osm': osm, 'fuentes_oficiales': fuentes_oficiales}


def programadas():
    """Nombres válidos de TAREAS_PROGRAMADAS, en orden. Los desconocidos se avisan y se ignoran."""
    nombres = [nombre.strip() for nombre in settings.TAREAS_PROGRAMADAS.split(',') if nombre.strip()]
    for nombre in nombres:
        if nombre not in TAREAS:
            logger.warning('Tarea desconocida en TAREAS_PROGRAMADAS: %s', nombre)
    return [nombre for nombre in nombres if nombre in TAREAS]


def toca(tarea, ahora=None):
    ahora = ahora or timezone.now()
    ultima = EjecucionTarea.objects.filter(tarea=tarea).exclude(resultado='en_curso').first()
    if ultima is None:
        return True
    espera = PERIODOS[tarea] if ultima.resultado == 'exito' else REINTENTO
    return ahora - ultima.inicio >= espera


def ejecutar(tarea):
    """Corre una tarea y deja su registro. Nunca lanza: el resultado queda en la EjecucionTarea."""
    registro = EjecucionTarea.objects.create(tarea=tarea)
    try:
        registro.conteos = TAREAS[tarea]() or {}
        registro.resultado = 'exito'
    except TareaSaltada as aviso:
        registro.resultado, registro.mensaje = 'saltada', str(aviso)
    except Exception as error:  # Se registra y la siguiente tarea sigue. Los mensajes de error no llevan claves.
        logger.warning('La tarea %s falló: %s', tarea, type(error).__name__)
        registro.resultado, registro.mensaje = 'error', f'{type(error).__name__}: {error}'[:2000]
    registro.fin = timezone.now()
    registro.save(update_fields=['conteos', 'resultado', 'mensaje', 'fin'])
    return registro
