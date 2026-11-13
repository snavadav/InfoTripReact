"""Carga lugares desde un CSV preparado a mano (OpenStreetMap y Sistema de Información Cultural), sin duplicar.

Cada fila dice a qué modelo va (`modelo_sugerido`):
- «Lugar»: se publica de inmediato, como en `importar_lugares`.
- «Destino»: queda oculto hasta que el equipo lo revise y publique, como en `importar_osm`.

Solo agrega: nunca cambia ni borra lo que ya existe. Se puede repetir. Guía: docs/importar-osm.md
"""
import csv
from collections import Counter
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.core.geo import distancia_km
from apps.destinos.models import Categoria, Destino, Lugar, TIPO_DE_SUBTIPO
from .importar_osm import es_duplicado, municipio_de
from .sembrar_contenido import TEXTO_AUTOMATICO

COLUMNAS = {'nombre', 'municipio', 'estado', 'latitud', 'longitud', 'categoria', 'modelo_sugerido', 'tipo', 'subtipo',
            'direccion', 'telefono', 'sitio_web', 'horario', 'horario_fuente_url', 'fuente_nombre', 'fuente_url',
            'fuente_id', 'fecha_consulta'}
# Mismo nombre a esta distancia de algo que ya existe es el mismo sitio, venga de la fuente que venga.
KM_MISMO_SITIO = 0.15
METROS_MISMO_SITIO = int(KM_MISMO_SITIO * 1000)
# Recuadro amplio alrededor de Jalisco: una coordenada fuera de aquí es un error de captura.
JALISCO = (18.8, 22.8, -105.8, -101.4)
# Categorías del archivo que llegan sin subtipo y sí le sirven a quien viaja. Las demás tiendas de alimentos
# (carnicerías, pescaderías, fruterías…) se omiten, igual que en la importación de OpenStreetMap.
SUBTIPO_DE_CATEGORIA = {'Heladerías': 'ice_cream', 'Zonas de comida': 'food_court', 'Cabañas': 'chalet'}
# Categoría del archivo → (nombre en una frase, categoría del catálogo o None si no hay una clara).
DESTINOS = {
    'Iglesias y templos': ('Templo', 'Ciudad y cultura'), 'Centros culturales': ('Centro cultural', 'Ciudad y cultura'),
    'Museos': ('Museo', 'Ciudad y cultura'), 'Galerías': ('Galería', 'Ciudad y cultura'),
    'Librerías': ('Librería', 'Ciudad y cultura'), 'Memoriales': ('Memorial', 'Ciudad y cultura'),
    'Teatros': ('Teatro', 'Ciudad y cultura'), 'Artesanías': ('Casa de artesanías', 'Ciudad y cultura'),
    'Monumentos': ('Monumento', 'Ciudad y cultura'), 'Vestigios históricos': ('Vestigio histórico', 'Ciudad y cultura'),
    'Miradores': ('Mirador', 'Miradores'), 'Cascadas': ('Cascada', 'Naturaleza'), 'Jardines': ('Jardín', 'Naturaleza'),
    'Áreas de picnic': ('Área de picnic', 'Naturaleza'), 'Campamentos': ('Campamento', 'Naturaleza'),
    'Playas': ('Playa', 'Costa'), 'Zonas arqueológicas': ('Sitio arqueológico', 'Arqueología'),
    'Sitios de interés': ('Lugar de interés', None), 'Información turística': ('Módulo de información turística', None),
    'Parques acuáticos': ('Parque acuático', None), 'Parques temáticos': ('Parque temático', None),
    'Zoológicos': ('Zoológico', None),
}


def _parecidos(uno, otro):
    """Iguales, o uno contiene al otro («Mercado Corona» y «Mercado Corona Guadalajara»)."""
    return uno == otro or (min(len(uno), len(otro)) > 6 and (uno in otro or otro in uno))


class Cercanos:
    """Nombres ya registrados, por celda de ~1 km, para comparar cada fila solo con lo que tiene alrededor."""

    def __init__(self):
        self.celdas = {}
        for modelo in (Lugar, Destino):
            for nombre, latitud, longitud in modelo.objects.values_list('nombre', 'latitud', 'longitud').iterator():
                self.agregar(nombre, float(latitud), float(longitud))

    def agregar(self, nombre, latitud, longitud):
        self.celdas.setdefault((round(latitud, 2), round(longitud, 2)), []).append((slugify(nombre), latitud, longitud))

    def hay(self, nombre, latitud, longitud):
        nombre = slugify(nombre)
        if not nombre:
            return False
        for paso_lat in (-0.01, 0, 0.01):
            for paso_lng in (-0.01, 0, 0.01):
                celda = (round(latitud + paso_lat, 2), round(longitud + paso_lng, 2))
                for otro, otra_lat, otra_lng in self.celdas.get(celda, []):
                    if not _parecidos(nombre, otro):
                        continue
                    if distancia_km(latitud, longitud, otra_lat, otra_lng) <= KM_MISMO_SITIO:
                        return True
        return False


def _sitio_web(valor):
    """Solo http y https: este valor termina en un enlace, y `javascript:` ejecutaría código."""
    valor = valor.strip()
    return valor if valor.startswith(('http://', 'https://')) and len(valor) <= 300 else ''


def _fecha(valor):
    try:
        return date.fromisoformat(valor.strip())
    except ValueError:
        return None


def _slug_libre(datos, clave):
    """Como el de importar_osm, pero la clave de la fuente no siempre es de OpenStreetMap."""
    base = slugify(datos['nombre'])[:180] or 'lugar'
    municipio = slugify(datos['municipio'])[:30]
    numero = slugify(clave.split('/')[-1])[:20] or 'x'
    for candidato in (base, f'{base}-{municipio}', f'{base}-{municipio}-{numero}'):
        if not Destino.objects.filter(slug=candidato).exists():
            return candidato
    raise CommandError(f"No hay slug libre para «{datos['nombre']}» ({clave}).")


class Command(BaseCommand):
    help = 'Carga lugares y destinos desde un CSV, sin duplicar lo que ya existe. Los destinos quedan ocultos.'

    def add_arguments(self, parser):
        parser.add_argument('archivo', help='Ruta del CSV (UTF-8, con encabezados).')
        parser.add_argument('--simular', action='store_true', help='Muestra qué haría sin guardar nada.')

    def handle(self, *args, archivo, simular, **opciones):
        filas = self.leer(archivo)
        osm = set(Lugar.objects.exclude(osm_id=None).values_list('osm_id', flat=True))
        osm |= set(Destino.objects.exclude(osm_id=None).values_list('osm_id', flat=True))
        cercanos = Cercanos()
        self.conteos = Counter()
        municipios = {}
        # atomic: un fallo a mitad no deja una carga parcial; al simular siempre se revierte.
        with transaction.atomic():
            for fila in filas:
                self.conteos[self.cargar(fila, osm, cercanos, municipios)] += 1
            if simular:
                transaction.set_rollback(True)

        accion = 'Se crearían' if simular else 'Creados'
        self.stdout.write(self.style.SUCCESS(
            f"{accion} {self.conteos['lugar']} lugares y {self.conteos['destino']} destinos ocultos, "
            f'de {len(filas)} filas.'))
        for motivo, texto in [('clave', 'Ya existían con la misma clave de OpenStreetMap'),
                              ('parecido', f'Mismo nombre a menos de {METROS_MISMO_SITIO} m de algo que ya existe'),
                              ('tipo', 'Tipo de lugar que no se importa'),
                              ('datos', 'Sin nombre, municipio o coordenadas válidas en Jalisco')]:
            self.stdout.write(f'  {texto}: {self.conteos[motivo]}.')
        if not simular and self.conteos['destino']:
            self.stdout.write('Revisa y publica los destinos en /admin/destinos/destino/ (filtro «Publicado: no»).')

    def leer(self, ruta):
        try:
            with open(ruta, encoding='utf-8-sig', newline='') as entrada:
                lector = csv.DictReader(entrada)
                faltan = COLUMNAS - set(lector.fieldnames or [])
                if faltan:
                    raise CommandError(f"Al archivo le faltan columnas: {', '.join(sorted(faltan))}.")
                filas = list(lector)
        except (OSError, UnicodeDecodeError, csv.Error) as error:
            raise CommandError(f'No se pudo leer {ruta}: {error}') from error
        if not filas:
            raise CommandError('El archivo no trae ninguna fila: no se cambió nada.')
        return filas

    def cargar(self, fila, osm, cercanos, municipios):
        """Crea el lugar o el destino de la fila y devuelve qué pasó: 'lugar', 'destino' o el motivo de omitirla."""
        fila = {clave: (valor or '').strip() for clave, valor in fila.items()}
        nombre = fila['nombre'][:200]
        try:
            latitud, longitud = round(float(fila['latitud']), 6), round(float(fila['longitud']), 6)
        except ValueError:
            return 'datos'
        en_jalisco = JALISCO[0] <= latitud <= JALISCO[1] and JALISCO[2] <= longitud <= JALISCO[3]
        if not nombre or not fila['municipio'] or fila['estado'] != 'Jalisco' or not en_jalisco:
            return 'datos'
        es_destino = fila['modelo_sugerido'] == 'Destino'
        subtipo = fila['subtipo'] or SUBTIPO_DE_CATEGORIA.get(fila['categoria'], '')
        if es_destino and fila['categoria'] not in DESTINOS:
            return 'tipo'
        if not es_destino and (fila['modelo_sugerido'] != 'Lugar' or subtipo not in TIPO_DE_SUBTIPO):
            return 'tipo'
        osm_id = fila['fuente_id'] if fila['fuente_nombre'] == 'OpenStreetMap' else None
        if osm_id and osm_id in osm:
            return 'clave'
        datos = {'nombre': nombre, 'municipio': fila['municipio'], 'latitud': latitud, 'longitud': longitud,
                 'osm_id': osm_id}
        # es_duplicado: además, el mismo nombre de destino a menos de 2 km, o el nombre del municipio a secas.
        if cercanos.hay(nombre, latitud, longitud) or (es_destino and es_duplicado(datos)):
            return 'parecido'
        if fila['municipio'] not in municipios:
            municipios[fila['municipio']] = municipio_de(fila['municipio'])
        municipio = municipios[fila['municipio']]
        if es_destino:
            self.crear_destino(fila, datos, municipio)
        else:
            Lugar.objects.create(
                nombre=nombre, tipo=TIPO_DE_SUBTIPO[subtipo], subtipo=subtipo, municipio=municipio, latitud=latitud,
                longitud=longitud, direccion=fila['direccion'][:300], telefono=fila['telefono'][:60],
                sitio_web=_sitio_web(fila['sitio_web']), horario=fila['horario'][:200], osm_id=osm_id,
            )
        if osm_id:
            osm.add(osm_id)
        cercanos.agregar(nombre, latitud, longitud)
        return 'destino' if es_destino else 'lugar'

    def crear_destino(self, fila, datos, municipio):
        frase, nombre_categoria = DESTINOS[fila['categoria']]
        descripcion = (f"{frase} en {fila['municipio']}, Jalisco. {TEXTO_AUTOMATICO}: "
                       'si lo conoces, ayúdanos con información práctica.')
        if not datos['osm_id']:
            # Sin clave de OpenStreetMap el crédito no sale solo en la ficha: va en el texto.
            descripcion += (f" Fuente: {fila['fuente_nombre']} ({fila['fuente_url']}), "
                            f"consultado el {fila['fecha_consulta']}.")
        destino = Destino(
            nombre=datos['nombre'], slug=_slug_libre(datos, fila['fuente_id']), descripcion=descripcion,
            municipio=municipio,
            latitud=datos['latitud'], longitud=datos['longitud'], direccion=fila['direccion'][:300],
            es_activo=False, osm_id=datos['osm_id'],
        )
        # El horario de un destino solo se guarda con la cita de quien lo publica; el de OpenStreetMap no la trae.
        fuente_horario = _sitio_web(fila['horario_fuente_url'])
        if fila['horario'] and fuente_horario and not datos['osm_id']:
            destino.horario = fila['horario'][:200]
            destino.horario_fuente_url = fuente_horario
            destino.horario_fecha_consulta = _fecha(fila['fecha_consulta'])
        destino.save()
        if nombre_categoria:
            categoria, _ = Categoria.objects.get_or_create(nombre=nombre_categoria,
                                                           defaults={'slug': slugify(nombre_categoria)})
            destino.categorias.add(categoria)
