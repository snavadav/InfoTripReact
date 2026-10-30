"""Importa desde OpenStreetMap dónde comer, dormir, gasolineras, farmacias y cajeros de Jalisco.

A diferencia de `importar_osm`, estos lugares se publican de inmediato: son miles y no se pueden revisar
uno por uno. Se puede repetir para traer cambios; lo editado en el admin no se toca. Guía: docs/importar-osm.md
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.destinos.models import Lugar
from apps.destinos.osm import CONSULTA_LUGARES, ErrorOverpass, descargar, interpretar_lugares
from .importar_osm import municipio_de

CAMPOS = ['nombre', 'tipo', 'subtipo', 'latitud', 'longitud', 'direccion', 'telefono', 'sitio_web', 'horario',
          'municipio']
TANDA = 500


class Command(BaseCommand):
    help = 'Importa lugares útiles de Jalisco desde OpenStreetMap. Se publican de inmediato.'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', help='Usa una respuesta ya guardada en lugar de consultar Overpass.')
        parser.add_argument('--guardar', help='Guarda la respuesta de Overpass en este archivo.')
        parser.add_argument('--simular', action='store_true', help='Muestra qué haría sin guardar nada.')
        parser.add_argument('--retirar-ausentes', action='store_true',
                            help='Oculta lo importado antes que ya no aparece en OpenStreetMap.')

    def handle(self, *args, archivo, guardar, simular, retirar_ausentes, **opciones):
        try:
            datos = self.leer(archivo) if archivo else descargar(CONSULTA_LUGARES)
            if guardar:
                with open(guardar, 'w', encoding='utf-8') as salida:
                    json.dump(datos, salida, ensure_ascii=False)
            lugares, omitidos = interpretar_lugares(datos)
        except ErrorOverpass as error:
            raise CommandError(str(error)) from error
        # Una respuesta vacía no debe interpretarse como que todos los lugares desaparecieron.
        if not lugares:
            raise CommandError('La respuesta no trae ningún lugar: no se cambió nada.')

        existentes = {lugar.osm_id: lugar for lugar in Lugar.objects.exclude(osm_id=None)}
        municipios, nuevos, cambiados, protegidos = {}, [], [], 0
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
            if simular:
                transaction.set_rollback(True)

        accion = 'Se crearían' if simular else 'Creados'
        self.stdout.write(self.style.SUCCESS(
            f'{accion} {len(nuevos)} lugares. Actualizados: {len(cambiados)}. Editados en el admin, sin tocar: '
            f'{protegidos}. Retirados: {retirados}. Omitidos por falta de datos: {omitidos}.'))

    def leer(self, ruta):
        try:
            with open(ruta, encoding='utf-8') as entrada:
                return json.load(entrada)
        except (OSError, ValueError) as error:
            raise CommandError(f'No se pudo leer {ruta}: {error}') from error
