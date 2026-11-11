"""Registra como fuentes oficiales las páginas que ya cita referencias_costo.csv. Se puede repetir sin duplicar.

Cada fila del CSV con su ReferenciaCosto cargada se vuelve una FuenteOficial de precio. Los PDF quedan inactivos:
el lector solo entiende páginas HTML o texto, así que se revisan a mano.
"""
import csv

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.datos.models import FuenteOficial, validar_url_oficial
from apps.destinos.management.commands.cargar_referencias_costo import ARCHIVO
from apps.destinos.models import ReferenciaCosto


class Command(BaseCommand):
    help = 'Crea las fuentes oficiales de precios a partir de las referencias de costo ya cargadas.'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', default=str(ARCHIVO), help='CSV de referencias.')

    def handle(self, *args, archivo, **opciones):
        try:
            with open(archivo, encoding='utf-8', newline='') as entrada:
                filas = list(csv.DictReader(entrada))
        except OSError as error:
            raise CommandError(f'No se pudo leer {archivo}: {error}') from None
        creadas = existentes = sin_referencia = rechazadas = 0
        for fila in filas:
            try:
                validar_url_oficial(fila['fuente_url'])
            except ValidationError:
                rechazadas += 1
                continue
            referencia = ReferenciaCosto.objects.filter(
                destino__slug=fila['destino'], concepto=fila['concepto'], descripcion=fila['descripcion'],
                fuente_url=fila['fuente_url']).first()
            if referencia is None:
                sin_referencia += 1
                continue
            es_pdf = fila['fuente_url'].lower().split('?')[0].endswith('.pdf')
            _, creada = FuenteOficial.objects.get_or_create(
                url=fila['fuente_url'], referencia=referencia,
                defaults={'nombre': fila['fuente_nombre'][:200], 'tipo_dato': 'precio', 'destino': referencia.destino,
                          'activo': not es_pdf, 'nota': 'PDF: se revisa a mano.' if es_pdf else ''},
            )
            creadas += creada
            existentes += not creada
        self.stdout.write(self.style.SUCCESS(
            f'{creadas} fuentes creadas, {existentes} ya existían. Sin referencia cargada: {sin_referencia}. '
            f'Rechazadas por dominio: {rechazadas}.'))
