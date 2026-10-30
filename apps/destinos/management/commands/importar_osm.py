"""Importa lugares turísticos de Jalisco desde OpenStreetMap, ocultos hasta que el personal los publique.

No crea cuentas ni requiere clave. Se puede repetir: lo ya importado no se toca, así se conservan las
ediciones del equipo. Guía: docs/importar-osm.md
"""
import json
import math

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify

from apps.destinos.models import Categoria, Destino, Municipio, Region
from apps.destinos.osm import TIPOS, ErrorOverpass, descargar, interpretar

REGION_POR_DEFECTO = 'Otras zonas de Jalisco'
# El catálogo inicial usa otro nombre para estos municipios.
ALIAS_MUNICIPIOS = {'san-pedro-tlaquepaque': 'tlaquepaque'}
# Un lugar con el mismo nombre a esta distancia es el mismo, no uno nuevo.
KM_MISMO_LUGAR = 2


def distancia_km(lat1, lon1, lat2, lon2):
    """Aproximación suficiente para distancias cortas."""
    alto = (lat2 - lat1) * 111
    ancho = (lon2 - lon1) * 111 * math.cos(math.radians(lat1))
    return math.hypot(alto, ancho)


def texto_de(lugar):
    if lugar['descripcion']:
        return lugar['descripcion']
    tipo = TIPOS[lugar['tipo']][0]
    return (f"{tipo} en {lugar['municipio']}, Jalisco. Todavía no tenemos una descripción: "
            'si lo conoces, ayúdanos con información práctica.')


def slug_libre(lugar):
    base = slugify(lugar['nombre'])[:180] or 'lugar'
    municipio = slugify(lugar['municipio'])[:30]
    for candidato in (base, f'{base}-{municipio}', f"{base}-{municipio}-{lugar['osm_id'].split('/')[1]}"):
        if not Destino.objects.filter(slug=candidato).exists():
            return candidato
    raise CommandError(f"No hay slug libre para {lugar['osm_id']}")


def es_duplicado(lugar):
    """Mismo nombre y cerca de un destino que ya existe; o el nombre del municipio, que no es un lugar concreto."""
    nombre = slugify(lugar['nombre'])[:180]
    if nombre == slugify(lugar['municipio']):
        return True
    # Un nombre sin letras latinas da un slug vacío, que coincidiría con todos los destinos.
    if not nombre:
        return False
    # Solo el slug exacto o el que slug_libre le daría: por prefijo, "Mirador" chocaría con "Mirador del Matemático".
    con_municipio = f"{nombre}-{slugify(lugar['municipio'])[:30]}"
    cercanos = Destino.objects.filter(
        Q(slug=nombre) | Q(slug__startswith=con_municipio)
    ).values_list('latitud', 'longitud')
    return any(
        distancia_km(lugar['latitud'], lugar['longitud'], float(latitud), float(longitud)) <= KM_MISMO_LUGAR
        for latitud, longitud in cercanos
    )


def municipio_de(nombre):
    slug = slugify(nombre)
    slug = ALIAS_MUNICIPIOS.get(slug, slug)
    existente = Municipio.objects.filter(slug=slug).first() or Municipio.objects.filter(nombre=nombre).first()
    if existente:
        return existente
    region, _ = Region.objects.get_or_create(nombre=REGION_POR_DEFECTO, defaults={'slug': slugify(REGION_POR_DEFECTO)})
    return Municipio.objects.create(nombre=nombre, slug=slug, region=region)


class Command(BaseCommand):
    help = 'Importa lugares de Jalisco desde OpenStreetMap. Quedan ocultos hasta publicarlos en el admin.'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', help='Usa una respuesta ya guardada en lugar de consultar Overpass.')
        parser.add_argument('--guardar', help='Guarda la respuesta de Overpass en este archivo.')
        parser.add_argument('--simular', action='store_true', help='Muestra qué haría sin guardar nada.')

    def handle(self, *args, archivo, guardar, simular, **opciones):
        try:
            datos = self.leer(archivo) if archivo else descargar()
            if guardar:
                with open(guardar, 'w', encoding='utf-8') as salida:
                    json.dump(datos, salida, ensure_ascii=False)
            lugares, omitidos = interpretar(datos)
        except ErrorOverpass as error:
            raise CommandError(str(error)) from error

        ya_importados = set(Destino.objects.exclude(osm_id=None).values_list('osm_id', flat=True))
        creados = conservados = duplicados = 0
        # atomic: un fallo a mitad no deja una importación parcial; al simular siempre se revierte.
        with transaction.atomic():
            for lugar in lugares:
                if lugar['osm_id'] in ya_importados:
                    conservados += 1
                elif es_duplicado(lugar):
                    duplicados += 1
                else:
                    self.crear(lugar)
                    creados += 1
            if simular:
                transaction.set_rollback(True)

        accion = 'Se crearían' if simular else 'Creados'
        self.stdout.write(self.style.SUCCESS(
            f'{accion} {creados} destinos ocultos. Ya importados: {conservados}. Duplicados: {duplicados}. '
            f'Omitidos por falta de datos: {omitidos}.'))
        if not simular and creados:
            self.stdout.write('Revísalos y publícalos en /admin/destinos/destino/ (filtro "Origen").')
        if not Destino.objects.filter(es_activo=True).exists():
            self.stdout.write(self.style.WARNING(
                'No hay destinos publicados: la portada se verá vacía hasta publicar alguno. '
                'Puedes cargar el catálogo inicial con cargar_destinos_iniciales.'))

    def leer(self, ruta):
        try:
            with open(ruta, encoding='utf-8') as entrada:
                return json.load(entrada)
        except (OSError, ValueError) as error:
            raise CommandError(f'No se pudo leer {ruta}: {error}') from error

    def crear(self, lugar):
        destino = Destino.objects.create(
            nombre=lugar['nombre'][:200], slug=slug_libre(lugar), descripcion=texto_de(lugar),
            municipio=municipio_de(lugar['municipio']), latitud=lugar['latitud'], longitud=lugar['longitud'],
            es_activo=False, osm_id=lugar['osm_id'],
        )
        nombre_categoria = TIPOS[lugar['tipo']][1]
        if nombre_categoria:
            categoria, _ = Categoria.objects.get_or_create(nombre=nombre_categoria,
                                                           defaults={'slug': slugify(nombre_categoria)})
            destino.categorias.add(categoria)
