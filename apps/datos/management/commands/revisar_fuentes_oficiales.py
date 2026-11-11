"""Revisa los sitios oficiales que toca y crea propuestas para la cola de moderación. Guía: docs/actualizacion-datos.md

Respeta robots.txt, descarga con poca frecuencia y solo llama a la IA si la página cambió. Nunca publica: una persona
aprueba cada propuesta en /admin/moderacion/. Requiere ANTHROPIC_API_KEY; sin ella, no hace nada.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.datos.lector import PAUSA_SEGUNDOS, pendientes_de_revisar, revisar_fuentes
from apps.datos.models import FuenteOficial


class Command(BaseCommand):
    help = 'Lee los sitios oficiales (precios y horarios) y propone cambios para aprobar. No publica nada.'

    def add_arguments(self, parser):
        parser.add_argument('--fuente', type=int, action='append', help='Revisa solo esta fuente (id).')
        parser.add_argument('--pausa', type=float, default=PAUSA_SEGUNDOS, help='Segundos entre descargas.')

    def handle(self, *args, fuente, pausa, **opciones):
        if not settings.ANTHROPIC_API_KEY:
            self.stdout.write(self.style.WARNING('Falta ANTHROPIC_API_KEY: no se revisó ninguna fuente.'))
            return
        fuentes = (list(FuenteOficial.objects.filter(pk__in=fuente, activo=True)
                        .select_related('destino', 'lugar', 'referencia')) if fuente else pendientes_de_revisar())
        conteos = revisar_fuentes(fuentes, pausa=pausa)
        self.stdout.write(self.style.SUCCESS(', '.join(f'{clave}: {valor}' for clave, valor in conteos.items())))
