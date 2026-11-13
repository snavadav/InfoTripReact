"""Carga de lugares desde un CSV: qué entra, qué queda oculto y qué se omite por duplicado. No consulta la red."""
import csv
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .management.commands.importar_csv import COLUMNAS
from .models import Destino, Lugar, Municipio, Region

SIC = 'Sistema de Información Cultural / Secretaría de Cultura'


def fila(numero, nombre, **campos):
    base = dict.fromkeys(COLUMNAS, '')
    base.update(nombre=nombre, municipio='Tapalpa', estado='Jalisco', latitud='19.9450', longitud='-103.7570',
                categoria='Restaurantes', modelo_sugerido='Lugar', tipo='comer', subtipo='restaurant',
                fuente_nombre='OpenStreetMap', fuente_id=f'node/{numero}',
                fuente_url=f'https://www.openstreetmap.org/node/{numero}', fecha_consulta='2026-11-13')
    base.update(campos)
    return base


def templo(numero, nombre, **campos):
    return fila(numero, nombre, categoria='Iglesias y templos', modelo_sugerido='Destino', tipo='', subtipo='', **campos)


class ImportarCsvTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nombre='Sierra', slug='sierra')
        self.municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=region)

    def importar(self, *filas, columnas=None, **opciones):
        with tempfile.NamedTemporaryFile('w', suffix='.csv', encoding='utf-8-sig', newline='', delete=False) as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=columnas or sorted(COLUMNAS), extrasaction='ignore')
            escritor.writeheader()
            escritor.writerows(filas)
        self.addCleanup(os.remove, archivo.name)
        salida = StringIO()
        call_command('importar_csv', archivo.name, stdout=salida, **opciones)
        return salida.getvalue()

    def test_los_lugares_se_publican_y_los_destinos_quedan_ocultos(self):
        texto = self.importar(
            fila(1, 'Fonda Lupita', telefono='33 1234', sitio_web='javascript:alert(1)', direccion='Juárez 5',
                 horario='Mo-Su 09:00-18:00'),
            templo(2, 'Templo de San Antonio', latitud='19.9500'),
        )
        self.assertIn('Creados 1 lugares y 1 destinos ocultos, de 2 filas', texto)
        fonda = Lugar.objects.get()
        self.assertEqual((fonda.tipo, fonda.subtipo, fonda.osm_id, fonda.municipio, fonda.telefono, fonda.sitio_web,
                          fonda.direccion, fonda.horario, fonda.es_activo),
                         ('comer', 'restaurant', 'node/1', self.municipio, '33 1234', '', 'Juárez 5',
                          'Mo-Su 09:00-18:00', True))
        destino = Destino.objects.get()
        self.assertFalse(destino.es_activo)
        self.assertEqual((destino.slug, destino.osm_id, destino.horario), ('templo-de-san-antonio', 'node/2', ''))
        self.assertIn('Templo en Tapalpa, Jalisco. Todavía no tenemos una descripción', destino.descripcion)
        self.assertEqual([categoria.nombre for categoria in destino.categorias.all()], ['Ciudad y cultura'])
        # Nada oculto se asoma en el sitio.
        self.assertNotContains(self.client.get('/destinos/'), 'Templo de San Antonio')

    def test_lo_del_sistema_de_informacion_cultural_lleva_su_cita(self):
        self.importar(fila(754, 'Casa de la Cultura', categoria='Centros culturales', modelo_sugerido='Destino',
                           tipo='', subtipo='', fuente_nombre=SIC, fuente_id='centro_cultural/754',
                           fuente_url='https://sic.cultura.gob.mx/ficha.php?table=centro_cultural&table_id=754',
                           horario='Lunes a viernes de 9 a 15 h', direccion='Mina 18',
                           horario_fuente_url='https://sic.cultura.gob.mx/ficha.php?table=centro_cultural&table_id=754'))
        destino = Destino.objects.get()
        self.assertIsNone(destino.osm_id)
        self.assertIn(f'Fuente: {SIC} (https://sic.cultura.gob.mx/ficha.php?table=centro_cultural&table_id=754), '
                      'consultado el 2026-11-13.', destino.descripcion)
        self.assertEqual((destino.horario, destino.direccion, str(destino.horario_fecha_consulta)),
                         ('Lunes a viernes de 9 a 15 h', 'Mina 18', '2026-11-13'))
        self.assertTrue(destino.horario_fuente_url.startswith('https://sic.cultura.gob.mx/'))

    def test_no_duplica_por_clave_ni_por_nombre_cercano(self):
        Lugar.objects.create(nombre='Otro nombre', tipo='comer', subtipo='restaurant', latitud=19.9, longitud=-103.7,
                             osm_id='node/1')
        Destino.objects.create(nombre='Oculto por el equipo', slug='oculto', descripcion='-', municipio=self.municipio,
                               latitud=19.9, longitud=-103.7, osm_id='node/2', es_activo=False)
        Lugar.objects.create(nombre='Mercado Corona', tipo='comer', subtipo='marketplace', latitud=19.9451,
                             longitud=-103.7570)
        texto = self.importar(
            fila(1, 'Fonda Lupita'),
            templo(2, 'Templo Oculto'),
            fila(3, 'Mercado Corona Tapalpa', subtipo='marketplace', categoria='Mercados'),
            fila(4, 'Mercado Corona', subtipo='marketplace', categoria='Mercados', latitud='19.9700'),
            fila(5, 'Café Uno', subtipo='cafe'), fila(6, 'Café Uno', subtipo='cafe'),
        )
        self.assertIn('Creados 2 lugares y 0 destinos ocultos', texto)
        self.assertIn('misma clave de OpenStreetMap: 2.', texto)
        self.assertIn('Mismo nombre a menos de 150 m de algo que ya existe: 2.', texto)
        nuevos = Lugar.objects.filter(osm_id__in=['node/3', 'node/4', 'node/5', 'node/6'])
        self.assertEqual(set(nuevos.values_list('osm_id', flat=True)), {'node/4', 'node/5'})
        # Lo que el equipo ocultó sigue oculto.
        self.assertFalse(Destino.objects.get(osm_id='node/2').es_activo)

    def test_repetir_no_crea_nada(self):
        filas = [fila(1, 'Fonda Lupita'), templo(2, 'Templo de San Antonio', latitud='19.95'),
                 templo(9, 'Capilla', fuente_nombre=SIC, fuente_id='catedral/9', latitud='19.96')]
        self.importar(*filas)
        self.assertIn('Creados 0 lugares y 0 destinos ocultos', self.importar(*filas))
        self.assertEqual((Lugar.objects.count(), Destino.objects.count()), (1, 2))

    def test_solo_los_tipos_utiles_para_viajar(self):
        texto = self.importar(
            fila(1, 'Nieves de Garrafa', categoria='Heladerías', subtipo=''),
            fila(2, 'Cabañas El Pino', categoria='Cabañas', tipo='dormir', subtipo='', latitud='19.95'),
            fila(3, 'Carnes Selectas', categoria='Carnicerías', tipo='comprar', subtipo='', latitud='19.96'),
            fila(4, 'Algo Raro', categoria='Otra cosa', modelo_sugerido='Destino', tipo='', subtipo='', latitud='19.97'),
        )
        self.assertEqual(set(Lugar.objects.values_list('nombre', 'tipo', 'subtipo')),
                         {('Nieves de Garrafa', 'comer', 'ice_cream'), ('Cabañas El Pino', 'dormir', 'chalet')})
        self.assertIn('Tipo de lugar que no se importa: 2.', texto)
        self.assertFalse(Destino.objects.exists())

    def test_omite_filas_sin_datos_o_fuera_de_jalisco(self):
        texto = self.importar(fila(1, ''), fila(2, 'Lejos', latitud='25.0'), fila(3, 'Mal', latitud='norte'),
                              fila(4, 'Otro estado', estado='Colima'), fila(5, 'Fonda Buena'))
        self.assertIn('Creados 1 lugares', texto)
        self.assertIn('Sin nombre, municipio o coordenadas válidas en Jalisco: 4.', texto)

    def test_simular_no_guarda(self):
        self.assertIn('Se crearían 1 lugares y 1 destinos ocultos',
                      self.importar(fila(1, 'Fonda'), templo(2, 'Templo', latitud='19.95'), simular=True))
        self.assertFalse(Lugar.objects.exists() or Destino.objects.exists())

    def test_rechaza_un_archivo_que_no_es_el_esperado(self):
        with self.assertRaisesMessage(CommandError, 'faltan columnas'):
            self.importar(fila(1, 'Fonda'), columnas=['nombre', 'latitud'])
        with self.assertRaisesMessage(CommandError, 'ninguna fila'):
            self.importar()
        with self.assertRaisesMessage(CommandError, 'No se pudo leer'):
            call_command('importar_csv', 'no-existe.csv', stdout=StringIO())
