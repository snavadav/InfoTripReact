"""Dónde dormir cerca de un punto: dos o tres opciones, con hoteles y casas de huéspedes primero.

Orden: hotel o casa de huéspedes > hostal o departamento > motel; luego la calificación de reseñas publicadas, lo
recomendado por el equipo y la cercanía. Los moteles bajan (no se ocultan): muchos son de paso. Solo se muestran
precio y calificación cuando hay reseñas publicadas de la comunidad.
"""
from django.urls import reverse

from apps.comunidad.selectors import gasto_de_lugar
from apps.destinos.lugares import cerca_de

RADIO_KM = 10
OPCIONES = 3
# Se revisan los más cercanos; de ahí salen las opciones.
REVISADOS = 40
PRIORIDAD = {'hotel': 2, 'guest_house': 2, 'hostel': 1.5, 'apartment': 1.5, 'motel': 0}
PRIORIDAD_GENERAL = 1
# Cada estrella por encima o por debajo de 3 mueve un cuarto de nivel; solo con reseñas publicadas.
PESO_CALIFICACION = 0.25
BONO_RECOMENDADO = 0.75
# Estar en el límite del radio resta dos niveles: un hostal a la vuelta va antes que un hotel a 5 km.
PESO_DISTANCIA = 2.0


def _con_resenas(lugar):
    return bool(getattr(lugar, 'num_resenas', 0)) and lugar.calificacion_promedio is not None


def puntaje(lugar, radio_km=RADIO_KM):
    valor = PRIORIDAD.get(lugar.subtipo, PRIORIDAD_GENERAL)
    if _con_resenas(lugar):
        valor += (float(lugar.calificacion_promedio) - 3) * PESO_CALIFICACION
    if lugar.recomendado_equipo:
        valor += BONO_RECOMENDADO
    return valor - PESO_DISTANCIA * lugar.distancia_km / radio_km


def tarjeta(lugar):
    """Lo que muestra la tarjeta. Precio y calificación solo si vienen de reseñas publicadas."""
    gasto = gasto_de_lugar(lugar)
    con_resenas = _con_resenas(lugar)
    return {
        'id': lugar.pk, 'nombre': lugar.nombre, 'subtipo': lugar.get_subtipo_display(),
        'url': reverse('lugar-detalle', args=[lugar.pk]), 'distancia': lugar.distancia_legible,
        'distancia_km': lugar.distancia_km, 'latitud': float(lugar.latitud), 'longitud': float(lugar.longitud),
        'calificacion': round(float(lugar.calificacion_promedio), 1) if con_resenas else None,
        'num_resenas': lugar.num_resenas if con_resenas else 0,
        # Lo que dijeron gastar por noche quienes reseñaron en el último año (mínimo y máximo).
        'precio': None if gasto is None else {'minimo': str(gasto['minimo']), 'maximo': str(gasto['maximo']),
                                              'reportes': gasto['cantidad']},
        'recomendado_equipo': lugar.recomendado_equipo,
    }


def opciones_hospedaje(punto, radio_km=RADIO_KM, cuantas=OPCIONES):
    """Las mejores opciones para dormir cerca de un punto, ya como tarjetas. Lista vacía si no hay ninguna."""
    cercanos = cerca_de(punto[0], punto[1], radio_km=radio_km, tipo='dormir', limite=REVISADOS)
    cercanos.sort(key=lambda lugar: (-puntaje(lugar, radio_km), lugar.distancia_km, lugar.pk))
    return [tarjeta(lugar) for lugar in cercanos[:cuantas]]
