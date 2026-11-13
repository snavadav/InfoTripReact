"""Importa desde OpenStreetMap dónde comer, dormir y comprar, gasolineras, farmacias y cajeros de Jalisco.

A diferencia de `importar_osm`, estos lugares se publican de inmediato: son miles y no se pueden revisar
uno por uno. Se puede repetir para traer cambios; lo editado en el admin no se toca. Guía: docs/importar-osm.md

Con --solo-mercados descarga y toca únicamente los mercados (amenity=marketplace): lo demás queda igual.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.destinos.ausentes import marcar_ausentes as marcar_ausentes_de
from apps.destinos.models import Lugar
from apps.destinos.osm import (
    CONSULTA_LUGARES, CONSULTA_MERCADOS, CONSULTA_MUSEOS_PARQUES, ErrorOverpass, descargar, interpretar_lugares,
)
from .importar_osm import municipio_de

# Opción → (consulta reducida, subtipos que toca). Lo demás queda como estaba.
PARCIALES = {
    'solo_mercados': (CONSULTA_MERCADOS, {'marketplace'}),
    'solo_museos_parques': (CONSULTA_MUSEOS_PARQUES, {'museum', 'park', 'nature_reserve'}),
}

CAMPOS = ['nombre', 'tipo', 'subtipo', 'latitud', 'longitud', 'direccion', 'telefono', 'sitio_web', 'horario',
          'municipio',
          'posiblemente_cerrado', 'ausente_desde']
TANDA = 500


class Command(BaseCommand):
    help = 'Importa lugares útiles de Jalisco desde OpenStreetMap. Se publican de inmediato.'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', help='Usa una respuesta ya guardada en lugar de consultar Overpass.')
        parser.add_argument('--guardar', help='Guarda la respuesta de Overpass en este archivo.')
        parser.add_argument('--simular', action='store_true', help='Muestra qué haría sin guardar nada.')
        parser.add_argument('--retirar-ausentes', action='store_true',
                            help='Oculta lo importado antes que ya no aparece en OpenStreetMap.')
        parser.add_argument('--marcar-ausentes', action='store_true',
                            help='Marca como posiblemente cerrado lo que ya no aparece en OpenStreetMap, sin '
                                 'borrarlo ni ocultarlo: una persona decide en la cola de moderación.')
        parser.add_argument('--solo-mercados', action='store_true',
                            help='Solo mercados (amenity=marketplace); no toca los demás lugares.')
        parser.add_argument('--solo-museos-parques', action='store_true',
                            help='Solo museos y parques; no toca los demás lugares.')

    def handle(self, *args, archivo, guardar, simular, retirar_ausentes, marcar_ausentes=False, **opciones):
        elegidas = [opcion for opcion in PARCIALES if opciones.get(opcion)]
        if len(elegidas) > 1:
            raise CommandError('Elige una sola importación parcial a la vez.')
        consulta, subtipos = PARCIALES[elegidas[0]] if elegidas else (CONSULTA_LUGARES, None)
        try:
            datos = self.leer(archivo) if archivo else descargar(consulta)
            if guardar:
                with open(guardar, 'w', encoding='utf-8') as salida:
                    json.dump(datos, salida, ensure_ascii=False)
            lugares, omitidos = interpretar_lugares(datos)
        except ErrorOverpass as error:
            raise CommandError(str(error)) from error
        if subtipos:
            lugares = [lugar for lugar in lugares if lugar['subtipo'] in subtipos]
        # Una respuesta vacía no debe interpretarse como que todos los lugares desaparecieron.
        if not lugares:
            raise CommandError('La respuesta no trae ningún lugar: no se cambió nada.')

        importados = Lugar.objects.exclude(osm_id=None)
        if subtipos:
            importados = importados.filter(subtipo__in=subtipos)
        existentes = {lugar.osm_id: lugar for lugar in importados}
        municipios, nuevos, cambiados, protegidos, reaparecidos = {}, [], [], 0, 0
        # atomic: un fallo a mitad no deja una importación parcial; al simular siempre se revierte.
        with transaction.atomic():
            for lugar in lugares:
                nombre = lugar.pop('municipio')
                if nombre not in municipios:
                    municipios[nombre] = municipio_de(nombre)
                lugar['municipio'] = municipios[nombre]
                registro = existentes.get(lugar['osm_id'])
                if registro is None:
                    nuevos.append(Lugar(**lugar))
                elif registro.protegido:
                    protegidos += 1
                else:
                    reaparecidos += registro.posiblemente_cerrado
                    lugar.update(posiblemente_cerrado=False, ausente_desde=None)
                    if registro.horario_fuente_url:
                        lugar['horario'] = registro.horario  # Aprobado de una fuente oficial: no se pisa.
                    for campo in CAMPOS:
                        setattr(registro, campo, lugar[campo])
                    cambiados.append(registro)
            Lugar.objects.bulk_create(nuevos, batch_size=TANDA)
            Lugar.objects.bulk_update(cambiados, CAMPOS, batch_size=TANDA)
            retirados = 0
            if retirar_ausentes:
                vigentes = {lugar['osm_id'] for lugar in lugares}
                ausentes = [lugar.pk for clave, lugar in existentes.items()
                            if clave not in vigentes and lugar.es_activo]
                retirados = Lugar.objects.filter(pk__in=ausentes).update(es_activo=False)
            marcados = 0
            if marcar_ausentes:
                vigentes = {lugar['osm_id'] for lugar in lugares}
                marcados = marcar_ausentes_de(existentes, vigentes, timezone.localdate())
            if simular:
                transaction.set_rollback(True)

        self.conteos = {'creados': len(nuevos), 'actualizados': len(cambiados), 'protegidos': protegidos,
                        'retirados': retirados, 'posiblemente_cerrados': marcados, 'reaparecidos': reaparecidos,
                        'omitidos': omitidos}
        accion = 'Se crearían' if simular else 'Creados'
        self.stdout.write(self.style.SUCCESS(
            f'{accion} {len(nuevos)} lugares. Actualizados: {len(cambiados)}. '
            f'Editados en el admin, sin tocar: {protegidos}. Retirados: {retirados}. '
            f'Posiblemente cerrados (a revisión): {marcados}. Reaparecidos: {reaparecidos}. '
            f'Omitidos por falta de datos: {omitidos}.'))

    def leer(self, ruta):
        try:
            with open(ruta, encoding='utf-8') as entrada:
                return json.load(entrada)
        except (OSError, ValueError) as error:
            raise CommandError(f'No se pudo leer {ruta}: {error}') from error
