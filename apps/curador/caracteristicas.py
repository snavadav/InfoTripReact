"""De la base de datos a las filas que lee el modelo; también junta las etiquetas del equipo."""
import math
from collections import defaultdict

import numpy as np
from django.utils.text import slugify

from apps.destinos.denue import ZONA_METROPOLITANA
from apps.destinos.models import Destino, Lugar

from .models import EtiquetaLugar

RADIO_TIERRA_KM = 6371.0


def _coordenadas_de_destinos():
    puntos = list(Destino.objects.filter(es_activo=True).values_list('latitud', 'longitud'))
    return np.radians(np.array(puntos, dtype=float)) if puntos else np.empty((0, 2))


def km_al_destino_mas_cercano(latitud, longitud, destinos):
    """Distancia en línea recta (haversine) al destino público más cercano; 500 km si no hay destinos."""
    if not len(destinos):
        return 500.0
    lat, lng = math.radians(latitud), math.radians(longitud)
    dlat, dlng = destinos[:, 0] - lat, destinos[:, 1] - lng
    a = np.sin(dlat / 2) ** 2 + math.cos(lat) * np.cos(destinos[:, 0]) * np.sin(dlng / 2) ** 2
    return float(2 * RADIO_TIERRA_KM * np.arcsin(np.sqrt(a)).min())


def fila(lugar, destinos):
    km = km_al_destino_mas_cercano(float(lugar.latitud), float(lugar.longitud), destinos)
    return {
        'nombre': lugar.nombre,
        'tipo': lugar.tipo,
        'subtipo': lugar.subtipo,
        'fuente': 'denue' if lugar.denue_id else 'osm' if lugar.osm_id else 'comunidad',
        'tiene_telefono': int(bool(lugar.telefono)),
        'tiene_web': int(bool(lugar.sitio_web)),
        'tiene_horario': int(bool(lugar.horario)),
        'tiene_direccion': int(bool(lugar.direccion)),
        'metropolitana': int(bool(lugar.municipio) and slugify(lugar.municipio.nombre) in ZONA_METROPOLITANA),
        'log_km_destino': math.log1p(km),
        'palabras': len(lugar.nombre.split()),
    }


def filas(lugares):
    destinos = _coordenadas_de_destinos()
    return [fila(lugar, destinos) for lugar in lugares]


def etiquetas_por_lugar():
    """Una etiqueta por lugar: la mayoría de las respuestas "sí" o "no". Los empates y los "no sé" se descartan."""
    votos = defaultdict(list)
    for lugar_id, util in EtiquetaLugar.objects.exclude(util=None).values_list('lugar_id', 'util'):
        votos[lugar_id].append(util)
    return {lugar_id: sum(v) > len(v) / 2 for lugar_id, v in votos.items() if sum(v) * 2 != len(v)}


def acuerdo_entre_personas():
    """Kappa de Cohen entre pares de respuestas sobre el mismo lugar (las dos primeras de cada lugar).

    Mide si el criterio es claro: con kappa bajo, ni una persona ni un modelo pueden aprender bien la tarea.
    Devuelve (lugares comparados, porcentaje de acuerdo, kappa) o None si hay menos de 20 lugares comparables.
    """
    pares = defaultdict(list)
    for lugar_id, util in (EtiquetaLugar.objects.exclude(util=None).order_by('creado', 'pk')
                           .values_list('lugar_id', 'util')):
        if len(pares[lugar_id]) < 2:
            pares[lugar_id].append(util)
    dobles = [p for p in pares.values() if len(p) == 2]
    if len(dobles) < 20:
        return None
    n = len(dobles)
    observado = sum(a == b for a, b in dobles) / n
    si_a, si_b = sum(a for a, _ in dobles) / n, sum(b for _, b in dobles) / n
    esperado = si_a * si_b + (1 - si_a) * (1 - si_b)
    kappa = 1.0 if esperado == 1 else (observado - esperado) / (1 - esperado)
    return n, observado, kappa


def lugares_etiquetados():
    """(lugares, etiquetas) en el mismo orden, listos para entrenar."""
    etiquetas = etiquetas_por_lugar()
    lugares = list(Lugar.objects.filter(pk__in=etiquetas).select_related('municipio').order_by('pk'))
    return lugares, [etiquetas[lugar.pk] for lugar in lugares]
