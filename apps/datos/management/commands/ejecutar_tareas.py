"""Corre las tareas programadas que tocan (o una con --tarea). Guía: docs/actualizacion-datos.md

El servicio `tareas` lo llama cada hora: el calendario (DENUE mensual, OSM y sitios oficiales semanales) sale del
registro de EjecucionTarea, así que reiniciar el contenedor no repite ni salta corridas.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.datos.tareas import TAREAS, ejecutar, programadas, toca


class Command(BaseCommand):
    help = 'Corre las tareas de actualización de datos que tocan según su calendario.'

    def add_arguments(self, parser):
        parser.add_argument('--tarea', choices=sorted(TAREAS), help='Corre solo esta tarea, aunque no le toque.')

    def handle(self, *args, tarea, **opciones):
        nombres = [tarea] if tarea else [nombre for nombre in programadas() if toca(nombre)]
        if not nombres:
            self.stdout.write('Ninguna tarea pendiente.')
        for nombre in nombres:
            registro = ejecutar(nombre)
            linea = f'{nombre}: {registro.get_resultado_display().lower()}'
            if registro.mensaje:
                linea += f' · {registro.mensaje}'
            if registro.conteos:
                linea += ' · ' + ', '.join(f'{clave} {valor}' for clave, valor in registro.conteos.items())
            estilo = {'exito': self.style.SUCCESS, 'saltada': self.style.WARNING}.get(registro.resultado,
                                                                                       self.style.ERROR)
            self.stdout.write(estilo(linea))
            if tarea and registro.resultado == 'error':
                raise CommandError(f'La tarea {nombre} falló.')
