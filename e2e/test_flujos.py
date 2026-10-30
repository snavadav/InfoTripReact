"""Flujos reales en Chromium: ejecutan el JavaScript y fallan ante cualquier violación de CSP o error de página.

Requieren navegador:  playwright install chromium
Ejecución:            E2E=1 python manage.py test e2e --settings=infotrip.settings.test
"""
import os
import re
from unittest import skipUnless

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core import mail
from django.core.cache import cache

from apps.comunidad.models import Viaje
from apps.destinos.models import Destino, Municipio, Region
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario

CLAVE = 'Prueba-segura-493!'


@skipUnless(os.environ.get('E2E'), 'Pruebas de navegador: definir E2E=1')
class FlujosTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        # Playwright síncrono corre sobre un bucle de eventos; Django lo interpreta como contexto asíncrono.
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
        from playwright.sync_api import sync_playwright
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.navegador = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.navegador.close()
        cls.playwright.stop()
        super().tearDownClass()
        os.environ.pop('DJANGO_ALLOW_ASYNC_UNSAFE', None)

    def setUp(self):
        cache.clear()
        region = Region.objects.create(nombre='Sierra', slug='sierra')
        municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=region)
        self.destino = Destino.objects.create(nombre='Mirador', slug='mirador', municipio=municipio,
                                              descripcion='Lugar de prueba', latitud=19.9, longitud=-103.7)
        self.usuario = Usuario.objects.create_user('ana@example.com', 'Ana', 'Prueba', CLAVE, es_verificado=True)
        self.problemas = []
        self.contexto = self.navegador.new_context()
        self.pagina = self.contexto.new_page()
        self.pagina.on('pageerror', lambda error: self.problemas.append(f'Error de página: {error}'))
        self.pagina.on('console', self.revisar_consola)
        self.pagina.on('response', self.revisar_respuesta)

    def tearDown(self):
        # Espera a las peticiones en curso: si la prueba termina antes, la base se vacía bajo ellas.
        self.pagina.wait_for_load_state('networkidle')
        self.contexto.close()
        self.assertEqual(self.problemas, [])

    def revisar_consola(self, mensaje):
        if 'Content Security Policy' in mensaje.text:
            self.problemas.append(mensaje.text)

    def revisar_respuesta(self, respuesta):
        if respuesta.status >= 500:
            self.problemas.append(f'{respuesta.status} en {respuesta.url}')

    def abrir(self, ruta):
        self.pagina.goto(self.live_server_url + ruta)

    def iniciar_sesion(self):
        self.abrir('/login/')
        self.completar_login()

    def completar_login(self):
        self.pagina.fill('#email', self.usuario.email)
        self.pagina.fill('#password', CLAVE)
        self.pagina.click('#submitBtn')
        self.pagina.wait_for_selector('#codeForm:not([hidden])')
        self.pagina.fill('#loginCode', re.search(r'[0-9]{6}', mail.outbox[-1].body).group())
        self.pagina.click('#verifyBtn')
        self.pagina.wait_for_url(lambda url: '/login/' not in url)

    def test_paginas_publicas_sin_violaciones_de_csp(self):
        for ruta in ['/', '/destinos/', '/destinos/mirador/', '/destinos/mirador/costos/', '/costos/', '/login/', '/registro/', '/api/v1/docs/', '/no-existe/']:
            with self.subTest(ruta=ruta):
                self.abrir(ruta)
                self.pagina.wait_for_load_state('load')

    def test_el_mapa_de_la_portada_se_puede_abrir(self):
        self.abrir('/')
        self.pagina.click('#map-mode')
        self.pagina.wait_for_selector('#preview-map[src*="maps.google.com"]', state='visible')

    def test_sesion_en_cookie_y_no_en_localstorage(self):
        self.iniciar_sesion()
        visibles = self.pagina.evaluate('[Object.keys(localStorage), document.cookie]')
        self.assertEqual(visibles[0], ['usuario'])
        self.assertNotIn('infotrip_refresh', visibles[1])
        cookie = next(c for c in self.contexto.cookies() if c['name'] == 'infotrip_refresh')
        self.assertTrue(cookie['httpOnly'])
        # Una página nueva recupera la sesión desde la cookie.
        self.abrir('/perfil/')
        self.pagina.wait_for_selector('#profile-content:not([hidden])')
        self.assertIn(self.usuario.email, self.pagina.inner_text('#profile-email'))

    def test_registro_en_un_paso_y_vuelve_a_la_ficha(self):
        self.abrir('/destinos/mirador/')
        self.pagina.click('#nav-guest a[href*="/registro/"]')
        self.pagina.fill('#nombre', 'Nueva')
        self.pagina.fill('#email', 'nueva@example.com')
        self.pagina.fill('#password', CLAVE)
        self.pagina.check('#showPassword')
        self.assertEqual(self.pagina.get_attribute('#password', 'type'), 'text')
        self.pagina.click('#submitBtn')
        self.pagina.wait_for_selector('#codeForm:not([hidden])')
        self.pagina.fill('#loginCode', re.search(r'[0-9]{6}', mail.outbox[-1].body).group())
        self.pagina.click('#verifyBtn')
        self.pagina.wait_for_url(self.live_server_url + '/destinos/mirador/')
        self.assertTrue(Usuario.objects.get(email='nueva@example.com').es_verificado)

    def test_dispositivo_recordado_entra_solo_con_contrasena(self):
        self.abrir('/login/')
        self.pagina.fill('#email', self.usuario.email)
        self.pagina.fill('#password', CLAVE)
        self.pagina.click('#submitBtn')
        self.pagina.wait_for_selector('#codeForm:not([hidden])')
        self.pagina.fill('#loginCode', re.search(r'[0-9]{6}', mail.outbox[-1].body).group())
        self.pagina.check('#rememberDevice')
        self.pagina.click('#verifyBtn')
        self.pagina.wait_for_url(self.live_server_url + '/')
        self.pagina.click('#logoutBtn')
        self.pagina.wait_for_selector('#nav-guest', state='visible')
        cache.clear()
        enviados = len(mail.outbox)
        self.abrir('/login/')
        self.pagina.fill('#email', self.usuario.email)
        self.pagina.fill('#password', CLAVE)
        self.pagina.click('#submitBtn')
        self.pagina.wait_for_url(self.live_server_url + '/')
        self.assertEqual(len(mail.outbox), enviados)

    def test_compartir_una_ficha_y_una_escapada(self):
        self.contexto.grant_permissions(['clipboard-read', 'clipboard-write'], origin=self.live_server_url)
        self.pagina.add_init_script("Object.defineProperty(navigator, 'share', {value: undefined})")
        self.abrir('/destinos/mirador/')
        self.pagina.click('#share-place')
        self.pagina.wait_for_selector('#favorite-status:has-text("Enlace copiado")')
        self.assertIn('/destinos/mirador/?ref=compartido', self.pagina.evaluate('navigator.clipboard.readText()'))

        viaje = Viaje.objects.create(autor=self.usuario, nombre='Con amigos', destino='Tapalpa', personas=4,
                                     presupuesto=1000, fecha_inicio='2026-12-01', fecha_fin='2026-12-02',
                                     notas='Nota privada')
        self.iniciar_sesion()
        self.abrir('/mis-viajes/')
        self.pagina.locator('.trip-card button', has_text='Compartir').first.click()
        self.pagina.wait_for_selector('#trip-status:has-text("Enlace copiado")')
        enlace = self.pagina.evaluate('navigator.clipboard.readText()')
        viaje.refresh_from_db()
        self.assertIn(str(viaje.enlace_publico), enlace)
        anonimo = self.navegador.new_context()
        pagina = anonimo.new_page()
        pagina.goto(enlace)
        self.assertIn('Con amigos', pagina.inner_text('main'))
        self.assertNotIn('Nota privada', pagina.content())
        anonimo.close()
        self.pagina.wait_for_load_state('networkidle')

    def test_los_botones_de_mis_viajes_se_pueden_pulsar(self):
        Viaje.objects.create(autor=self.usuario, nombre='Editable', destino='Tapalpa', personas=1, presupuesto=1,
                             fecha_inicio='2026-12-01', fecha_fin='2026-12-02')
        self.iniciar_sesion()
        self.abrir('/mis-viajes/')
        self.pagina.locator('.trip-card button', has_text='Editar').click()
        self.assertEqual(self.pagina.input_value('[name="nombre"]'), 'Editable')
        self.pagina.on('dialog', lambda dialogo: dialogo.accept())
        self.pagina.locator('.trip-card button', has_text='Eliminar').click()
        self.pagina.wait_for_selector('#trip-status:has-text("eliminada")')
        self.assertFalse(Viaje.objects.exists())

    def test_reportar_un_gasto_desde_la_pagina_de_costos(self):
        self.abrir('/destinos/mirador/costos/')
        self.pagina.click('a[href$="#reportar-gasto"]')
        self.pagina.wait_for_selector('#contribution-form select[name="concepto"]', state='visible')
        self.assertEqual(self.pagina.input_value('#contribution-form select[name="tipo"]'), 'gasto')
        self.pagina.wait_for_load_state('networkidle')
        self.assertTrue(Evento.objects.filter(nombre='costos_vista', destino='mirador').exists())

    def test_tras_iniciar_sesion_vuelve_a_la_ficha(self):
        self.abrir('/destinos/mirador/')
        self.pagina.click('#favorite-toggle')
        self.pagina.click('#favorite-status a')
        self.completar_login()
        self.pagina.wait_for_url(self.live_server_url + '/destinos/mirador/')

    def test_next_externo_no_redirige_fuera_del_sitio(self):
        self.abrir('/login/?next=https://ajeno.example/')
        self.completar_login()
        self.pagina.wait_for_url(self.live_server_url + '/')

    def test_el_borrador_del_viaje_sobrevive_a_iniciar_sesion(self):
        self.abrir('/mis-viajes/')
        self.pagina.fill('[name="nombre"]', 'Fin de semana')
        self.pagina.fill('[name="destino"]', 'Tapalpa')
        self.pagina.fill('[name="fecha_inicio"]', '2026-12-01')
        self.pagina.fill('[name="fecha_fin"]', '2026-12-02')
        self.pagina.fill('[name="personas"]', '2')
        self.pagina.fill('[name="presupuesto"]', '1500')
        self.pagina.click('#add-expense')
        self.pagina.fill('.trip-expense [name="descripcion"]', 'Gasolina')
        self.pagina.fill('.trip-expense [name="monto"]', '500')
        self.pagina.click('#trip-login a')
        self.completar_login()
        self.pagina.wait_for_url(self.live_server_url + '/mis-viajes/')
        self.assertEqual(self.pagina.input_value('[name="nombre"]'), 'Fin de semana')
        self.assertEqual(self.pagina.input_value('.trip-expense [name="descripcion"]'), 'Gasolina')
        self.pagina.click('#trip-form button[type="submit"]')
        self.pagina.wait_for_selector('#trip-form .form-status:has-text("guardada")')
        self.assertEqual(self.usuario.viajes.get().nombre, 'Fin de semana')
        self.assertIsNone(self.pagina.evaluate("localStorage.getItem('infotrip_borrador_viaje')"))

    def test_en_movil_los_resultados_se_ven_sin_desplazarse_y_se_puede_tocar(self):
        self.pagina.set_viewport_size({'width': 375, 'height': 812})
        self.abrir('/destinos/')
        self.pagina.wait_for_selector('.trip-card', state='attached')
        self.assertLess(self.pagina.locator('.trip-card').first.bounding_box()['y'], 812)
        self.assertFalse(self.pagina.locator('#filters-panel').evaluate('panel => panel.open'))
        self.assertEqual(self.pagina.evaluate('document.documentElement.scrollWidth'), 375)
        self.abrir('/destinos/?q=mirador')
        self.assertTrue(self.pagina.locator('#filters-panel').evaluate('panel => panel.open'))
        self.abrir('/')
        pequenos = self.pagina.evaluate('''[...document.querySelectorAll('main button, main input, main select')]
            .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.height < 44; }).length''')
        self.assertEqual(pequenos, 0)
        chat = self.pagina.locator('#trip-chat-toggle').bounding_box()
        self.assertLessEqual(chat['width'], 56)
        self.assertEqual(self.pagina.get_by_role('button', name='¿Planeamos tu viaje?').count(), 1)

    def test_el_teclado_muestra_el_foco(self):
        self.abrir('/login/')
        self.pagina.keyboard.press('Tab')
        estilo = self.pagina.evaluate('getComputedStyle(document.activeElement).outlineStyle')
        self.assertEqual(estilo, 'solid')

    def test_guardar_favorito_y_cerrar_sesion(self):
        self.iniciar_sesion()
        self.abrir('/destinos/mirador/')
        self.pagina.wait_for_selector('#favorite-toggle:not([disabled])')
        self.pagina.click('#favorite-toggle')
        self.pagina.wait_for_selector('#favorite-status:has-text("Guardado")')
        self.abrir('/favoritos/')
        self.pagina.wait_for_selector('#favorites-list h2')
        self.pagina.click('#logoutBtn')
        self.pagina.wait_for_url(self.live_server_url + '/')
        self.abrir('/perfil/')
        self.pagina.wait_for_selector('#profile-login:not([hidden])')
