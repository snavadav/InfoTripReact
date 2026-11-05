"""Aplica la curación del catálogo: oculta destinos importados que no sirven a un viajero, corrige nombres y une
categorías repetidas. Usa identificadores de OpenStreetMap, no de la base, para que dé lo mismo en cualquier
instalación. Nada se borra: `--revertir` vuelve a publicar lo ocultado. Guía: docs/mvp.md
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.destinos.models import Categoria, Destino

ARCHIVO = Path(__file__).resolve().parents[2] / 'datos' / 'curacion.json'


class Command(BaseCommand):
    help = 'Oculta destinos importados de poco valor, corrige nombres y une categorías repetidas.'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', default=str(ARCHIVO))
        parser.add_argument('--simular', action='store_true', help='Muestra qué haría sin guardar nada.')
        parser.add_argument('--revertir', action='store_true', help='Vuelve a publicar los destinos de la lista.')

    def handle(self, *args, archivo, simular, revertir, **opciones):
        try:
            curacion = json.loads(Path(archivo).read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise CommandError(f'No se pudo leer {archivo}: {error}') from error
        ocultar = [fila['osm_id'] for fila in curacion['ocultar']]
        with transaction.atomic():
            listados = Destino.objects.filter(osm_id__in=ocultar)
            if revertir:
                cambiados = listados.filter(es_activo=False).update(es_activo=True)
                self.stdout.write(self.style.SUCCESS(f'Publicados de nuevo: {cambiados}.'))
            else:
                cambiados = listados.filter(es_activo=True).update(es_activo=False)
                renombrados = 0
                for osm_id, nombre in curacion['renombrar'].items():
                    # El slug no cambia: los enlaces que ya se compartieron siguen funcionando.
                    renombrados += Destino.objects.filter(osm_id=osm_id).exclude(nombre=nombre).update(nombre=nombre)
                unidos = self.unir_categorias(curacion['unir_categorias'])
                self.stdout.write(self.style.SUCCESS(
                    f'{"Se ocultarían" if simular else "Ocultados"}: {cambiados}. Renombrados: {renombrados}. '
                    f'Destinos movidos de categoría: {unidos}. En la lista pero no en esta base: '
                    f'{len(ocultar) - listados.count()}.'))
            if simular:
                transaction.set_rollback(True)

    def unir_categorias(self, uniones):
        movidos = 0
        for origen, destino in uniones.items():
            vieja = Categoria.objects.filter(nombre=origen).first()
            if not vieja:
                continue
            nueva, _ = Categoria.objects.get_or_create(nombre=destino, defaults={'slug': destino.lower()})
            for lugar in vieja.destinos.all():
                lugar.categorias.add(nueva)
                lugar.categorias.remove(vieja)
                movidos += 1
        return movidos
