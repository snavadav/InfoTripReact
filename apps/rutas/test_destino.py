"""Planeador 2.0, paso A1: a dónde vas (corredor, tipos de viaje, punto final) y el aviso de tiempo."""
from django.core.cache import cache
from django.test import SimpleTestCase
from django.utils.text import slugify
from rest_framework.test import APITestCase

from apps.destinos.models import Categoria, Destino, Lugar, Municipio, Region
from .optimizador import Dia, Problema, decodificar, genetico, voraz
from .servicio import MARGEN_CORREDOR_KM, RADIO_KM, advertencia_tiempo, lejania
from .test_optimizador import ORIGEN, SABADO, cerca, claves, h, sitio
from .test_planeador import proximo

URL = '/api/v1/rutas/planear/'


class PuntoFinalTests(SimpleTestCase):
    def test_solo_ida_termina_en_el_destino(self):
        final = cerca(60)
        # A mitad del camino y fuera de él (al sur, detrás de la salida).
        problema = Problema(ORIGEN, [Dia(SABADO, h(9), h(18))], [sitio('camino', km=30), sitio('atras', km=-30)],
                            regresar=False, final=final)
        plan = decodificar(problema, [0, 1])
        # Visitar "atrás" y luego llegar al final no cabe en el día... o sí: lo que importa es que se cuente el tramo.
        self.assertIn('camino', claves(problema, plan)[0])
        ultimo = problema.sitios.index(next(s for s in problema.sitios if s.clave == claves(problema, plan)[0][-1]))
        tramo_final = problema.km[ultimo + 1][problema.nodo_final]
        self.assertAlmostEqual(plan.km, sum(p.km for p in plan.dias[0]) + tramo_final, places=6)

    def test_no_visita_lo_que_impide_llegar_al_final(self):
        # 150 km al sur y el destino 150 km al norte: ir y luego llegar no cabe en 9 horas.
        problema = Problema(ORIGEN, [Dia(SABADO, h(9), h(18))], [sitio('sur', km=-150, duracion=30)],
                            regresar=False, final=cerca(150))
        self.assertEqual(claves(problema, decodificar(problema, [0])), [[]])
        # Sin punto final, en cambio, sí se puede ir.
        libre = Problema(ORIGEN, [Dia(SABADO, h(9), h(18))], [sitio('sur', km=-150, duracion=30)], regresar=False)
        self.assertEqual(claves(libre, decodificar(libre, [0])), [['sur']])

    def test_los_dias_anteriores_dejan_tiempo_para_llegar(self):
        # Día 1 libre, pero el día 2 solo tiene 4 horas: ir 150 km al sur el día 1 dejaría el final (200 km al
        # norte) a más de 4 horas.
        dias = [Dia(SABADO, h(9), h(18)), Dia(6, h(9), h(13))]
        problema = Problema(ORIGEN, dias, [sitio('sur', km=-150, duracion=30), sitio('norte', km=150, duracion=30)],
                            regresar=False, final=cerca(200))
        visitados = [c for dia in claves(problema, decodificar(problema, [0, 1])) for c in dia]
        self.assertNotIn('sur', visitados)
        self.assertIn('norte', visitados)

    def test_regresar_sigue_igual_sin_punto_final(self):
        lejos = [sitio('lejos', km=150, duracion=60)]
        con_regreso = Problema(ORIGEN, [Dia(SABADO, h(9), h(14))], lejos)
        self.assertEqual(claves(con_regreso, decodificar(con_regreso, [0])), [[]])
        self.assertIsNone(con_regreso.nodo_final)

    def test_quedarse_en_el_destino_sale_y_vuelve_cada_dia(self):
        final = cerca(100)
        sitios = [sitio('camino', km=50), sitio('junto_al_destino', km=105)]
        n = len(sitios) + 1
        dias = [Dia(SABADO, h(9), h(18), hasta=n), Dia(6, h(9), h(18), desde=n, hasta=n)]
        problema = Problema(ORIGEN, dias, sitios, regresar=False, final=final)
        plan = genetico(problema, semilla=1)
        self.assertEqual(sorted(c for d in claves(problema, plan) for c in d), ['camino', 'junto_al_destino'])
        # El día 2 empieza en el destino: su primera parada queda cerca.
        if plan.dias[1]:
            self.assertLess(plan.dias[1][0].km, 10)

    def test_el_hibrido_nunca_queda_debajo_del_voraz_con_punto_final(self):
        sitios = [sitio(i, km=(i * 13) % 90 - 20, puntaje=1 + i % 3, duracion=45 + (i % 4) * 15) for i in range(18)]
        problema = Problema(ORIGEN, [Dia(SABADO, h(9), h(18)), Dia(6, h(9), h(18))], sitios, regresar=False,
                            final=cerca(80))
        for semilla in range(1, 6):
            self.assertGreaterEqual(genetico(problema, semilla=semilla).aptitud, voraz(problema).aptitud - 1e-9)


class CorredorTests(SimpleTestCase):
    def test_circulo_como_siempre(self):
        self.assertAlmostEqual(lejania(ORIGEN, cerca(40), 1), 40 / RADIO_KM[1], places=2)
        self.assertIsNone(lejania(ORIGEN, cerca(90), 1))

    def test_corredor_entre_salida_y_destino(self):
        destino = cerca(120)
        # En el camino: sin desvío.
        self.assertAlmostEqual(lejania(ORIGEN, cerca(60), 1, 'ida', destino), 0, places=2)
        # Detrás de la salida: desvío de 2 × 40 km, fuera del margen de un día.
        self.assertIsNone(lejania(ORIGEN, cerca(-40), 1, 'ida', destino))
        # Más días, margen más amplio: a 20 km de la salida hacia atrás, el desvío es 40 km.
        self.assertIsNone(lejania(ORIGEN, cerca(-20), 1, 'ida', destino))
        self.assertIsNotNone(lejania(ORIGEN, cerca(-20), 2, 'ida', destino))
        self.assertLess(MARGEN_CORREDOR_KM[1], MARGEN_CORREDOR_KM[2])

    def test_base_suma_el_circulo_alrededor_del_destino(self):
        destino = cerca(120)
        # 40 km más allá del destino: fuera del corredor de un día, dentro del círculo del destino.
        self.assertIsNone(lejania(ORIGEN, cerca(160), 1, 'ida', destino))
        self.assertIsNotNone(lejania(ORIGEN, cerca(160), 2, 'base', destino))


class AdvertenciaTests(SimpleTestCase):
    destino = {'nombre': 'Lejos', 'punto': cerca(400)}

    def test_avisa_si_el_trayecto_no_cabe(self):
        # 400 km en línea recta son unas 8 h de manejo; un día de 6 h no alcanza.
        texto = advertencia_tiempo(ORIGEN, 'Guadalajara', self.destino, 1, h(9), h(15), 'ida')
        self.assertIn('Guadalajara', texto)
        self.assertIn('más días', texto)
        self.assertIsNone(advertencia_tiempo(ORIGEN, 'Guadalajara', self.destino, 2, h(9), h(15), 'ida'))

    def test_ida_y_vuelta_cuenta_el_regreso(self):
        texto = advertencia_tiempo(ORIGEN, 'Guadalajara', self.destino, 2, h(9), h(15), 'ida_vuelta')
        self.assertIn('ida y vuelta', texto)

    def test_sin_destino_no_avisa(self):
        self.assertIsNone(advertencia_tiempo(ORIGEN, 'Guadalajara', None, 1, h(9), h(10), 'circulo'))


class PlanearConDestinoTests(APITestCase):
    def setUp(self):
        cache.clear()
        region = Region.objects.create(nombre='Sur', slug='sur')
        self.gdl = Municipio.objects.create(nombre='Guadalajara', slug='guadalajara', region=region)
        self.tapalpa = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=region)
        self.lejos = Municipio.objects.create(nombre='Puerto Vallarta', slug='puerto-vallarta', region=region)
        pueblos = Categoria.objects.create(nombre='Pueblos', slug='pueblos')
        self.naturaleza = Categoria.objects.create(nombre='Naturaleza', slug='naturaleza')

        def destino(nombre, municipio, lat, lng, categoria=pueblos):
            nuevo = Destino.objects.create(nombre=nombre, slug=slugify(nombre), municipio=municipio, descripcion='-',
                                           latitud=lat, longitud=lng)
            nuevo.categorias.add(categoria)
            return nuevo

        destino('Plaza de Guadalajara', self.gdl, 20.6767, -103.3475)
        destino('Pueblo de Tapalpa', self.tapalpa, 19.9450, -103.7580)
        destino('Piedras Bola', self.tapalpa, 19.9700, -103.7200, self.naturaleza)
        # En el camino entre Guadalajara y Tapalpa (Acatlán de Juárez, más o menos).
        destino('Mirador del camino', self.gdl, 20.4200, -103.5900, self.naturaleza)
        # Lejos de todo lo demás: fuera del corredor.
        destino('Malecón', self.lejos, 20.6100, -105.2350)
        Lugar.objects.create(nombre='Hotel del Bosque', tipo='dormir', subtipo='hotel', latitud=19.9460,
                             longitud=-103.7570)

    def peticion(self, **cambios):
        datos = {'municipio': 'guadalajara', 'fecha': proximo(5).isoformat(), 'dias': 2, 'hora_inicio': '09:00',
                 'hora_fin': '19:00', 'intereses': ['pueblos', 'naturaleza'], 'personas': 2, **cambios}
        return self.client.post(URL, datos, format='json')

    def nombres(self, plan):
        return [p['destino']['nombre'] for dia in plan['dias'] for p in dia['paradas']]

    def test_sin_destino_como_siempre(self):
        plan = self.peticion(dias=1).json()
        self.assertEqual(plan['viaje']['modo'], 'circulo')
        self.assertIsNone(plan['viaje']['destino'])
        # Tapalpa queda a más de 80 km: fuera del círculo de un día.
        self.assertNotIn('Pueblo de Tapalpa', self.nombres(plan))

    def test_solo_ida_llega_al_destino_y_visita_en_el_camino(self):
        respuesta = self.peticion(dias=1, destino='municipio:tapalpa', modo='ida')
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        plan = respuesta.json()
        nombres = self.nombres(plan)
        self.assertIn('Mirador del camino', nombres)
        self.assertIn('Pueblo de Tapalpa', nombres)
        self.assertNotIn('Malecón', nombres)
        self.assertEqual(plan['viaje']['destino']['nombre'], 'Tapalpa')
        self.assertFalse(plan['viaje']['regresar'])
        # Google Maps del último día termina en el destino del viaje, no en la última parada ni en la salida.
        url = plan['dias'][-1]['google_maps']['url']
        self.assertIn('destination=19.9', url.replace('%2C', ','))
        # Solo ida: la noche es en el destino.
        self.assertEqual(plan['dias'][-1]['dormir']['nombre'], 'Hotel del Bosque')

    def test_destino_concreto_es_parada_obligatoria(self):
        plan = self.peticion(dias=1, destino='destino:piedras-bola', modo='ida_vuelta').json()
        self.assertIn('Piedras Bola', self.nombres(plan))
        self.assertTrue(plan['viaje']['regresar'])

    def test_quedarse_duerme_en_el_destino(self):
        plan = self.peticion(destino='municipio:tapalpa', modo='base').json()
        self.assertEqual(plan['viaje']['modo'], 'base')
        self.assertEqual([d['dormir']['nombre'] for d in plan['dias']], ['Hotel del Bosque'] * 2)
        # Desde el día 2, las paradas están alrededor del destino.
        for parada in plan['dias'][1]['paradas']:
            self.assertLess(abs(parada['destino']['latitud'] - 19.95), 0.5)

    def test_advertencia_si_no_da_tiempo(self):
        plan = self.peticion(dias=1, hora_inicio='09:00', hora_fin='13:00', destino='municipio:puerto-vallarta',
                             modo='ida_vuelta').json()
        self.assertIn('más días', plan['viaje']['advertencia'])
        self.assertEqual(plan['avisos'][0], plan['viaje']['advertencia'])
        cerca_ = self.peticion(dias=1, destino='municipio:tapalpa', modo='ida').json()
        self.assertIsNone(cerca_['viaje']['advertencia'])

    def test_validacion(self):
        casos = [
            ({'destino': 'municipio:tapalpa', 'modo': 'base', 'dias': 1}, 'modo'),
            ({'modo': 'ida'}, 'destino'),
            ({'destino': 'municipio:no-existe', 'modo': 'ida'}, 'destino'),
            ({'destino': 'tapalpa', 'modo': 'ida'}, 'destino'),
            ({'destino': 'municipio:tapalpa', 'modo': 'circulo'}, 'modo'),
            ({'destino': 'municipio:tapalpa', 'modo': 'volar'}, 'modo'),
        ]
        for cambios, campo in casos:
            with self.subTest(cambios=cambios):
                respuesta = self.peticion(**cambios)
                self.assertEqual(respuesta.status_code, 400)
                self.assertIn(campo, respuesta.json())
        # Con destino y sin tipo de viaje: ida y vuelta.
        self.assertEqual(self.peticion(destino='municipio:tapalpa').json()['viaje']['modo'], 'ida_vuelta')

    def test_el_buscador_da_lo_que_el_planeador_necesita(self):
        resultados = self.client.get('/api/v1/sugerencias/', {'q': 'tapalpa'}).json()['resultados']
        por_tipo = {r['tipo']: r for r in resultados}
        self.assertEqual(por_tipo['municipio']['slug'], 'tapalpa')
        self.assertAlmostEqual(por_tipo['municipio']['latitud'], (19.945 + 19.97) / 2, places=3)
        destinos = {r['slug']: r for r in resultados if r['tipo'] == 'destino'}
        self.assertEqual(destinos['pueblo-de-tapalpa']['latitud'], 19.945)

    def test_la_ruta_compartida_guarda_el_destino(self):
        respuesta = self.client.post('/api/v1/rutas/compartidas/', {
            'municipio': 'guadalajara', 'fecha': proximo(5).isoformat(), 'dias': 1, 'hora_inicio': '09:00',
            'hora_fin': '19:00', 'intereses': ['pueblos'], 'destino': 'municipio:tapalpa', 'modo': 'ida'},
            format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        self.assertTrue(respuesta.json()['titulo'].endswith('a Tapalpa'))
        pagina = self.client.get(respuesta.json()['url'])
        self.assertContains(pagina, 'Pueblo de Tapalpa')
        self.assertContains(pagina, '"modo": "ida"')
