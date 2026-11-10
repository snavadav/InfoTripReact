"""Lugares importados que ya no aparecen en su fuente (OpenStreetMap o DENUE).

No se borran ni se ocultan solos: un negocio puede faltar por un error de la fuente. Se marcan como posiblemente
cerrados y aparecen en la cola de moderación, donde una persona decide si siguen abiertos o se ocultan.
"""
from .models import Lugar


def marcar_ausentes(existentes, vigentes, hoy):
    """Marca los lugares de `existentes` (clave → Lugar) cuya clave no está en `vigentes`. Devuelve cuántos.

    Lo editado por el equipo (protegido), lo ya oculto y lo ya marcado no se toca.
    """
    claves = [lugar.pk for clave, lugar in existentes.items()
              if clave not in vigentes and lugar.es_activo and not lugar.protegido and not lugar.posiblemente_cerrado]
    return Lugar.objects.filter(pk__in=claves).update(posiblemente_cerrado=True, ausente_desde=hoy)
