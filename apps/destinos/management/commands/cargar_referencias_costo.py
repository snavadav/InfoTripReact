"""Carga precios publicados por fuentes oficiales desde un CSV versionado. Guía: docs/referencias-costo.md

Cada fila cita su fuente y la fecha de consulta. Nunca se estima un precio: si no hay fuente, no hay fila.
Estos precios van aparte de los gastos de viajeros y no cuentan para su mediana ni para el mínimo de reportes.
Se puede repetir: actualiza la fila con la misma cita (destino, concepto, descripción y fuente) en vez de duplicarla.
"""
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.datos.models import PropuestaActualizacion
from apps.destinos.models import Destino, ReferenciaCosto

ARCHIVO = Path(__file__).resolve().parents[2] / 'datos' / 'referencias_costo.csv'
COLUMNAS = ['destino', 'concepto', 'monto', 'descripcion', 'fuente_nombre', 'fuente_url', 'fecha_consulta',
            'fecha_fuente']


def leer_fecha(texto, obligatoria):
    if not texto:
        if obligatoria:
            raise ValueError('falta la fecha')
        return None
    return date.fromisoformat(texto)


def referencia_de(fila, destinos):
    """ReferenciaCosto validada y sin guardar; ValueError si la fila no se puede cargar."""
    try:
        monto = Decimal(fila['monto'])
    except InvalidOperation:
        raise ValueError(f"monto inválido: {fila['monto']!r}") from None
    fecha_consulta = leer_fecha(fila['fecha_consulta'], obligatoria=True)
    if fecha_consulta > timezone.localdate():
        raise ValueError('la fecha de consulta está en el futuro')
    referencia = ReferenciaCosto(
        destino=destinos[fila['destino']], concepto=fila['concepto'], monto=monto, descripcion=fila['descripcion'],
        fuente_nombre=fila['fuente_nombre'], fuente_url=fila['fuente_url'], fecha_consulta=fecha_consulta,
        fecha_fuente=leer_fecha(fila['fecha_fuente'], obligatoria=False),
    )
    if not referencia.fuente_url.startswith('https://'):
        raise ValueError('la fuente debe ser una dirección https')
    try:
        referencia.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError as error:
        raise ValueError('; '.join(f'{campo}: {" ".join(mensajes)}'
                                   for campo, mensajes in error.message_dict.items())) from None
    return referencia


class Command(BaseCommand):
    help = 'Carga precios de fuentes oficiales, con su cita, desde un CSV. No toca los gastos de viajeros.'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', default=str(ARCHIVO), help='CSV de referencias.')

    def handle(self, *args, **opciones):
        try:
            with open(opciones['archivo'], encoding='utf-8', newline='') as entrada:
                lector = csv.DictReader(entrada)
                if lector.fieldnames != COLUMNAS:
                    raise CommandError(f'Columnas esperadas: {",".join(COLUMNAS)}')
                filas = list(lector)
        except OSError as error:
            raise CommandError(f'No se pudo leer {opciones["archivo"]}: {error}') from None

        destinos = Destino.objects.in_bulk({fila['destino'] for fila in filas}, field_name='slug')
        referencias, errores, sin_destino = [], [], set()
        for numero, fila in enumerate(filas, start=2):
            if fila['destino'] not in destinos:
                sin_destino.add(fila['destino'])
                continue
            try:
                referencias.append(referencia_de(fila, destinos))
            except ValueError as error:
                errores.append(f'Línea {numero}: {error}')
        if errores:
            raise CommandError('No se cargó nada. ' + ' | '.join(errores))

        creadas = actualizadas = conservadas = 0
        with transaction.atomic():
            for referencia in referencias:
                # Un precio aprobado después desde su fuente oficial (apps.datos) es más reciente que el CSV.
                if PropuestaActualizacion.objects.filter(
                        estado='aprobada', fuente__referencia__destino=referencia.destino,
                        fuente__referencia__concepto=referencia.concepto,
                        fuente__referencia__descripcion=referencia.descripcion,
                        fuente__referencia__fuente_url=referencia.fuente_url,
                        fecha_consulta__gt=referencia.fecha_consulta).exists():
                    conservadas += 1
                    continue
                _, creada = ReferenciaCosto.objects.update_or_create(
                    destino=referencia.destino, concepto=referencia.concepto, descripcion=referencia.descripcion,
                    fuente_url=referencia.fuente_url,
                    defaults={'monto': referencia.monto, 'fuente_nombre': referencia.fuente_nombre,
                              'fecha_consulta': referencia.fecha_consulta, 'fecha_fuente': referencia.fecha_fuente},
                )
                creadas += creada
                actualizadas += not creada
        if sin_destino:
            self.stdout.write(self.style.WARNING(
                f'Se omitieron destinos que no existen en esta base: {", ".join(sorted(sin_destino))}'))
        mensaje = f'{creadas} referencias creadas y {actualizadas} actualizadas.'
        if conservadas:
            mensaje += f' {conservadas} conservadas: se aprobó un precio más reciente desde su fuente oficial.'
        self.stdout.write(self.style.SUCCESS(mensaje))
