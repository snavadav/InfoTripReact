"""Catálogo inicial; coordenadas orientativas de localidades, fuentes en docs/catalogo-inicial.md."""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from apps.destinos.models import Destino, Municipio, Region, Categoria

# Nombre del municipio cuando la localidad pertenece a otro; por defecto, el mismo nombre.
MUNICIPIOS = {'Ajijic': 'Chapala', 'Guachimontones': 'Teuchitlán', 'Barra de Navidad': 'Cihuatlán'}

LUGARES = [
    (
        'Guadalajara',
        'Centro de Jalisco',
        'Ciudad y cultura',
        '20.676389',
        '-103.342222',
        'Capital de Jalisco, en el Valle de Atemajac. Recorre su centro histórico y visita el Hospicio Cabañas.',
    ),
    (
        'Tlaquepaque',
        'Centro de Jalisco',
        'Ciudad y cultura',
        '20.583333',
        '-103.350000',
        'Parte del área metropolitana de Guadalajara. Pasea por su centro y conoce el Santuario de la Soledad.',
    ),
    (
        'Tonalá',
        'Centro de Jalisco',
        'Ciudad y cultura',
        '20.623333',
        '-103.245556',
        'Municipio del área metropolitana de Guadalajara, con plazas y templos históricos por recorrer.',
    ),
    (
        'Ajijic',
        'Ribera de Chapala',
        'Lago',
        '20.300278',
        '-103.272222',
        'Localidad del municipio de Chapala, a orillas del lago, con malecón y vistas a las montañas.',
    ),
    (
        'Guachimontones',
        'Valles de Jalisco',
        'Arqueología',
        '20.695149',
        '-103.835719',
        'Antiguo asentamiento prehispánico en Teuchitlán, cerca de una hora de Guadalajara, con pirámides circulares.',
    ),
    (
        'San Sebastián del Oeste',
        'Sierra de Jalisco',
        'Pueblos',
        '20.760833',
        '-104.851667',
        'Antiguo pueblo minero en la sierra del occidente de Jalisco.',
    ),
    (
        'Mascota',
        'Sierra de Jalisco',
        'Pueblos',
        '20.525556',
        '-104.782222',
        'Población de la sierra occidental, con plaza, quiosco y calles para recorrer a pie.',
    ),
    (
        'Talpa de Allende',
        'Sierra de Jalisco',
        'Pueblos',
        '20.381389',
        '-104.818056',
        'Localidad de la sierra occidental, conocida por su basílica de Nuestra Señora del Rosario.',
    ),
    (
        'Lagos de Moreno',
        'Altos de Jalisco',
        'Ciudad y cultura',
        '21.361389',
        '-101.935000',
        'Ciudad de la región Altos Norte, con templos históricos y el Teatro José Rosas Moreno.',
    ),
    (
        'Barra de Navidad',
        'Costa de Jalisco',
        'Costa',
        '19.208056',
        '-104.680556',
        'Pueblo pesquero de la costa sur, en el municipio de Cihuatlán, con playa frente al Pacífico.',
    ),
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
    help = 'Carga 15 destinos iniciales sin modificar ni reactivar registros existentes.'
    @transaction.atomic
    def handle(self, *args, **options):
        creados = 0
        for nombre, region_nombre, categoria_nombre, latitud, longitud, descripcion in LUGARES:
            slug = slugify(nombre)
            if Destino.objects.filter(slug=slug).exists():
                continue
            region, _ = Region.objects.get_or_create(nombre=region_nombre, defaults={'slug':slugify(region_nombre)})
            nombre_municipio = MUNICIPIOS.get(nombre, nombre)
            municipio, _ = Municipio.objects.get_or_create(
                nombre=nombre_municipio, defaults={'slug': slugify(nombre_municipio), 'region': region}
            )
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
