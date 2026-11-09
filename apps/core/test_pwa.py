"""App instalable: manifiesto, service worker y página sin conexión (apps/core/pwa.py)."""
import json
import re
from unittest import mock

from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings

from apps.core import pwa


def precache_de(codigo):
    return json.loads(re.search(r'^const PRECACHE = (.*);$', codigo, re.M).group(1))


def version_de(codigo):
    return re.search(r'^const VERSION = "(\w+)";$', codigo, re.M).group(1)


class ManifiestoTests(TestCase):
    def test_responde_con_su_tipo_y_los_iconos_existen(self):
        respuesta = self.client.get('/manifest.webmanifest')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/manifest+json')
        datos = json.loads(respuesta.content)
        self.assertEqual(datos['short_name'], 'InfoTrip')
        self.assertEqual((datos['start_url'], datos['scope'], datos['display']), ('/', '/', 'standalone'))
        self.assertEqual(datos['theme_color'], '#FFFFFF')
        tamanos = {(icono['sizes'], icono['purpose']) for icono in datos['icons']}
        self.assertEqual(tamanos, {('192x192', 'any'), ('512x512', 'any'), ('512x512', 'maskable')})
        for icono in datos['icons']:
            self.assertTrue(finders.find(icono['src'].removeprefix('/static/')), icono['src'])

    def test_las_paginas_enlazan_el_manifiesto_y_registran_el_service_worker(self):
        html = self.client.get('/privacidad/').content.decode()
        self.assertIn('<link rel="manifest" href="/manifest.webmanifest">', html)
        self.assertIn('/static/js/pwa.js', html)
        self.assertIn('rel="apple-touch-icon"', html)

    def test_la_csp_permite_el_service_worker_y_el_manifiesto_propios(self):
        csp = self.client.get('/privacidad/')['Content-Security-Policy']
        self.assertIn("worker-src 'self'", csp)
        self.assertIn("manifest-src 'self'", csp)


class ServiceWorkerTests(TestCase):
    def setUp(self):
        pwa.configuracion_fija.cache_clear()
        self.addCleanup(pwa.configuracion_fija.cache_clear)

    def test_se_sirve_desde_la_raiz_sin_cache_larga(self):
        respuesta = self.client.get('/sw.js')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'text/javascript; charset=utf-8')
        self.assertEqual(respuesta['Cache-Control'], 'no-cache, max-age=0')

    def test_su_csp_le_deja_descargar_los_cuadros_del_mapa(self):
        csp = self.client.get('/sw.js')['Content-Security-Policy']
        self.assertIn("default-src 'none'", csp)
        self.assertIn('connect-src', csp)
        self.assertIn('https://tile.openstreetmap.org', csp)

    def test_guarda_la_pagina_sin_conexion_y_los_estaticos_propios(self):
        precache = precache_de(self.client.get('/sw.js').content.decode())
        self.assertEqual(precache[0], '/sin-conexion/')
        for archivo in ('/static/css/style.css', '/static/js/tema.js', '/static/js/pwa.js',
                        '/static/js/sin-conexion.js', '/static/images/app/icono-192.png'):
            self.assertIn(archivo, precache)
        self.assertFalse([url for url in precache if url.startswith(('/api/', '/admin/', '/media/'))])
        self.assertFalse([url for url in precache if url.endswith('.map') or '/static/admin/' in url])

    def test_nunca_toca_la_api_el_admin_ni_las_paginas_personales(self):
        codigo = self.client.get('/sw.js').content.decode()
        intocables = re.search(r'const RUTAS_INTOCABLES = \[(.*?)\];', codigo).group(1)
        for ruta in (r'/^\/api\//', r'/^\/admin\//', r'/^\/media\//'):
            self.assertIn(ruta, intocables)
        self.assertIn("if (peticion.method !== 'GET') return;", codigo)
        guardables = re.search(r'const PAGINAS_GUARDABLES = \[(.*?)\];', codigo, re.S).group(1)
        for privada in ('perfil', 'favoritos', 'mis-viajes', 'escapadas', 'botes', 'login', 'registro'):
            self.assertNotIn(privada, guardables)
        # El pasaporte propio sí (llega sin datos personales); el compartido de otra persona no.
        self.assertIn(r'/^\/pasaporte\/$/', guardables)

    def test_la_version_cambia_cuando_cambia_un_estatico(self):
        primera = version_de(self.client.get('/sw.js').content.decode())
        pwa.configuracion_fija.cache_clear()
        self.assertEqual(version_de(self.client.get('/sw.js').content.decode()), primera)

        # En producción ManifestStaticFilesStorage da otro nombre al archivo cuando cambia su contenido.
        def con_hash(ruta):
            return f'/static/{ruta}'.replace('style.css', 'style.0123abcd.css')
        pwa.configuracion_fija.cache_clear()
        with mock.patch.object(pwa, 'static', con_hash):
            codigo = self.client.get('/sw.js').content.decode()
        self.assertIn('/static/css/style.0123abcd.css', precache_de(codigo))
        self.assertNotEqual(version_de(codigo), primera)

    @override_settings(DEBUG=False)
    def test_en_produccion_se_calcula_una_sola_vez(self):
        with mock.patch.object(pwa, 'calcular_configuracion', wraps=pwa.calcular_configuracion) as calcular:
            self.client.get('/sw.js')
            self.client.get('/sw.js')
        self.assertEqual(calcular.call_count, 1)

    def test_solo_get(self):
        self.assertEqual(self.client.post('/sw.js').status_code, 405)
        self.assertEqual(self.client.post('/manifest.webmanifest').status_code, 405)


class SinConexionTests(TestCase):
    def test_pagina_amable_que_lista_lo_guardado(self):
        respuesta = self.client.get('/sin-conexion/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Estás sin conexión')
        self.assertContains(respuesta, 'id="paginasGuardadas"')
        self.assertContains(respuesta, '/static/js/sin-conexion.js')
        self.assertContains(respuesta, '<meta name="robots" content="noindex">')
