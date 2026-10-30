"""Cálculos geográficos."""
from math import asin, cos, radians, sin, sqrt

RADIO_TIERRA_KM = 6371


def distancia_km(lat1, lon1, lat2, lon2):
    """Distancia en línea recta, con la fórmula del haversine."""
    fi1, fi2 = radians(lat1), radians(lat2)
    a = sin((fi2 - fi1) / 2) ** 2 + cos(fi1) * cos(fi2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * RADIO_TIERRA_KM * asin(sqrt(a))
