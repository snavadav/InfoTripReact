"""Mide y entrena el curador con las etiquetas del equipo.

    python manage.py entrenar_curador --reporte docs/experimentos/curador.csv

Primero compara, con validación cruzada de 5 pliegues, la regla actual (todo lo importado sirve), el modelo sin
el nombre y el modelo completo. Después entrena el modelo completo con todas las etiquetas y lo guarda.
"""
import csv
import math
from pathlib import Path

import joblib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.curador.caracteristicas import acuerdo_entre_personas, filas, lugares_etiquetados
from apps.curador.modelo import VERSION, entrenar, evaluar

MINIMO = 200
MINIMO_POR_CLASE = 20


class Command(BaseCommand):
    help = 'Compara el curador con la regla actual y lo entrena con las etiquetas del equipo.'

    def add_arguments(self, parser):
        parser.add_argument('--modelo', default=str(settings.CURADOR_MODELO), help='Dónde guardar el modelo.')
        parser.add_argument('--reporte', help='CSV con las medidas de cada método.')
        parser.add_argument('--minimo', type=int, default=MINIMO, help='Etiquetas mínimas para entrenar.')
        parser.add_argument('--solo-medir', action='store_true', help='No guarda el modelo.')

    def handle(self, *args, modelo, reporte, minimo, solo_medir, **opciones):
        lugares, etiquetas = lugares_etiquetados()
        sirven = sum(etiquetas)
        no_sirven = len(etiquetas) - sirven
        self.stdout.write(f'Etiquetas: {len(etiquetas)} lugares ({sirven} sirven, {no_sirven} no sirven).')
        if len(etiquetas) < minimo or min(sirven, no_sirven) < MINIMO_POR_CLASE:
            raise CommandError(f'Faltan etiquetas: se necesitan al menos {minimo} lugares y {MINIMO_POR_CLASE} de '
                               'cada respuesta. Etiqueten más en /admin/etiquetar-lugares/.')
        acuerdo = acuerdo_entre_personas()
        if acuerdo:
            n, observado, kappa = acuerdo
            self.stdout.write(f'Acuerdo entre personas: {observado:.0%} en {n} lugares (kappa = {kappa:.2f}).')
        else:
            self.stdout.write('Acuerdo entre personas: aún no hay 20 lugares etiquetados por dos personas.')
        datos = filas(lugares)
        resultados = evaluar(datos, etiquetas)
        self.stdout.write(f'\n{"método":<20}{"exactitud":>10}{"precisión":>11}{"exhaust.":>10}{"F1":>7}{"AUC":>7}')
        for metodo, m in resultados.items():
            auc = '—' if math.isnan(m['auc']) else f'{m["auc"]:.3f}'
            self.stdout.write(f'{metodo:<20}{m["exactitud"]:>10.3f}{m["precision_no_sirve"]:>11.3f}'
                              f'{m["exhaustividad_no_sirve"]:>10.3f}{m["f1_no_sirve"]:>7.3f}{auc:>7}')
        self.stdout.write('Precisión, exhaustividad y F1 se miden sobre los lugares que NO sirven.')
        if reporte:
            with open(reporte, 'w', newline='', encoding='utf-8') as archivo:
                escritor = csv.DictWriter(archivo, fieldnames=['metodo', *next(iter(resultados.values()))])
                escritor.writeheader()
                for metodo, m in resultados.items():
                    escritor.writerow({'metodo': metodo, **m})
            self.stdout.write(f'Reporte: {reporte}')
        if solo_medir:
            return
        ruta = Path(modelo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({'modelo': entrenar(datos, etiquetas), 'version': VERSION, 'etiquetas': len(etiquetas),
                     'entrenado': timezone.now().isoformat(), 'medidas': resultados['modelo_completo']}, ruta)
        self.stdout.write(self.style.SUCCESS(f'Modelo guardado en {ruta}.'))
