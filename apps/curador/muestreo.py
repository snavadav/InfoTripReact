"""Qué lugar mostrar a continuación para etiquetar.

Muestra: se toma el tipo de lugar con menos etiquetas, para que la muestra no quede llena de restaurantes (son
más de la mitad), y dentro de ese tipo un lugar en un orden pseudoaleatorio fijo: igual para todas las personas,
sin depender del orden alfabético ni de la fuente, y repetible. Sirve para medir el modelo sin sesgo.

Dudas (aprendizaje activo): cuando ya hay un modelo, el lugar sobre el que está más indeciso (probabilidad más
cercana a 0.5). Cada respuesta ahí le enseña más que una sobre un caso obvio. Estas etiquetas sirven para
entrenar, pero no forman una muestra representativa.
"""
from django.db.models import Count, F
from django.db.models.functions import Abs

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


def siguiente_dudoso(usuario):
    """El lugar con la predicción más indecisa que esta persona no ha etiquetado; None si no hay predicciones."""
    return (Lugar.objects.exclude(etiquetas__autor=usuario).filter(prediccion__isnull=False)
            .select_related('municipio').annotate(duda=Abs(F('prediccion__probabilidad') - 0.5))
            .order_by('duda', 'pk').first())
