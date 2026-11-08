import csv
import math
import tempfile
from io import StringIO
from pathlib import Path

import joblib
import numpy as np
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.destinos.models import Destino, Lugar, Municipio, Region
from apps.usuarios.models import Usuario

from .caracteristicas import (
    _coordenadas_de_destinos, acuerdo_entre_personas, etiquetas_por_lugar, fila, km_al_destino_mas_cercano,
)
from .models import EtiquetaLugar, PrediccionLugar
from .modelo import entrenar, evaluar, medidas, probabilidad_de_servir

SIRVEN = ['Restaurante La Hacienda', 'Hotel Plaza', 'Cafe del Centro', 'Mariscos El Puerto', 'Hotel Real',
          'Restaurante Los Arcos', 'Cafe Tapalpa', 'Posada del Sol', 'Restaurante El Mirador', 'Hotel Colonial']
NO_SIRVEN = ['Comedor Industrial Planta Norte', 'Distribuidora de Alimentos SA', 'Comedor Industrial Sur',
             'Distribuidora Regional', 'Comedor Empresa Textil']


def fila_de(nombre, **cambios):
    return {'nombre': nombre, 'tipo': 'comer', 'subtipo': 'restaurant', 'fuente': 'denue', 'tiene_telefono': 1,
            'tiene_web': 0, 'tiene_horario': 0, 'tiene_direccion': 1, 'metropolitana': 0, 'log_km_destino': 1.0,
            'palabras': len(nombre.split()), **cambios}


def conjunto():
    """Datos de prueba para el código, no de entrenamiento real: el nombre decide la clase."""
    filas, etiquetas = [], []
    for i in range(4):
        filas += [fila_de(f'{n} {i}') for n in SIRVEN] + [fila_de(f'{n} {i}') for n in NO_SIRVEN]
        etiquetas += [True] * len(SIRVEN) + [False] * len(NO_SIRVEN)
    return filas, etiquetas


class ModeloTests(SimpleTestCase):
    def test_el_modelo_con_nombre_supera_a_la_regla_actual(self):
        resultados = evaluar(*conjunto())
        self.assertEqual(resultados['regla_actual']['exhaustividad_no_sirve'], 0)
        self.assertGreater(resultados['modelo_completo']['f1_no_sirve'], 0.9)
        self.assertGreater(resultados['modelo_completo']['f1_no_sirve'], resultados['modelo_sin_nombre']['f1_no_sirve'])

    def test_entrenado_reconoce_nombres_nuevos_sin_acentos_ni_mayusculas(self):
        modelo = entrenar(*conjunto())
        sirve, no_sirve = probabilidad_de_servir(modelo, [fila_de('HOTEL DEL LAGO'), fila_de('Comedor Industrial Oeste')])
        self.assertGreater(sirve, 0.5)
        self.assertLess(no_sirve, 0.5)

    def test_medidas_sobre_la_clase_no_sirve(self):
        m = medidas([True, True, False, False], [0.9, 0.2, 0.1, 0.8])
        self.assertEqual((m['verdaderos_no'], m['falsos_no'], m['no_detectados'], m['verdaderos_si']), (1, 1, 1, 1))
        self.assertEqual(m['precision_no_sirve'], 0.5)
        self.assertTrue(math.isnan(medidas([True, True], [0.9, 0.8])['auc']))

    def test_distancia_al_destino_mas_cercano(self):
        destinos = np.radians(np.array([[20.0, -103.0], [21.0, -103.0]]))
        self.assertAlmostEqual(km_al_destino_mas_cercano(20.1, -103.0, destinos), 11.1, delta=0.1)
        self.assertEqual(km_al_destino_mas_cercano(20.0, -103.0, np.empty((0, 2))), 500.0)


class DatosTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nombre='C', slug='c')
        self.gdl = Municipio.objects.create(nombre='Guadalajara', slug='guadalajara', region=region)
        Destino.objects.create(nombre='Centro', slug='centro', municipio=self.gdl, descripcion='-', latitud=20.67,
                               longitud=-103.35)
        self.personas = [Usuario.objects.create_user(f'p{i}@example.com', 'P', 'Q', 'x') for i in range(3)]

    def lugar(self, nombre, **campos):
        return Lugar.objects.create(nombre=nombre, tipo='comer', subtipo='restaurant', latitud='20.67',
                                    longitud='-103.35', municipio=self.gdl, **campos)

    def test_fila_del_lugar(self):
        datos = fila(self.lugar('Birria Don Chuy', denue_id='9', telefono='33'), _coordenadas_de_destinos())
        self.assertEqual((datos['fuente'], datos['tiene_telefono'], datos['tiene_web'], datos['metropolitana']),
                         ('denue', 1, 0, 1))
        self.assertLess(datos['log_km_destino'], 0.1)

    def test_mayoria_sin_empates_ni_no_se(self):
        a, b, c, d = (self.lugar(n) for n in 'ABCD')
        respuestas = {a: [True, True, False], b: [True, False], c: [None, False], d: [None]}
        for lugar, votos in respuestas.items():
            for persona, util in zip(self.personas, votos):
                EtiquetaLugar.objects.create(lugar=lugar, autor=persona, util=util)
        self.assertEqual(etiquetas_por_lugar(), {a.pk: True, c.pk: False})

    def test_acuerdo_entre_personas(self):
        self.assertIsNone(acuerdo_entre_personas())
        for i in range(40):
            lugar = self.lugar(f'L{i}')
            EtiquetaLugar.objects.create(lugar=lugar, autor=self.personas[0], util=i % 2 == 0)
            EtiquetaLugar.objects.create(lugar=lugar, autor=self.personas[1], util=i % 2 == 0 if i < 36 else i % 2 == 1)
        n, observado, kappa = acuerdo_entre_personas()
        self.assertEqual((n, observado), (40, 0.9))
        self.assertAlmostEqual(kappa, 0.8)


class EntrenarCuradorTests(TestCase):
    def setUp(self):
        self.persona = Usuario.objects.create_user('p@example.com', 'P', 'Q', 'x')

    def etiquetar(self, nombres, util):
        for nombre in nombres:
            lugar = Lugar.objects.create(nombre=nombre, tipo='comer', subtipo='restaurant', latitud='20.6',
                                         longitud='-103.3')
            EtiquetaLugar.objects.create(lugar=lugar, autor=self.persona, util=util)

    def test_sin_etiquetas_suficientes_lo_dice(self):
        self.etiquetar(['Hotel Plaza'], True)
        with self.assertRaisesMessage(CommandError, 'Faltan etiquetas'):
            call_command('entrenar_curador', stdout=StringIO())

    def test_mide_entrena_y_guarda(self):
        for i in range(5):
            self.etiquetar([f'{n} {i}' for n in SIRVEN], True)
            self.etiquetar([f'{n} {i}' for n in NO_SIRVEN[:4]], False)
        with tempfile.TemporaryDirectory() as carpeta:
            ruta, reporte = Path(carpeta) / 'm' / 'curador.joblib', Path(carpeta) / 'r.csv'
            salida = StringIO()
            call_command('entrenar_curador', modelo=str(ruta), reporte=str(reporte), minimo=40, stdout=salida)
            guardado = joblib.load(ruta)
            self.assertEqual(guardado['etiquetas'], 70)
            with open(reporte, encoding='utf-8') as archivo:
                metodos = [f['metodo'] for f in csv.DictReader(archivo)]
        self.assertEqual(metodos, ['regla_actual', 'modelo_sin_nombre', 'modelo_completo'])
        self.assertIn('modelo_completo', salida.getvalue())


class AplicarCuradorTests(TestCase):
    """Entrena con datos de prueba, califica todos los lugares y usa las predicciones para elegir dudas."""

    def setUp(self):
        self.persona = Usuario.objects.create_superuser('p@example.com', 'P', 'Q', 'Prueba-segura-493!')
        for i in range(5):
            for nombre, util in [(n, True) for n in SIRVEN] + [(n, False) for n in NO_SIRVEN[:4]]:
                lugar = Lugar.objects.create(nombre=f'{nombre} {i}', tipo='comer', subtipo='restaurant',
                                             latitud='20.6', longitud='-103.3')
                EtiquetaLugar.objects.create(lugar=lugar, autor=self.persona, util=util)
        self.nuevo_no = Lugar.objects.create(nombre='Comedor Industrial Poniente', tipo='comer',
                                             subtipo='restaurant', latitud='20.6', longitud='-103.3')
        self.nuevo_si = Lugar.objects.create(nombre='Hotel del Lago', tipo='comer', subtipo='restaurant',
                                             latitud='20.6', longitud='-103.3')
        self.carpeta = tempfile.TemporaryDirectory()
        self.ruta = str(Path(self.carpeta.name) / 'curador.joblib')
        call_command('entrenar_curador', modelo=self.ruta, minimo=40, stdout=StringIO())

    def tearDown(self):
        self.carpeta.cleanup()

    def test_califica_todo_sin_ocultar_nada_y_se_puede_repetir(self):
        salida = StringIO()
        call_command('aplicar_curador', modelo=self.ruta, stdout=salida)
        call_command('aplicar_curador', modelo=self.ruta, stdout=StringIO())
        self.assertEqual(PrediccionLugar.objects.count(), Lugar.objects.count())
        self.nuevo_no.refresh_from_db()
        self.nuevo_si.refresh_from_db()
        self.assertLess(self.nuevo_no.prediccion.probabilidad, self.nuevo_si.prediccion.probabilidad)
        self.assertTrue(Lugar.objects.filter(pk=self.nuevo_no.pk, es_activo=True).exists())
        self.assertIn('probablemente no le sirven', salida.getvalue())

    def test_sin_modelo_lo_dice(self):
        with self.assertRaisesMessage(CommandError, 'entrenar_curador'):
            call_command('aplicar_curador', modelo=str(Path(self.carpeta.name) / 'no.joblib'), stdout=StringIO())

    def test_modo_dudas_elige_el_caso_mas_indeciso_y_el_admin_lo_lista(self):
        call_command('aplicar_curador', modelo=self.ruta, stdout=StringIO())
        dudoso = Lugar.objects.create(nombre='Lugar X', tipo='comer', subtipo='restaurant', latitud='20.6',
                                      longitud='-103.3')
        PrediccionLugar.objects.create(lugar=dudoso, probabilidad=0.51, version=1)
        self.client.force_login(self.persona)
        self.assertContains(self.client.get('/admin/etiquetar-lugares/?modo=dudas'), 'Lugar X')
        respuesta = self.client.post('/admin/etiquetar-lugares/', {'lugar': dudoso.pk, 'respuesta': 'si',
                                                                    'modo': 'dudas'})
        self.assertRedirects(respuesta, '/admin/etiquetar-lugares/?modo=dudas', fetch_redirect_response=False)
        self.assertNotContains(self.client.get('/admin/etiquetar-lugares/?modo=dudas'), 'Lugar X')
        PrediccionLugar.objects.filter(lugar=self.nuevo_no).update(probabilidad=0.1)
        PrediccionLugar.objects.filter(lugar=self.nuevo_si).update(probabilidad=0.9)
        lista = self.client.get('/admin/curador/prediccionlugar/?rango=no')
        self.assertContains(lista, 'Comedor Industrial Poniente')
        self.assertContains(lista, '10%')
        self.assertNotContains(lista, 'Hotel del Lago')

    def test_sin_modelo_el_modo_dudas_usa_la_muestra(self):
        PrediccionLugar.objects.all().delete()
        self.client.force_login(self.persona)
        respuesta = self.client.get('/admin/etiquetar-lugares/?modo=dudas')
        self.assertEqual(respuesta.context['modo'], 'muestra')
        self.assertIn(respuesta.context['lugar'], (self.nuevo_no, self.nuevo_si))
        self.assertNotContains(respuesta, 'casos dudosos')
