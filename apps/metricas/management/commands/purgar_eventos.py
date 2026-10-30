"""Borra los eventos de más de 13 meses: bastan para comparar con el año anterior."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.metricas.models import Evento


class Command(BaseCommand):
    help = 'Borra los eventos de uso de más de 13 meses.'

    def handle(self, *args, **opciones):
        borrados, _ = Evento.objects.filter(creado__lt=timezone.now() - timedelta(days=395)).delete()
        self.stdout.write(f'{borrados} eventos borrados.')
