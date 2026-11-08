"""Califica todos los lugares con el modelo guardado por `entrenar_curador`.

    python manage.py aplicar_curador

No oculta ni publica nada: guarda la probabilidad de que cada lugar le sirva a un viajero, para que el equipo
revise primero los más dudosos o los que probablemente no sirven.
"""
from pathlib import Path

import joblib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.curador.caracteristicas import _coordenadas_de_destinos, fila
from apps.curador.models import PrediccionLugar
from apps.curador.modelo import probabilidad_de_servir
from apps.destinos.models import Lugar

LOTE = 2000


class Command(BaseCommand):
    help = 'Guarda la probabilidad de que cada lugar le sirva a un viajero, según el modelo entrenado.'

    def add_arguments(self, parser):
        parser.add_argument('--modelo', default=str(settings.CURADOR_MODELO))

    def handle(self, *args, modelo, **opciones):
        ruta = Path(modelo)
        if not ruta.exists():
            raise CommandError(f'No existe {ruta}. Primero corre: python manage.py entrenar_curador')
        guardado = joblib.load(ruta)
        destinos = _coordenadas_de_destinos()
        lugares = Lugar.objects.select_related('municipio').order_by('pk')
        total = probables_no = 0
        for inicio in range(0, lugares.count(), LOTE):
            lote = list(lugares[inicio:inicio + LOTE])
            probabilidades = probabilidad_de_servir(guardado['modelo'], [fila(lugar, destinos) for lugar in lote])
            PrediccionLugar.objects.bulk_create(
                [PrediccionLugar(lugar=lugar, probabilidad=float(p), version=guardado['version'])
                 for lugar, p in zip(lote, probabilidades)],
                update_conflicts=True, unique_fields=['lugar'],
                update_fields=['probabilidad', 'version', 'actualizado'])
            total += len(lote)
            probables_no += sum(1 for lugar, p in zip(lote, probabilidades) if p < 0.5 and lugar.es_activo)
        self.stdout.write(self.style.SUCCESS(
            f'{total} lugares calificados con el modelo de {guardado["etiquetas"]} etiquetas. '
            f'{probables_no} lugares visibles probablemente no le sirven a un viajero: revísalos en '
            '/admin/curador/prediccionlugar/.'))
