"""Importa negocios del DENUE (INEGI) que le sirven a quien viaja. Requiere DENUE_TOKEN en .env.

Se publican de inmediato. Lo que ya existe de OpenStreetMap o de la comunidad no se duplica, y lo editado en el
admin no se toca. Guía: docs/importar-osm.md
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.geo import distancia_km
from apps.core.texto import se_parecen
from apps.destinos.denue import ErrorDenue, descargar, interpretar
from apps.destinos.ausentes import marcar_ausentes as marcar_ausentes_de
from apps.destinos.models import Lugar, TIPO_DE_SUBTIPO
from .importar_osm import municipio_de

CAMPOS = ['nombre', 'tipo', 'subtipo', 'latitud', 'longitud', 'direccion', 'telefono', 'sitio_web', 'municipio',
          'posiblemente_cerrado', 'ausente_desde']
TANDA = 1000
METROS_DE_DUPLICADO = 100
# Celdas de unos 110 m: basta comparar con la propia y sus vecinas, no con decenas de miles de lugares.
GRADOS_POR_CELDA = 0.001


def celda(latitud, longitud):
    return int(float(latitud) // GRADOS_POR_CELDA), int(float(longitud) // GRADOS_POR_CELDA)


class Rejilla:
    def __init__(self):
        self.celdas = {}

    def agregar(self, nombre, latitud, longitud):
        self.celdas.setdefault(celda(latitud, longitud), []).append((nombre, float(latitud), float(longitud)))

    def hay_parecido(self, nombre, latitud, longitud):
        x, y = celda(latitud, longitud)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for otro, lat, lng in self.celdas.get((x + dx, y + dy), []):
                    cerca = distancia_km(latitud, longitud, lat, lng) * 1000 <= METROS_DE_DUPLICADO
                    if cerca and se_parecen(nombre, otro):
                        return True
        return False


class Command(BaseCommand):
    help = 'Importa negocios útiles para viajar desde el DENUE del INEGI. Se publican de inmediato.'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', help='Usa una descarga ya guardada en lugar de consultar el DENUE.')
        parser.add_argument('--guardar', help='Guarda la descarga en este archivo. No contiene la clave.')
        parser.add_argument('--simular', action='store_true', help='Muestra qué haría sin guardar nada.')
        parser.add_argument('--retirar-ausentes', action='store_true',
                            help='Oculta lo importado antes que ya no aparece en el DENUE.')
        parser.add_argument('--marcar-ausentes', action='store_true',
                            help='Marca como posiblemente cerrado lo que ya no aparece en el DENUE, sin '
                                 'borrarlo ni ocultarlo: una persona decide en la cola de moderación.')

    def handle(self, *args, archivo, guardar, simular, retirar_ausentes, marcar_ausentes=False, **opciones):
        try:
            registros = self.leer(archivo) if archivo else descargar()
        except ErrorDenue as error:
            raise CommandError(str(error)) from None
        if guardar:
            with open(guardar, 'w', encoding='utf-8') as salida:
                json.dump(registros, salida, ensure_ascii=False)
        lugares, omitidos = interpretar(registros, TIPO_DE_SUBTIPO)
        if not lugares:
            raise CommandError('La descarga no trae ningún lugar: no se cambió nada.')

        existentes = {lugar.denue_id: lugar for lugar in Lugar.objects.exclude(denue_id=None)}
        rejilla = Rejilla()
        # Incluye lo ya importado del DENUE: si no, al repetir se crearía lo que antes se descartó por parecido.
        for fila in Lugar.objects.values_list('nombre', 'latitud', 'longitud'):
            rejilla.agregar(*fila)
        municipios, nuevos, cambiados, protegidos, reaparecidos, duplicados = {}, [], [], 0, 0, 0
        # atomic: un fallo a mitad no deja una importación parcial; al simular siempre se revierte.
        with transaction.atomic():
            for lugar in lugares:
                nombre_municipio = lugar.pop('municipio')
                registro = existentes.get(lugar['denue_id'])
                if registro is None and rejilla.hay_parecido(lugar['nombre'], lugar['latitud'], lugar['longitud']):
                    duplicados += 1
                    continue
                if nombre_municipio not in municipios:
                    municipios[nombre_municipio] = municipio_de(nombre_municipio)
                lugar['municipio'] = municipios[nombre_municipio]
                if registro is None:
                    nuevos.append(Lugar(**lugar))
                    rejilla.agregar(lugar['nombre'], lugar['latitud'], lugar['longitud'])
                elif registro.protegido:
                    protegidos += 1
                else:
                    reaparecidos += registro.posiblemente_cerrado
                    lugar.update(posiblemente_cerrado=False, ausente_desde=None)
                    for campo in CAMPOS:
                        setattr(registro, campo, lugar[campo])
                    cambiados.append(registro)
            Lugar.objects.bulk_create(nuevos, batch_size=TANDA)
            Lugar.objects.bulk_update(cambiados, CAMPOS, batch_size=TANDA)
            retirados = 0
            if retirar_ausentes:
                vigentes = {lugar['denue_id'] for lugar in lugares}
                ausentes = [lugar.pk for clave, lugar in existentes.items()
                            if clave not in vigentes and lugar.es_activo and not lugar.protegido]
                retirados = Lugar.objects.filter(pk__in=ausentes).update(es_activo=False)
            marcados = 0
            if marcar_ausentes:
                vigentes = {lugar['denue_id'] for lugar in lugares}
                marcados = marcar_ausentes_de(existentes, vigentes, timezone.localdate())
            if simular:
                transaction.set_rollback(True)

        self.conteos = {'creados': len(nuevos), 'actualizados': len(cambiados), 'ya_existian': duplicados,
                        'protegidos': protegidos, 'retirados': retirados, 'posiblemente_cerrados': marcados,
                        'reaparecidos': reaparecidos, 'omitidos': omitidos}
        accion = 'Se crearían' if simular else 'Creados'
        self.stdout.write(self.style.SUCCESS(
            f'{accion} {len(nuevos)} lugares. Actualizados: {len(cambiados)}. Ya existían: {duplicados}. '
            f'Editados en el admin, sin tocar: {protegidos}. Retirados: {retirados}. '
            f'Posiblemente cerrados (a revisión): {marcados}. Reaparecidos: {reaparecidos}. Omitidos: {omitidos}.'))

    def leer(self, ruta):
        try:
            with open(ruta, encoding='utf-8') as entrada:
                return json.load(entrada)
        except (OSError, ValueError) as error:
            raise CommandError(f'No se pudo leer {ruta}: {error}') from error
