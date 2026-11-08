"""Qué lugar mostrar a continuación para etiquetar.

Se toma el tipo de lugar con menos etiquetas, para que la muestra no quede llena de restaurantes (son más de la
mitad), y dentro de ese tipo un lugar en un orden pseudoaleatorio fijo: igual para todas las personas, sin
depender del orden alfabético ni de la fuente, y repetible.
"""
from django.db.models import Count, F

from apps.destinos.models import Lugar

from .models import EtiquetaLugar

# Multiplicador de Knuth: revuelve los id de forma determinista y la base de datos lo calcula sola.
_MEZCLA = 2654435761
_MODULO = 2 ** 32


def progreso():
    """Etiquetas útiles (sí o no) por tipo de lugar, y en total."""
    por_tipo = dict(EtiquetaLugar.objects.exclude(util=None).values_list('lugar__tipo')
                    .annotate(n=Count('pk')).order_by())
    filas = [{'tipo': nombre, 'total': por_tipo.get(clave, 0)} for clave, nombre in Lugar.TIPOS]
    return filas, sum(por_tipo.values())


def siguiente(usuario):
    """Un lugar que esta persona no ha etiquetado, del tipo con menos etiquetas; None si ya no hay."""
    por_tipo = dict(EtiquetaLugar.objects.values_list('lugar__tipo').annotate(n=Count('pk')).order_by())
    pendientes = Lugar.objects.exclude(etiquetas__autor=usuario)
    for tipo in sorted((clave for clave, _ in Lugar.TIPOS), key=lambda t: (por_tipo.get(t, 0), t)):
        lugar = (pendientes.filter(tipo=tipo).select_related('municipio')
                 .annotate(orden=F('pk') * _MEZCLA % _MODULO).order_by('orden', 'pk').first())
        if lugar:
            return lugar
    return None
