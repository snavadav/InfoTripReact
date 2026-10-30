"""Función "¿Cuánto cuesta ir a…?": cifras honestas a partir de gastos reportados."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.comunidad.models import Aporte
from apps.comunidad.selectors import MINIMO_REPORTES, costos_de_destino, costos_por_destino
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario
from .models import Destino, Municipio, Region


@override_settings(PUBLIC_BASE_URL='https://infotrip.example')
class CostosBase(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.autor = Usuario.objects.create_user('a@example.com', 'Ana', 'P', 'Prueba-segura-493!')
        self.municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa',
                                                  region=Region.objects.create(nombre='Sierra', slug='sierra'))
        self.destino = self.crear_destino('Mirador')

    def crear_destino(self, nombre):
        return Destino.objects.create(nombre=nombre, slug=nombre.lower(), municipio=self.municipio, descripcion='-',
                                      latitud=20, longitud=-103)

    def gasto(self, concepto, monto, destino=None, dias=5, **cambios):
        datos = dict(autor=self.autor, destino=destino or self.destino, tipo='gasto', texto='Gasto', concepto=concepto,
                     monto=monto, fecha_visita=self.hoy - timedelta(days=dias), estado='publicado')
        return Aporte.objects.create(**{**datos, **cambios})

    def gastos(self, concepto, montos, destino=None):
        for monto in montos:
            self.gasto(concepto, monto, destino)

    def concepto(self, costos, clave):
        return next(fila for fila in costos['conceptos'] if fila['clave'] == clave)


class CalculoTests(CostosBase):
    def test_mediana_y_rango_resisten_un_valor_exagerado(self):
        self.gastos('comida', [100, 120, 5000])
        fila = self.concepto(costos_de_destino(self.destino), 'comida')
        self.assertTrue(fila['suficiente'])
        self.assertEqual((fila['mediana'], fila['minimo'], fila['maximo'], fila['cantidad']),
                         (Decimal(120), Decimal(100), Decimal(5000), 3))

    def test_con_pocos_reportes_no_se_publica_ninguna_cifra(self):
        self.gastos('comida', [100] * (MINIMO_REPORTES - 1))
        costos = costos_de_destino(self.destino)
        fila = self.concepto(costos, 'comida')
        self.assertFalse(fila['suficiente'])
        self.assertIsNone(fila['mediana'])
        self.assertEqual(fila['cantidad'], MINIMO_REPORTES - 1)
        self.assertFalse(costos['hay_datos'])
        self.assertIsNone(costos['dia'])

    def test_solo_cuentan_gastos_publicados_recientes_y_de_cuentas_activas(self):
        self.gastos('comida', [100, 100])
        self.gasto('comida', 999, dias=400)
        self.gasto('comida', 999, estado='pendiente')
        inactiva = Usuario.objects.create_user('i@example.com', 'I', 'P', 'Prueba-segura-493!', es_activo=False)
        self.gasto('comida', 999, autor=inactiva)
        self.assertEqual(self.concepto(costos_de_destino(self.destino), 'comida')['cantidad'], 2)

    def test_el_dia_tipico_suma_lo_disponible_y_el_alojamiento_va_aparte(self):
        self.gastos('entrada', [50, 50, 50])
        self.gastos('comida', [200, 200, 200])
        self.gastos('transporte', [10, 10])
        self.gastos('alojamiento', [900, 1000, 1100])
        costos = costos_de_destino(self.destino)
        self.assertEqual(costos['dia']['total'], Decimal(250))
        self.assertEqual(costos['dia']['incluye'], ['entrada', 'comida'])
        self.assertEqual(costos['alojamiento']['mediana'], Decimal(1000))

    def test_un_solo_concepto_no_es_un_dia_tipico(self):
        self.gastos('comida', [200, 200, 200])
        costos = costos_de_destino(self.destino)
        self.assertTrue(costos['hay_datos'])
        self.assertIsNone(costos['dia'])

    def test_el_indice_calcula_todo_en_una_consulta(self):
        for nombre in ['Uno', 'Dos', 'Tres']:
            self.gastos('comida', [100, 110, 120], self.crear_destino(nombre))
        with self.assertNumQueries(1):
            resultado = costos_por_destino()
        self.assertEqual(len(resultado), 3)


class PaginasTests(CostosBase):
    def test_ficha_de_costos_con_datos(self):
        self.gastos('comida', [100, 150, 200])
        self.gastos('entrada', [50, 50, 50])
        respuesta = self.client.get('/destinos/mirador/costos/')
        self.assertContains(respuesta, '¿Cuánto cuesta ir a Mirador?')
        self.assertContains(respuesta, '$150 MXN')
        self.assertContains(respuesta, 'Un día típico por persona')
        self.assertContains(respuesta, '<title>¿Cuánto cuesta ir a Mirador? Gastos reales de viajeros — InfoTrip</title>')
        self.assertContains(respuesta, 'Un día típico cuesta cerca de $200 MXN por persona')
        self.assertContains(respuesta, 'data-costos="mirador"')
        self.assertNotContains(respuesta, 'noindex')

    def test_sin_datos_lo_dice_y_no_se_indexa(self):
        respuesta = self.client.get('/destinos/mirador/costos/')
        self.assertContains(respuesta, 'Todavía no hay suficientes reportes')
        self.assertContains(respuesta, '<meta name="robots" content="noindex">')
        self.assertContains(respuesta, '/destinos/mirador/#reportar-gasto')

    def test_destino_oculto_o_inexistente_da_404(self):
        Destino.objects.filter(pk=self.destino.pk).update(es_activo=False)
        self.assertEqual(self.client.get('/destinos/mirador/costos/').status_code, 404)
        self.assertEqual(self.client.get('/destinos/nada/costos/').status_code, 404)

    def test_el_texto_de_la_comunidad_no_llega_a_la_pagina(self):
        self.gastos('comida', [100, 100, 100])
        Aporte.objects.update(texto='Texto privado de un aporte')
        self.assertNotContains(self.client.get('/destinos/mirador/costos/'), 'Texto privado')

    def test_indice_compara_por_concepto_sin_ranking_y_omite_los_sin_datos(self):
        self.gastos('comida', [500, 500, 500])
        otro = self.crear_destino('Zapotlan')
        self.gastos('alojamiento', [900, 900, 900], otro)
        arroyo = self.crear_destino('Arroyo')
        self.gastos('comida', [100, 100, 100], arroyo)
        self.crear_destino('Vacio')
        respuesta = self.client.get('/costos/')
        filas = respuesta.context['filas']
        self.assertEqual([fila['destino'].nombre for fila in filas], ['Arroyo', 'Mirador', 'Zapotlan'])
        # Entrada, comida, alojamiento y transporte, en el orden de los encabezados.
        self.assertEqual(respuesta.context['encabezados'][1], 'Comida por persona')
        self.assertEqual(filas[0]['montos'], [None, Decimal(100), None, None])
        self.assertEqual(filas[2]['montos'], [None, None, Decimal(900), None])
        self.assertNotContains(respuesta, 'Vacio')

    def test_indice_vacio_invita_a_aportar(self):
        self.assertContains(self.client.get('/costos/'), 'Todavía no hay destinos con suficientes reportes')

    def test_la_ficha_y_el_listado_enlazan_a_los_costos(self):
        self.assertContains(self.client.get('/destinos/mirador/'), 'href="/destinos/mirador/costos/"')
        self.assertContains(self.client.get('/destinos/mirador/'), 'id="reportar-gasto"')
        self.assertContains(self.client.get('/destinos/'), 'href="/costos/"')

    def test_sitemap_solo_incluye_costos_con_datos(self):
        self.gastos('comida', [100, 100, 100])
        self.crear_destino('Vacio')
        respuesta = self.client.get('/sitemap.xml')
        self.assertContains(respuesta, '/destinos/mirador/costos/</loc>')
        self.assertContains(respuesta, '/costos/</loc>')
        self.assertNotContains(respuesta, '/destinos/vacio/costos/')

    def test_el_evento_de_la_pagina_se_acepta(self):
        respuesta = self.client.post('/api/v1/eventos/', {'nombre': 'costos_vista', 'destino': 'mirador'},
                                     content_type='application/json')
        self.assertEqual(respuesta.status_code, 204)
        self.assertEqual(Evento.objects.get().destino, 'mirador')
