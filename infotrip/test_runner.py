"""Ejecutor de pruebas: cada prueba empieza con la caché vacía.

Las pruebas deshacen la base de datos al terminar, pero no la caché local: sin esto, lo guardado del catálogo
(apps/destinos/cache_catalogo.py) o un contador de límites de una prueba podría verse en la siguiente.
"""
import unittest

from django.core.cache import caches
from django.test.runner import DiscoverRunner


class ResultadoConCacheLimpia(unittest.TextTestResult):
    def startTest(self, test):
        for cache in caches.all():
            cache.clear()
        super().startTest(test)


class Ejecutor(DiscoverRunner):
    def get_resultclass(self):
        # Con --pdb, --debug-sql o --parallel, Django usa su propio resultado y la caché no se vacía.
        return super().get_resultclass() or ResultadoConCacheLimpia
