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

from apps.destinos.models import Destino, Municipio, Region
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

    def tearDown(self):
        self.contexto.close()
        self.assertEqual(self.problemas, [])

    def revisar_consola(self, mensaje):
        if 'Content Security Policy' in mensaje.text:
            self.problemas.append(mensaje.text)

    def abrir(self, ruta):
        self.pagina.goto(self.live_server_url + ruta)

    def iniciar_sesion(self):
        self.abrir('/login/')
        self.pagina.fill('#email', self.usuario.email)
        self.pagina.fill('#password', CLAVE)
        self.pagina.click('#submitBtn')
        self.pagina.wait_for_selector('#codeForm:not([hidden])')
        self.pagina.fill('#loginCode', re.search(r'[0-9]{6}', mail.outbox[-1].body).group())
        self.pagina.click('#verifyBtn')
        self.pagina.wait_for_url(lambda url: '/login/' not in url)

    def test_paginas_publicas_sin_violaciones_de_csp(self):
        for ruta in ['/', '/destinos/', '/destinos/mirador/', '/login/', '/registro/', '/api/v1/docs/', '/no-existe/']:
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
