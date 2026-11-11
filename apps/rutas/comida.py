"""Dónde comer en cada parada: dos o tres opciones, con lo local y clásico primero.

Orden: mercado o fonda > restaurante > cafetería > comida rápida; luego la calificación de reseñas publicadas y la
cercanía. Las cadenas bajan (no se ocultan) según una lista versionada de nombres. Solo se muestran precio y
calificación cuando hay datos reales: reseñas publicadas de la comunidad.
"""
import re

from django.urls import reverse
from django.utils.text import slugify

from apps.comunidad.selectors import gasto_de_lugar
from apps.destinos.lugares import cerca_de

RADIO_KM = 3
OPCIONES = 3
# Se revisan los más cercanos; de ahí salen las opciones. Más no cambia el resultado y sí el tiempo.
REVISADOS = 40
# Bares y cantinas no son una comida de viaje familiar: no se proponen.
SUBTIPOS = ('marketplace', 'restaurant', 'cafe', 'fast_food')
PRIORIDAD = {'marketplace': 3, 'fonda': 3, 'restaurant': 2, 'cafe': 1, 'fast_food': 0}
# Cada estrella por encima o por debajo de 3 mueve un cuarto de nivel; solo con reseñas publicadas.
PESO_CALIFICACION = 0.25
BONO_RECOMENDADO = 0.75
# Una cadena baja casi un nivel y medio: un restaurante local va antes que una franquicia a la misma distancia.
CASTIGO_CADENA = 1.5
# Estar en el límite del radio resta un nivel completo.
PESO_DISTANCIA = 1.0

# Palabras del nombre que dicen que es una fonda o cocina tradicional (sin acentos, en minúsculas).
FONDA = re.compile(r'\b(fonda|cocina economica|cenaduria|birrieria|pozoleria|menuderia|comida casera|'
                   r'cocina tradicional|tortas ahogadas|carnitas)\b')

# Cadenas nacionales e internacionales. Se compara el nombre en forma de slug: «mcdonalds» encuentra
# «McDonald's Plaza del Sol». Para agregar o quitar una, cambia la lista y la versión (fecha de la revisión).
VERSION_CADENAS = '2026-11-10'
CADENAS = (
    'applebees', 'benedettis', 'burger-king', 'carls-jr', 'chilis', 'churchs', 'cielito-querido', 'dairy-queen',
    'dominos', 'dominos-pizza', 'el-fogoncito', 'el-porton', 'ihop', 'italiannis', 'kentucky-fried-chicken', 'kfc',
    'krispy-kreme', 'little-caesars', 'mcdonalds', 'panda-express', 'papa-johns', 'peter-piper-pizza', 'pizza-hut',
    'popeyes', 'potzollcalli', 'punta-del-cielo', 'sanborns', 'shake-shack', 'starbucks', 'subway', 'sushi-itto',
    'taco-bell', 'the-italian-coffee-company', 'tim-hortons', 'toks', 'vips', 'wendys',
)


def _plano(texto):
    return slugify(texto).replace('-', ' ')


def es_cadena(nombre):
    # Sin apóstrofos: «McDonald's» → «mcdonalds». La cadena tiene que aparecer como palabras completas.
    slug = f"-{slugify(nombre.replace("'", '').replace('’', ''))}-"
    return any(f'-{cadena}-' in slug for cadena in CADENAS)


def clase_de(lugar):
    """'marketplace', 'fonda', 'restaurant', 'cafe' o 'fast_food'."""
    if lugar.subtipo == 'restaurant' and FONDA.search(_plano(lugar.nombre)):
        return 'fonda'
    return lugar.subtipo


NOMBRE_CLASE = {'marketplace': 'Mercado', 'fonda': 'Fonda o cocina tradicional', 'restaurant': 'Restaurante',
                'cafe': 'Cafetería', 'fast_food': 'Comida rápida'}


def puntaje(lugar, radio_km=RADIO_KM):
    valor = PRIORIDAD[clase_de(lugar)]
    if getattr(lugar, 'num_resenas', 0) and lugar.calificacion_promedio is not None:
        valor += (float(lugar.calificacion_promedio) - 3) * PESO_CALIFICACION
    if lugar.recomendado_equipo:
        valor += BONO_RECOMENDADO
    if es_cadena(lugar.nombre):
        valor -= CASTIGO_CADENA
    return valor - PESO_DISTANCIA * lugar.distancia_km / radio_km


def tarjeta(lugar):
    """Lo que muestra la tarjeta. Precio y calificación solo si vienen de reseñas publicadas."""
    gasto = gasto_de_lugar(lugar)
    con_resenas = bool(getattr(lugar, 'num_resenas', 0)) and lugar.calificacion_promedio is not None
    return {
        'id': lugar.pk, 'nombre': lugar.nombre, 'clase': clase_de(lugar), 'tipo': NOMBRE_CLASE[clase_de(lugar)],
        'subtipo': lugar.get_subtipo_display(), 'url': reverse('lugar-detalle', args=[lugar.pk]),
        'distancia': lugar.distancia_legible, 'distancia_km': lugar.distancia_km,
        'latitud': float(lugar.latitud), 'longitud': float(lugar.longitud),
        'calificacion': round(float(lugar.calificacion_promedio), 1) if con_resenas else None,
        'num_resenas': lugar.num_resenas if con_resenas else 0,
        # Lo que dijeron gastar por persona quienes reseñaron en el último año (mínimo y máximo).
        'precio': None if gasto is None else {'minimo': str(gasto['minimo']), 'maximo': str(gasto['maximo']),
                                              'reportes': gasto['cantidad']},
        'recomendado_equipo': lugar.recomendado_equipo, 'cadena': es_cadena(lugar.nombre),
    }


def opciones_comida(punto, radio_km=RADIO_KM, cuantas=OPCIONES):
    """Las mejores opciones para comer cerca de un punto, ya como tarjetas. Lista vacía si no hay ninguna."""
    cercanos = [lugar for lugar in cerca_de(punto[0], punto[1], radio_km=radio_km, tipo='comer', limite=REVISADOS)
                if lugar.subtipo in SUBTIPOS]
    cercanos.sort(key=lambda lugar: (-puntaje(lugar, radio_km), lugar.distancia_km, lugar.pk))
    return [tarjeta(lugar) for lugar in cercanos[:cuantas]]
