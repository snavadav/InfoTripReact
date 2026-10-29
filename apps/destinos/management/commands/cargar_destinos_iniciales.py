"""Catálogo inicial; coordenadas orientativas de localidades, fuentes en docs/catalogo-inicial.md."""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from apps.destinos.models import Destino, Municipio, Region, Categoria

LUGARES = [
    (
        'Tequila',
        'Valles de Jalisco',
        'Pueblos',
        '20.879439',
        '-103.835647',
        'Conoce una localidad del paisaje agavero de Jalisco y recorre sus calles y espacios culturales.',
    ),
    (
        'Puerto Vallarta',
        'Costa de Jalisco',
        'Costa',
        '20.641300',
        '-105.223300',
        'Descubre una ciudad junto al Pacífico, con paseos frente al mar y paisajes de bahía.',
    ),
    (
        'Chapala',
        'Ribera de Chapala',
        'Lagos',
        '20.298056',
        '-103.190278',
        'Explora una localidad junto al lago de Chapala y conoce sus paseos y espacios del centro.',
    ),
    (
        'Mazamitla',
        'Sierra de Jalisco',
        'Pueblos',
        '19.916111',
        '-103.020556',
        'Encuentra un pueblo de montaña y descubre el entorno boscoso de esta zona de Jalisco.',
    ),
    (
        'Tapalpa',
        'Sierra de Jalisco',
        'Pueblos',
        '19.945000',
        '-103.757778',
        'Recorre un pueblo de montaña y sus espacios tradicionales entre paisajes de sierra.',
    ),
]

class Command(BaseCommand):
    help = 'Carga cinco destinos iniciales sin modificar ni reactivar registros existentes.'
    @transaction.atomic
    def handle(self, *args, **options):
        creados = 0
        for nombre, region_nombre, categoria_nombre, latitud, longitud, descripcion in LUGARES:
            slug = slugify(nombre)
            if Destino.objects.filter(slug=slug).exists():
                continue
            region, _ = Region.objects.get_or_create(nombre=region_nombre, defaults={'slug':slugify(region_nombre)})
            municipio, _ = Municipio.objects.get_or_create(nombre=nombre, defaults={'slug':slug,'region':region})
            categoria, _ = Categoria.objects.get_or_create(
                nombre=categoria_nombre, defaults={'slug': slugify(categoria_nombre)}
            )
            destino = Destino.objects.create(
                nombre=nombre,
                slug=slug,
                municipio=municipio,
                latitud=latitud,
                longitud=longitud,
                descripcion=descripcion
                + ' Ubicación orientativa de la localidad; confirma el punto específico de tu visita.',
                direccion='Ubicación orientativa de la localidad, Jalisco, México',
            )
            destino.categorias.add(categoria)
            creados += 1
        self.stdout.write(self.style.SUCCESS(f'{creados} destinos creados. Los registros existentes se conservaron.'))
