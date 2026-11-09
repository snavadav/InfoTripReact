"""Referencias oficiales de costo: precios publicados por una fuente, siempre citados y aparte de los viajeros."""
import csv
import os
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.comunidad.models import Aporte
from apps.comunidad.selectors import MINIMO_REPORTES, costos_de_destino
from apps.usuarios.models import Usuario
from .management.commands.cargar_referencias_costo import ARCHIVO, COLUMNAS
from .models import Destino, Municipio, ReferenciaCosto, Region

SIC = 'Sistema de Información Cultural, Secretaría de Cultura'


class ReferenciasBase(TestCase):
    def setUp(self):
        municipio = Municipio.objects.create(nombre='Teuchitlán', slug='teuchitlan',
                                             region=Region.objects.create(nombre='Valles', slug='valles'))
        self.destino = Destino.objects.create(nombre='Guachimontones', slug='guachimontones', municipio=municipio,
                                              descripcion='-', latitud=20.69, longitud=-103.83)

    def referencia(self, **cambios):
        datos = dict(destino=self.destino, concepto='entrada', monto=Decimal(30), descripcion='Entrada general',
                     fuente_nombre=SIC, fuente_url='https://sic.cultura.gob.mx/ficha.php?table=museo&table_id=1841',
                     fecha_consulta=date(2026, 11, 9), fecha_fuente=date(2026, 9, 29))
        return ReferenciaCosto.objects.create(**{**datos, **cambios})


class ModeloTests(ReferenciasBase):
    def test_se_describe_con_destino_concepto_y_monto(self):
        self.assertEqual(str(self.referencia()), 'Guachimontones · Entrada · $30')

    def test_no_admite_montos_negativos(self):
        with self.assertRaises(ValidationError):
            ReferenciaCosto(destino=self.destino, concepto='entrada', monto=Decimal(-1), descripcion='x',
                            fuente_nombre=SIC, fuente_url='https://example.org', fecha_consulta=date(2026, 11, 9)
                            ).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.referencia(monto=Decimal(-1))

    def test_la_misma_cita_no_se_duplica(self):
        self.referencia()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.referencia(monto=Decimal(40))

    def test_entrada_libre_es_monto_cero(self):
        self.referencia(monto=Decimal(0), descripcion='Entrada libre')
        self.assertEqual(self.destino.referencias_costo.get(descripcion='Entrada libre').monto, Decimal(0))


FILA = {'destino': 'guachimontones', 'concepto': 'entrada', 'monto': '30', 'descripcion': 'Entrada general',
        'fuente_nombre': SIC, 'fuente_url': 'https://sic.cultura.gob.mx/ficha.php?table=museo&table_id=1841',
        'fecha_consulta': '2026-11-09', 'fecha_fuente': '2026-09-29'}


class CargaTests(ReferenciasBase):
    def cargar(self, *filas, columnas=COLUMNAS):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, 'r.csv')
            with open(ruta, 'w', encoding='utf-8', newline='') as salida:
                escritor = csv.DictWriter(salida, fieldnames=columnas)
                escritor.writeheader()
                escritor.writerows(filas)
            texto = StringIO()
            call_command('cargar_referencias_costo', archivo=ruta, stdout=texto)
            return texto.getvalue()

    def test_carga_con_su_cita_y_fechas(self):
        self.cargar(FILA, {**FILA, 'descripcion': 'Museo, entrada libre', 'monto': '0', 'fecha_fuente': ''})
        referencia = ReferenciaCosto.objects.get(descripcion='Entrada general')
        self.assertEqual((referencia.destino, referencia.monto, referencia.fuente_nombre),
                         (self.destino, Decimal(30), SIC))
        self.assertEqual((referencia.fecha_consulta, referencia.fecha_fuente), (date(2026, 11, 9), date(2026, 9, 29)))
        self.assertIsNone(ReferenciaCosto.objects.get(monto=0).fecha_fuente)

    def test_repetir_la_carga_actualiza_sin_duplicar(self):
        self.cargar(FILA)
        salida = self.cargar({**FILA, 'monto': '35', 'fecha_consulta': '2026-11-01'})
        self.assertIn('0 referencias creadas y 1 actualizadas', salida)
        referencia = ReferenciaCosto.objects.get()
        self.assertEqual((referencia.monto, referencia.fecha_consulta), (Decimal(35), date(2026, 11, 1)))

    def test_omite_destinos_que_no_existen_y_lo_avisa(self):
        salida = self.cargar(FILA, {**FILA, 'destino': 'no-existe'})
        self.assertIn('no-existe', salida)
        self.assertEqual(ReferenciaCosto.objects.count(), 1)

    def test_una_fila_invalida_impide_toda_la_carga(self):
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        invalidas = [{'monto': '-5'}, {'monto': 'treinta'}, {'concepto': 'propina'}, {'fuente_url': 'http://x.org'},
                     {'fuente_url': ''}, {'fecha_consulta': ''}, {'fecha_consulta': manana}, {'fecha_fuente': '9/29'},
                     {'descripcion': ''}]
        for cambio in invalidas:
            with self.subTest(cambio), self.assertRaisesMessage(CommandError, 'Línea 3'):
                self.cargar({**FILA, 'descripcion': 'Otra'}, {**FILA, **cambio})
        self.assertFalse(ReferenciaCosto.objects.exists())

    def test_exige_las_columnas_esperadas(self):
        with self.assertRaisesMessage(CommandError, 'Columnas esperadas'):
            self.cargar({'destino': 'guachimontones'}, columnas=['destino'])

    def test_avisa_si_no_encuentra_el_archivo(self):
        with self.assertRaisesMessage(CommandError, 'No se pudo leer'):
            call_command('cargar_referencias_costo', archivo='no-existe.csv', stdout=StringIO())


class ArchivoVersionadoTests(SimpleTestCase):
    """El CSV del repositorio: cada fila con fuente oficial https, fecha y un concepto válido."""
    def setUp(self):
        with open(ARCHIVO, encoding='utf-8', newline='') as entrada:
            lector = csv.DictReader(entrada)
            self.columnas, self.filas = lector.fieldnames, list(lector)

    def test_tiene_las_columnas_y_filas_completas(self):
        self.assertEqual(self.columnas, COLUMNAS)
        self.assertTrue(self.filas)
        conceptos = {clave for clave, _ in ReferenciaCosto.CONCEPTOS}
        for fila in self.filas:
            with self.subTest(destino=fila['destino'], descripcion=fila['descripcion']):
                self.assertIn(fila['concepto'], conceptos)
                self.assertGreaterEqual(Decimal(fila['monto']), 0)
                self.assertTrue(fila['fuente_url'].startswith('https://'))
                self.assertTrue(fila['fuente_nombre'] and fila['descripcion'])
                self.assertLessEqual(date.fromisoformat(fila['fecha_consulta']), timezone.localdate())
                if fila['fecha_fuente']:
                    self.assertLessEqual(date.fromisoformat(fila['fecha_fuente']), date.fromisoformat(fila['fecha_consulta']))

    def test_las_fuentes_son_oficiales(self):
        dominios = ('https://sic.cultura.gob.mx/', 'https://app.sct.gob.mx/', 'https://pot.capufe.mx/',
                    'https://www.siteur.gob.mx/')
        for fila in self.filas:
            self.assertTrue(fila['fuente_url'].startswith(dominios), fila['fuente_url'])

    def test_sin_citas_repetidas(self):
        citas = [(f['destino'], f['concepto'], f['descripcion'], f['fuente_url']) for f in self.filas]
        self.assertEqual(len(citas), len(set(citas)))


@override_settings(PUBLIC_BASE_URL='https://infotrip.example')
class PaginasTests(ReferenciasBase):
    URL = '/destinos/guachimontones/costos/'

    def gastos(self, concepto, montos):
        autor = Usuario.objects.create_user(f'{concepto}@example.com', 'Ana', 'P', 'Prueba-segura-493!')
        for monto in montos:
            Aporte.objects.create(autor=autor, destino=self.destino, tipo='gasto', texto='Gasto', concepto=concepto,
                                  monto=monto, fecha_visita=timezone.localdate() - timedelta(days=5),
                                  estado='publicado')

    def test_la_ficha_muestra_la_referencia_con_fuente_y_fechas(self):
        self.referencia()
        self.referencia(monto=Decimal(0), descripcion='Museo vecino, entrada libre', fecha_fuente=None)
        respuesta = self.client.get(self.URL)
        self.assertContains(respuesta, '<h2 id="referencia-oficial">Referencia oficial</h2>', html=False)
        self.assertContains(respuesta, 'Precio oficial publicado; puede haber cambiado.')
        self.assertContains(respuesta, '$30 MXN')
        self.assertContains(respuesta, 'Sin costo')
        self.assertContains(respuesta, 'href="https://sic.cultura.gob.mx/ficha.php?table=museo&amp;table_id=1841"')
        self.assertContains(respuesta, 'fecha de la fuente: 29/09/2026 · consultada el 09/11/2026')
        self.assertContains(respuesta, 'consultada el 09/11/2026', count=2)

    def test_sin_referencias_no_aparece_la_seccion(self):
        self.assertNotContains(self.client.get(self.URL), 'Referencia oficial')

    def test_no_cuenta_para_el_minimo_de_reportes_ni_para_la_mediana(self):
        self.gastos('entrada', [100] * (MINIMO_REPORTES - 1))
        for monto in (30, 35, 40):
            self.referencia(monto=Decimal(monto), descripcion=f'Tarifa {monto}')
        fila = next(f for f in costos_de_destino(self.destino)['conceptos'] if f['clave'] == 'entrada')
        self.assertEqual((fila['cantidad'], fila['suficiente']), (MINIMO_REPORTES - 1, False))
        respuesta = self.client.get(self.URL)
        self.assertContains(respuesta, 'Todavía no hay suficientes reportes')
        self.assertContains(respuesta, f'{MINIMO_REPORTES - 1} de {MINIMO_REPORTES} reportes necesarios')

        self.gastos('comida', [200, 200, 200])
        self.referencia(concepto='comida', monto=Decimal(5000), descripcion='Menú')
        fila = next(f for f in costos_de_destino(self.destino)['conceptos'] if f['clave'] == 'comida')
        self.assertEqual((fila['mediana'], fila['maximo'], fila['cantidad']), (Decimal(200), Decimal(200), 3))

    def test_el_indice_agrupa_por_destino_y_omite_destinos_ocultos(self):
        self.referencia()
        oculto = Destino.objects.create(nombre='Oculto', slug='oculto', municipio=self.destino.municipio,
                                        descripcion='-', latitud=20, longitud=-103, es_activo=False)
        self.referencia(destino=oculto, descripcion='No debe verse')
        respuesta = self.client.get('/costos/')
        self.assertContains(respuesta, 'Precio oficial publicado; puede haber cambiado.')
        self.assertContains(respuesta, f'<a href="{self.URL}">Guachimontones</a>')
        self.assertNotContains(respuesta, 'No debe verse')
        # Las referencias no crean filas en la comparación de viajeros.
        self.assertEqual(respuesta.context['filas'], [])
        self.assertContains(respuesta, 'Todavía no hay destinos con suficientes reportes')

    def test_el_indice_sin_referencias_no_muestra_la_seccion(self):
        self.assertNotContains(self.client.get('/costos/'), 'Referencia oficial')
