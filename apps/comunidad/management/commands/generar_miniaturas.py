"""Crea la miniatura de las fotos subidas antes de que existiera este campo. Se puede repetir sin riesgo."""
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.comunidad.models import Aporte
from apps.core.imagenes import miniatura_de


class Command(BaseCommand):
    help = 'Crea las miniaturas que falten de las fotos de los aportes.'

    def handle(self, *args, **opciones):
        creadas = fallidas = 0
        for aporte in Aporte.objects.exclude(imagen='').filter(miniatura=''):
            try:
                with aporte.imagen.open('rb') as archivo:
                    original = ContentFile(archivo.read())
                aporte.miniatura = miniatura_de(original)
                aporte.save(update_fields=['miniatura'])
                creadas += 1
            except OSError as error:
                self.stderr.write(f'Aporte {aporte.pk}: {error}')
                fallidas += 1
        self.stdout.write(f'{creadas} miniaturas creadas, {fallidas} con error.')
