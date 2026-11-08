"""El experimento que compara los métodos: CSV, resumen y prueba de signos."""
import csv
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.destinos.models import Categoria, Destino, Municipio, Region
from .management.commands.experimento_rutas import prueba_de_signos


class PruebaDeSignosTests(SimpleTestCase):
    def test_valores_conocidos(self):
        self.assertEqual(prueba_de_signos(0, 0), 1.0)
        self.assertEqual(prueba_de_signos(5, 5), 1.0)
        # Diez de diez a favor: 2 × (1/2)^10.
        self.assertAlmostEqual(prueba_de_signos(10, 0), 2 / 1024)
        self.assertEqual(prueba_de_signos(3, 7), prueba_de_signos(7, 3))


class ExperimentoTests(TestCase):
    def setUp(self):
        municipio = Municipio.objects.create(nombre='Guadalajara', slug='guadalajara',
                                             region=Region.objects.create(nombre='Centro', slug='centro'))
        cultura = Categoria.objects.create(nombre='Ciudad y cultura', slug='ciudad-y-cultura')
        for i in range(6):
            destino = Destino.objects.create(nombre=f'Museo {i}', slug=f'museo-{i}', municipio=municipio,
                                             descripcion='-', latitud=20.67 + i / 200, longitud=-103.34)
            destino.categorias.add(cultura)

    def test_escribe_cada_corrida_y_el_resumen(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, 'experimento.csv')
            salida = StringIO()
            call_command('experimento_rutas', corridas=2, escenarios=1, salida=ruta, stdout=salida)
            with open(ruta, encoding='utf-8') as archivo:
                filas = list(csv.DictReader(archivo))
        # Un voraz y dos corridas de cada genético.
        self.assertEqual([f['metodo'] for f in filas], ['voraz'] + ['genetico_puro'] * 2 + ['genetico_hibrido'] * 2)
        self.assertEqual({f['candidatos'] for f in filas}, {'6'})
        texto = salida.getvalue()
        self.assertIn('genetico_hibrido: mejora', texto)
        self.assertIn('prueba de signos p =', texto)

    def test_misma_semilla_mismo_resultado(self):
        def correr():
            with tempfile.TemporaryDirectory() as carpeta:
                ruta = os.path.join(carpeta, 'experimento.csv')
                call_command('experimento_rutas', corridas=2, escenarios=1, salida=ruta, stdout=StringIO())
                with open(ruta, encoding='utf-8') as archivo:
                    return [(f['metodo'], f['semilla'], f['aptitud'], f['km']) for f in csv.DictReader(archivo)]
        self.assertEqual(correr(), correr())

    def test_sin_datos(self):
        Destino.objects.all().delete()
        Municipio.objects.all().delete()
        with self.assertRaises(CommandError):
            call_command('experimento_rutas', corridas=1, escenarios=1, stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('experimento_rutas', corridas=0, stdout=StringIO())
