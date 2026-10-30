"""Metadatos para buscadores y redes sociales de las fichas de destino."""
import json

from django.conf import settings
from django.urls import reverse
from django.utils.text import Truncator


def seo_de_destino(lugar, resumen=None):
    """Título, descripción, imagen y datos estructurados de una ficha. `lugar` viene de completar()."""
    municipio = lugar['municipio']
    lugar_y_municipio = lugar['nombre'] if lugar['nombre'] == municipio else f"{lugar['nombre']}, {municipio}"
    titulo = f'{lugar_y_municipio}, Jalisco: qué saber antes de ir — InfoTrip'
    descripcion = Truncator(' '.join(lugar['descripcion'].split())).chars(155)
    imagen = settings.PUBLIC_BASE_URL + lugar['foto_url'] if lugar['foto_url'] else ''
    return {
        'titulo': titulo, 'descripcion': descripcion, 'imagen': imagen,
        'datos_estructurados': datos_estructurados(lugar, descripcion, imagen, resumen),
    }


def datos_estructurados(lugar, descripcion, imagen, resumen):
    datos = {
        '@context': 'https://schema.org', '@type': 'TouristAttraction',
        'name': lugar['nombre'], 'description': descripcion,
        'url': settings.PUBLIC_BASE_URL + reverse('destino-detalle', kwargs={'slug': lugar['slug']}),
        'address': {'@type': 'PostalAddress', 'addressLocality': lugar['municipio'],
                    'addressRegion': 'Jalisco', 'addressCountry': 'MX'},
    }
    if imagen:
        datos['image'] = imagen
    if not lugar['editorial']:
        datos['geo'] = {'@type': 'GeoCoordinates', 'latitude': lugar['latitud'], 'longitude': lugar['longitud']}
    resenas = (resumen or {}).get('resenas') or {}
    if resenas.get('cantidad'):
        datos['aggregateRating'] = {'@type': 'AggregateRating', 'ratingValue': round(float(resenas['promedio']), 1),
                                    'reviewCount': resenas['cantidad'], 'bestRating': 5, 'worstRating': 1}
    # El texto viene de la comunidad: "<" escapado para que no pueda cerrar la etiqueta <script>.
    return json.dumps(datos, ensure_ascii=False).replace('<', '\\u003c')
