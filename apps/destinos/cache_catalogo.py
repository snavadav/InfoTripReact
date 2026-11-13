"""Caché de lo que se arma a partir del catálogo público y casi no cambia (puntos del mapa, opciones de filtros…).

Cada valor se guarda bajo una «versión del catálogo». Guardar o borrar un destino, su municipio, región,
categoría o servicio, o un aporte (fotos, gastos, datos prácticos), cambia la versión: lo guardado antes deja de
leerse de inmediato y caduca solo. Lo que no pasa por señales (`queryset.update()`, cambios hechos a mano en la
base) se ve como mucho `DURACION` segundos después. En producción la caché es Redis, compartida entre procesos.
"""
import time

from django.apps import apps
from django.core.cache import cache
from django.db.models.signals import m2m_changed, post_delete, post_save

CLAVE_VERSION = 'catalogo:version'
DURACION = 10 * 60
# Modelos cuyo cambio puede alterar lo guardado. Se registran en DestinosConfig.ready().
MODELOS = [
    'destinos.Destino', 'destinos.Municipio', 'destinos.Region', 'destinos.Categoria', 'destinos.Servicio',
    'destinos.ReferenciaCosto', 'comunidad.Aporte', 'comunidad.Colaboracion', 'comunidad.Confirmacion',
]


def version():
    actual = cache.get(CLAVE_VERSION)
    if actual is None:
        # El reloj, para no repetir una versión anterior si la caché se vació (otro proceso, reinicio de Redis).
        cache.add(CLAVE_VERSION, int(time.time() * 1000), timeout=None)
        actual = cache.get(CLAVE_VERSION)
    return actual


def invalidar(**_):
    try:
        cache.incr(CLAVE_VERSION)
    except ValueError:  # Aún no había versión: la próxima lectura crea una nueva.
        pass


def guardado(nombre, calcular, duracion=DURACION):
    """El valor de `calcular()` para esta versión del catálogo; se calcula solo si no estaba guardado."""
    clave = f'catalogo:{version()}:{nombre}'
    valor = cache.get(clave)
    if valor is None:
        valor = calcular()
        cache.set(clave, valor, duracion)
    return valor


def conectar_senales():
    for etiqueta in MODELOS:
        modelo = apps.get_model(etiqueta)
        post_save.connect(invalidar, sender=modelo, dispatch_uid=f'catalogo-guardar-{etiqueta}')
        post_delete.connect(invalidar, sender=modelo, dispatch_uid=f'catalogo-borrar-{etiqueta}')
    destino = apps.get_model('destinos.Destino')
    for relacion in (destino.categorias.through, destino.servicios.through):
        m2m_changed.connect(invalidar, sender=relacion, dispatch_uid=f'catalogo-m2m-{relacion._meta.label}')
