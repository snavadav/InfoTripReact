"""Flujos reales en Chromium: ejecutan el JavaScript y fallan ante cualquier violación de CSP o error de página.

Requieren navegador:  playwright install chromium
Ejecución:            E2E=1 python manage.py test e2e --settings=infotrip.settings.test
"""
import os
import re
from datetime import date
from urllib.parse import quote
from unittest import skipUnless

from io import BytesIO

from PIL import Image
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core import mail
from django.core.cache import cache

from apps.comunidad.models import Aporte, Colaboracion, Comentario, InteresNegocio, PropuestaLugar, Viaje
from apps.comunidad.moderacion import moderar
from apps.destinos.models import Categoria, Destino, Lugar, Municipio, Region
from apps.metricas.models import Evento
from apps.rutas.models import RutaCompartida
from apps.usuarios.models import Usuario

CLAVE = 'Prueba-segura-493!'
SIN_SALUDO = "try { localStorage.setItem('infotrip_axo_saludo', new Date().toLocaleDateString('en-CA')); } catch {}"
# El botón "Instalar app" (iPhone o Chrome instalable) no debe tapar nada en las demás pruebas.
SIN_INSTALAR = "try { localStorage.setItem('infotrip_instalar_cerrado', '1'); } catch {}"


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
        self.usuario = Usuario.objects.create_user('ana@example.com', 'Ana', 'Prueba', CLAVE, es_verificado=True,
                                                    username='ana')
        self.problemas = []
        self.contexto = self.nuevo_contexto()
        self.pagina = self.contexto.new_page()
        self.pagina.on('pageerror', lambda error: self.problemas.append(f'Error de página: {error}'))
        self.pagina.on('console', self.revisar_consola)
        self.pagina.on('response', self.revisar_respuesta)

    def nuevo_contexto(self, saludo=False, **opciones):
        # Playwright no ve ni intercepta lo que pide un service worker: solo la prueba de la app lo activa.
        opciones.setdefault('service_workers', 'block')
        contexto = self.navegador.new_context(**opciones)
        contexto.add_init_script(SIN_INSTALAR)
        if not saludo:
            # La burbuja de bienvenida de Axo ya salió hoy: así no tapa botones en las demás pruebas.
            contexto.add_init_script(SIN_SALUDO)
        return contexto

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
        for ruta in ['/', '/destinos/', '/destinos/mirador/', '/destinos/mirador/costos/', '/costos/', '/misiones/', '/pasaporte/', '/negocios/', '/planeador/', '/lugares/proponer/', '/login/', '/registro/', '/api/v1/docs/', '/no-existe/',
                     '/sin-conexion/']:
            with self.subTest(ruta=ruta):
                self.abrir(ruta)
                self.pagina.wait_for_load_state('load')

    def test_sin_senal_se_ve_lo_guardado_o_la_pagina_sin_conexion(self):
        self.contexto.close()
        self.contexto = self.nuevo_contexto(service_workers='allow')
        self.pagina = self.contexto.new_page()
        self.pagina.on('console', self.revisar_consola)
        self.pagina.on('response', self.revisar_respuesta)
        self.abrir('/destinos/')
        # Con clients.claim() el service worker controla la página en cuanto se activa.
        # (evaluate y no wait_for_function: este evalúa texto en la página y la CSP lo bloquea).
        self.pagina.evaluate("navigator.serviceWorker.controller || new Promise(listo =>"
                             " navigator.serviceWorker.addEventListener('controllerchange', listo))")
        self.abrir('/destinos/mirador/')
        self.pagina.wait_for_load_state('load')
        self.assertTrue(self.pagina.evaluate("caches.keys().then(n => n.some(c => c.startsWith('infotrip-paginas-')))"))

        self.contexto.set_offline(True)
        self.pagina.reload()
        self.pagina.get_by_role('heading', name='Mirador', level=1).wait_for()

        # Una página que no se visitó: la de sin conexión, con lo que sí está guardado.
        self.abrir('/misiones/')
        self.pagina.get_by_role('heading', name='Estás sin conexión').wait_for()
        guardadas = self.pagina.locator('#paginasGuardadas a')
        guardadas.first.wait_for()
        rutas = guardadas.evaluate_all('enlaces => enlaces.map(a => a.getAttribute("href"))')
        self.assertIn('/destinos/mirador/', rutas)
        # La API nunca se guarda: sin red falla aunque se haya pedido antes.
        self.assertFalse(self.pagina.evaluate(
            "caches.keys().then(async nombres => { for (const n of nombres) {"
            " for (const p of await (await caches.open(n)).keys()) if (new URL(p.url).pathname.startsWith('/api/'))"
            " return true; } return false; })"))
        self.contexto.set_offline(False)

    def test_el_mapa_de_la_portada_se_puede_abrir(self):
        self.abrir('/')
        self.pagina.click('#map-mode')
        self.pagina.wait_for_selector('#preview-map[src*="maps.google.com"]', state='visible')

    def test_sesion_en_cookie_y_no_en_localstorage(self):
        self.iniciar_sesion()
        visibles = self.pagina.evaluate('[Object.keys(localStorage), document.cookie]')
        # Fuera de la sesión solo quedan la fecha del saludo de Axo y la marca de "Instalar app" cerrado,
        # que no identifican a nadie (las pone el init script de las pruebas).
        preferencias = {'infotrip_axo_saludo', 'infotrip_instalar_cerrado'}
        self.assertEqual([clave for clave in visibles[0] if clave not in preferencias], ['usuario'])
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
        # Cuenta nueva: primero elige su nombre de usuario, con una sugerencia que aún no se guarda.
        self.pagina.wait_for_url('**/elegir-usuario/**')
        self.pagina.wait_for_selector('#usuario-disponible:has-text("@nueva está disponible")')
        self.assertIsNone(Usuario.objects.get(email='nueva@example.com').username)
        self.pagina.click('#usuario-form button[type="submit"]')
        self.pagina.wait_for_url(self.live_server_url + '/destinos/mirador/')
        nueva = Usuario.objects.get(email='nueva@example.com')
        self.assertTrue(nueva.es_verificado)
        self.assertEqual(nueva.username, 'nueva')

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
        self.pagina.click('#account-toggle')
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
        anonimo = self.nuevo_contexto()
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
        self.abrir('/destinos/?concepto=comida')
        self.assertTrue(self.pagina.locator('#filters-panel').evaluate('panel => panel.open'))
        self.abrir('/')
        pequenos = self.pagina.evaluate('''[...document.querySelectorAll('main button, main input, main select')]
            .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.height < 44; }).length''')
        self.assertEqual(pequenos, 0)
        chat = self.pagina.locator('#trip-chat-toggle').bounding_box()
        self.assertLessEqual(chat['width'], 56)
        self.assertEqual(self.pagina.get_by_role('button', name='Hablar con Axo, tu asistente de viaje').count(), 1)

    def test_el_teclado_muestra_el_foco(self):
        self.abrir('/login/')
        self.pagina.keyboard.press('Tab')
        estilo = self.pagina.evaluate('getComputedStyle(document.activeElement).outlineStyle')
        self.assertEqual(estilo, 'solid')

    def test_bote_entre_dos_personas(self):
        viaje = Viaje.objects.create(autor=self.usuario, nombre='Con amigos', destino='Tapalpa', personas=2,
                                     fecha_inicio='2026-01-01', fecha_fin='2026-01-02', presupuesto='100')
        viaje.lugares.add(self.destino)
        self.iniciar_sesion()
        self.abrir('/mis-viajes/')
        self.pagina.click('button:has-text("Bote del grupo")')
        self.pagina.wait_for_selector('#bote-contenido:not([hidden])')
        self.pagina.fill('#bote-form [name="descripcion"]', 'Cena')
        self.pagina.fill('#bote-form [name="monto"]', '300')
        self.pagina.click('#bote-form button[type="submit"]')
        self.pagina.wait_for_selector('.bote-gasto:has-text("Cena")')
        viaje.refresh_from_db()

        ana, contexto_ana = self.pagina, self.contexto
        self.contexto = self.nuevo_contexto()
        self.pagina = self.contexto.new_page()
        self.pagina.on('pageerror', lambda error: self.problemas.append(f'Error de página: {error}'))
        self.usuario = Usuario.objects.create_user('leo@example.com', 'Leo', 'Prueba', CLAVE, es_verificado=True,
                                                    username='leo')
        self.abrir(f'/botes/{viaje.enlace_bote}/')
        self.pagina.click('#bote-unirse')
        self.pagina.wait_for_url('**/login/**')
        self.completar_login()
        self.pagina.wait_for_url(f'**/botes/{viaje.enlace_bote}/')
        self.pagina.click('#bote-unirse')
        self.pagina.wait_for_selector('#bote-contenido:not([hidden])')
        self.pagina.click('#pestana-cuentas')
        self.pagina.wait_for_selector('#bote-personas:has-text("Leo (@leo) (tú)")')
        self.assertTrue(self.pagina.is_hidden('#bote-publicar'))
        self.pagina.wait_for_load_state('networkidle')
        self.contexto.close()
        self.pagina, self.contexto = ana, contexto_ana

        # Leo no estaba en el reparto de la cena; Ana la incluye y aparece la deuda.
        self.pagina.reload()
        self.pagina.wait_for_selector('#bote-contenido:not([hidden])')
        self.pagina.click('.bote-gasto button:has-text("Editar")')
        self.pagina.wait_for_selector('#bote-form-titulo:has-text("Editar")')
        self.pagina.check('#bote-entre label:has-text("Leo") input')
        self.pagina.click('#bote-form button[type="submit"]')
        self.pagina.wait_for_selector('.bote-gasto:has-text("entre todos")')
        self.pagina.click('#pestana-cuentas')
        self.pagina.wait_for_selector('#bote-transferencias:has-text("Leo le paga")')
        self.assertIn('150', self.pagina.inner_text('#bote-transferencias'))
        self.pagina.click('#pestana-gastos')
        self.pagina.click('#bote-publicar-boton')
        self.pagina.wait_for_selector('#bote-publicar-estado:has-text("1 gasto enviado")')
        self.assertTrue(Aporte.objects.get().anonimo)

    def como(self, usuario, ruta='/'):
        """Abre una sesión de `usuario` en su propio navegador y la deja como la página actual."""
        self.usuario = usuario
        self.contexto = self.nuevo_contexto()
        self.pagina = self.contexto.new_page()
        self.pagina.on('pageerror', lambda error: self.problemas.append(f'Error de página: {error}'))
        self.pagina.on('console', self.revisar_consola)
        self.pagina.on('response', self.revisar_respuesta)
        # "Ya pagué" y "Eliminar" piden confirmación con confirm().
        self.pagina.on('dialog', lambda dialogo: dialogo.accept())
        self.abrir(f'/login/?next={quote(ruta)}')
        self.completar_login()
        self.pagina.wait_for_url(f'**{ruta}')
        return self.contexto, self.pagina

    def test_tres_amigos_se_invitan_dividen_gastos_y_quedan_a_mano(self):
        crear = Usuario.objects.create_user
        ana = self.usuario
        leo = crear('leo@example.com', 'Leo', 'Prueba', CLAVE, es_verificado=True, username='leo')
        eva = crear('eva@example.com', 'Eva', 'Prueba', CLAVE, es_verificado=True, username='eva')
        Lugar.objects.create(nombre='Fonda Doña Lupe', tipo='comer', subtipo='restaurant', latitud='19.91',
                             longitud='-103.71', municipio=self.destino.municipio)
        Lugar.objects.create(nombre='Gasolinera del Bosque', tipo='gasolina', subtipo='fuel', latitud='19.92',
                             longitud='-103.72', municipio=self.destino.municipio)
        viaje = Viaje.objects.create(autor=ana, nombre='Tapalpa en grupo', destino='Tapalpa', personas=3,
                                     fecha_inicio='2026-01-01', fecha_fin='2026-01-02', presupuesto='0')
        viaje.lugares.add(self.destino)
        self.contexto.close()
        sesiones = {}

        # Ana busca a Leo y a Eva por su @usuario y les envía solicitudes.
        sesiones['ana'] = self.como(ana, '/amigos/')
        for nombre in ('leo', 'eva'):
            self.pagina.fill('#buscar-q', f'@{nombre}')
            self.pagina.click(f'#buscar-resultados button[aria-label="Enviar solicitud de amistad a @{nombre}"]')
            self.pagina.wait_for_selector(f'#lista-enviadas:has-text("@{nombre}")')
        self.assertNotIn('@example.com', self.pagina.inner_text('main'))

        # Leo y Eva aceptan.
        for usuario in (leo, eva):
            sesiones[usuario.username] = self.como(usuario, '/amigos/')
            self.pagina.click('#lista-recibidas button:has-text("Aceptar")')
            self.pagina.wait_for_selector('#lista-amigos:has-text("@ana")')

        # Ana invita a sus amigos a la escapada desde Mis viajes.
        self.contexto, self.pagina = sesiones['ana']
        self.abrir('/mis-viajes/')
        self.pagina.click('.trip-card button:has-text("Invitar amigos")')
        self.pagina.wait_for_selector('#bote-amigos-lista input')
        self.pagina.check('#bote-amigos-lista label:has-text("@leo") input')
        self.pagina.check('#bote-amigos-lista label:has-text("@eva") input')
        self.pagina.click('#bote-amigos-form button[type="submit"]')
        self.pagina.wait_for_selector('#bote-amigos-form .form-status:has-text("Agregaste a 2 amigos")')

        def yo_pague(monto, donde):
            self.pagina.click('#pestana-gastos')
            self.pagina.fill('#bote-form [name="monto"]', monto)
            self.pagina.fill('#bote-donde', donde)
            self.pagina.click(f'#bote-donde-resultados button[aria-label^="Elegir {donde}"]')
            self.pagina.wait_for_selector(f'#bote-donde-elegido:has-text("{donde}")')
            self.pagina.click('#bote-form button[type="submit"]')
            self.pagina.wait_for_selector(f'.bote-gasto:has-text("{donde}")')

        # Cada quien anota lo que pagó en un establecimiento, dividido entre los tres.
        yo_pague('300', 'Fonda Doña Lupe')
        self.contexto, self.pagina = sesiones['leo']
        self.abrir(f'/mis-viajes/{viaje.pk}/bote/')
        self.pagina.wait_for_selector('#bote-contenido:not([hidden])')
        yo_pague('90', 'Gasolinera del Bosque')

        # 390 entre tres: Leo debe 40 y Eva 130, ambos a Ana. Cada quien marca "Ya pagué".
        for nombre, monto in (('leo', '40.00'), ('eva', '130.00')):
            self.contexto, self.pagina = sesiones[nombre]
            self.abrir(f'/mis-viajes/{viaje.pk}/bote/#cuentas')
            self.pagina.reload()  # Con la misma página abierta, cambiar solo el ancla no la recarga.
            self.pagina.wait_for_selector(f'#bote-transferencias:has-text("le paga ${monto} a Ana")')
            self.pagina.click('#bote-transferencias button:has-text("Ya pagué")')
            self.pagina.wait_for_selector('#bote-transferencias:has-text("Falta que Ana confirme")')

        # Ana confirma lo recibido y quedan a mano.
        self.contexto, self.pagina = sesiones['ana']
        self.abrir(f'/mis-viajes/{viaje.pk}/bote/#cuentas')
        self.pagina.reload()
        for _ in range(2):
            self.pagina.click('#bote-transferencias button:has-text("Confirmar recibido") >> nth=0')
            self.pagina.wait_for_load_state('networkidle')
        self.pagina.wait_for_selector('#bote-a-mano:not([hidden]):has-text("Quedaron a mano")')
        self.assertIn('No falta ningún pago', self.pagina.inner_text('#bote-transferencias'))
        self.assertEqual(self.pagina.locator('#bote-historial li:has-text("Confirmado")').count(), 2)

        # La pestaña se maneja con el teclado.
        self.pagina.focus('#pestana-cuentas')
        self.pagina.keyboard.press('ArrowLeft')
        self.assertEqual(self.pagina.evaluate('document.activeElement.id'), 'pestana-gastos')
        self.assertTrue(self.pagina.is_visible('#panel-gastos'))

        for nombre in ('leo', 'eva'):
            contexto, pagina = sesiones[nombre]
            pagina.wait_for_load_state('networkidle')
            contexto.close()

    def test_comprobar_una_visita_con_la_ubicacion(self):
        self.contexto.grant_permissions(['geolocation'])
        self.contexto.set_geolocation({'latitude': 19.901, 'longitude': -103.701})
        self.iniciar_sesion()
        self.abrir('/destinos/mirador/')
        self.pagina.click('#visit-check')
        self.pagina.wait_for_selector('#visit-check:has-text("Visita comprobada")')
        self.assertTrue(self.usuario.visitas_comprobadas.filter(destino=self.destino).exists())
        self.abrir('/destinos/mirador/')
        self.pagina.wait_for_selector('#visit-check:has-text("Visita comprobada")')

    def test_una_mision_abre_el_formulario_del_dato(self):
        self.abrir('/misiones/')
        self.pagina.click('a[href*="dato=acceso"]')
        self.pagina.wait_for_selector('#sugerir-dato[open]')
        self.assertEqual(self.pagina.input_value('#sugerir-dato [name="campo"]'), 'acceso')

    def test_ganar_un_sello_y_compartir_el_pasaporte(self):
        Destino.objects.filter(pk=self.destino.pk).update(slug='tapalpa')
        self.contexto.grant_permissions(['geolocation', 'clipboard-read', 'clipboard-write'], origin=self.live_server_url)
        self.contexto.set_geolocation({'latitude': 19.901, 'longitude': -103.701})
        self.iniciar_sesion()
        self.abrir('/destinos/tapalpa/')
        self.pagina.click('#visit-check')
        self.pagina.wait_for_selector('#visit-status:has-text("Ganaste un sello")')
        self.abrir('/pasaporte/')
        self.pagina.wait_for_selector('#pagina-tapalpa.pagina--sellada [data-sello]:not([hidden])')
        self.assertIn('1 de 12', self.pagina.inner_text('#pasaporte-progreso'))
        self.pagina.evaluate('delete Navigator.prototype.share')
        self.pagina.click('#pasaporte-enlace')
        self.pagina.wait_for_selector('#pasaporte-retirar:not([hidden])')
        self.abrir(f'/pasaporte/{self.usuario.pasaporte.enlace}/')
        self.pagina.wait_for_selector('#pagina-tapalpa.pagina--sellada [aria-label="Tapalpa, visitado"]')

    def test_un_negocio_deja_sus_datos_sin_cuenta(self):
        self.abrir('/negocios/')
        self.pagina.fill('[name="negocio"]', 'Hostal Sierra')
        self.pagina.fill('[name="contacto"]', 'Eva')
        self.pagina.fill('[name="correo"]', 'eva@example.com')
        self.pagina.fill('[name="municipio"]', 'Tapalpa')
        self.pagina.check('[name="acepto"]')
        self.pagina.click('#negocios-form button[type="submit"]')
        self.pagina.wait_for_selector('#negocios-form .form-status:has-text("Gracias")')
        self.assertEqual(InteresNegocio.objects.get().negocio, 'Hostal Sierra')

    def test_elegir_en_el_mapa_guardar_y_armar_un_recorrido(self):
        Destino.objects.create(nombre='Cascada', slug='cascada', municipio=self.destino.municipio, descripcion='Salto de agua',
                               latitud=19.95, longitud=-103.75)
        self.iniciar_sesion()
        self.abrir('/destinos/')
        self.pagina.wait_for_selector('.pin', state='attached')
        self.pagina.click('.trip-card[data-slug="mirador"]')
        self.pagina.wait_for_selector('#place-panel:not([hidden])')
        self.assertEqual(self.pagina.inner_text('#place-name'), 'Mirador')
        self.pagina.wait_for_selector('#place-description:has-text("Lugar de prueba")')
        self.assertIn('/destinos/mirador/', self.pagina.get_attribute('#place-detail', 'href'))
        self.pagina.click('#place-favorite')
        self.pagina.wait_for_selector('#place-status:has-text("Guardado")')
        self.assertTrue(self.usuario.favoritos.filter(destino=self.destino).exists())
        self.pagina.click('#place-route')
        self.pagina.click('.trip-card[data-slug="cascada"]')
        self.pagina.wait_for_selector('#place-name:has-text("Cascada")')
        self.pagina.click('#place-route')
        self.assertEqual(self.pagina.locator('#route-stops li').count(), 2)
        self.pagina.wait_for_selector('path.linea-recorrido', state='attached')
        ruta = self.pagina.get_attribute('#route-open', 'href')
        self.assertIn('google.com/maps/dir', ruta)
        self.assertIn('waypoints=19.9', ruta)
        # El recorrido sobrevive a recargar; solo está en este navegador.
        self.pagina.reload()
        self.pagina.wait_for_selector('#route-panel:not([hidden])')
        self.pagina.click('#route-clear')
        self.assertTrue(self.pagina.is_hidden('#route-panel'))

    def test_el_tema_se_cambia_y_se_recuerda(self):
        self.contexto.close()
        self.contexto = self.nuevo_contexto(color_scheme='light')
        self.pagina = self.contexto.new_page()
        self.abrir('/destinos/')
        self.assertEqual(self.pagina.evaluate('document.documentElement.dataset.theme'), 'light')
        fondo_claro = self.pagina.evaluate("getComputedStyle(document.querySelector('.explorer-side')).backgroundColor")
        self.pagina.click('#navbar [data-theme-toggle]')
        self.assertEqual(self.pagina.evaluate('document.documentElement.dataset.theme'), 'dark')
        self.assertNotEqual(self.pagina.evaluate("getComputedStyle(document.querySelector('.explorer-side')).backgroundColor"), fondo_claro)
        self.assertIn('invert', self.pagina.evaluate("getComputedStyle(document.querySelector('.leaflet-tile-pane')).filter"))
        self.abrir('/login/')
        self.assertEqual(self.pagina.evaluate('document.documentElement.dataset.theme'), 'dark')

    def test_en_movil_la_tarjeta_elegida_queda_a_la_vista(self):
        for numero in range(6):
            Destino.objects.create(nombre=f'Lugar {numero}', slug=f'lugar-{numero}', municipio=self.destino.municipio,
                                   descripcion='-', latitud=19.9, longitud=-103.7)
        self.pagina.set_viewport_size({'width': 375, 'height': 812})
        self.abrir('/')
        self.pagina.wait_for_selector('.discovery-card')
        for _ in range(4):
            self.pagina.click('#next-place')
        caja = self.pagina.locator('.discovery-card[aria-pressed="true"]').bounding_box()
        # Margen de un píxel: el navegador redondea la posición al desplazar.
        self.assertGreaterEqual(caja['x'], -1)
        self.assertLessEqual(caja['x'] + caja['width'], 376)

    def test_el_mapa_se_identifica_ante_openstreetmap(self):
        # Sin Referer, el servidor responde 403 y pinta "Access blocked" en cada cuadro del mapa.
        peticiones = []
        self.pagina.on('request', lambda p: peticiones.append(p) if 'tile.openstreetmap.org' in p.url else None)
        self.abrir('/destinos/')
        self.pagina.wait_for_selector('.leaflet-tile', state='attached')
        self.pagina.wait_for_load_state('networkidle')
        self.assertTrue(peticiones)
        for peticion in peticiones:
            self.assertEqual(peticion.all_headers().get('referer'), self.live_server_url + '/')

    def test_cerca_de_mi_y_lugares_por_zona(self):
        Lugar.objects.create(nombre='Fonda Doña Ana', tipo='comer', subtipo='restaurant', latitud=19.901, longitud=-103.701,
                             telefono='33 1234', osm_id='node/1')
        Lugar.objects.create(nombre='Hotel Sierra', tipo='dormir', subtipo='hotel', latitud=19.905, longitud=-103.705)
        self.contexto.grant_permissions(['geolocation'], origin=self.live_server_url)
        self.contexto.set_geolocation({'latitude': 19.9, 'longitude': -103.7})
        # El enlace de la portada abre directamente la búsqueda.
        self.abrir('/')
        self.pagina.click('.home-cerca a')
        self.pagina.wait_for_selector('#nearby-list .nearby-fila')
        filas = self.pagina.locator('#nearby-list .nearby-fila')
        self.assertEqual(filas.count(), 2)
        self.assertIn('Fonda Doña Ana', filas.first.inner_text())
        self.pagina.click('[data-lugar-tipo="dormir"]')
        self.pagina.wait_for_selector('#nearby-list .nearby-fila:has-text("Fonda")', state='detached')
        self.assertIn('Hotel Sierra', self.pagina.inner_text('#nearby-list'))
        self.pagina.click('#nearby-list .nearby-fila')
        self.pagina.wait_for_selector('.lugar-popup:has-text("Hotel Sierra")')
        # Al cerrar sigue el filtro, ahora por la zona visible del mapa.
        self.pagina.click('#nearby-close')
        self.pagina.click('[data-lugar-tipo="comer"]')
        self.pagina.wait_for_selector('.pin-lugar', state='attached')
        self.pagina.click('.pin-lugar')
        self.pagina.wait_for_selector('.lugar-popup:has-text("Fonda Doña Ana")')
        self.assertEqual(self.pagina.get_attribute('.lugar-popup a[href^="tel:"]', 'href'), 'tel:331234')

    def crear_destinos_para_cercania(self):
        municipio = Municipio.objects.create(nombre='Zapopan', slug='zapopan', region=self.destino.municipio.region)
        Destino.objects.create(nombre='Bosque cercano', slug='bosque-cercano', municipio=municipio, descripcion='-',
                               latitud=20.70, longitud=-103.40)
        Destino.objects.create(nombre='Lago lejano', slug='lago-lejano', municipio=municipio, descripcion='-',
                               latitud=21.50, longitud=-104.90)

    def test_explorar_sin_busqueda_muestra_primero_lo_cercano(self):
        self.crear_destinos_para_cercania()
        self.contexto.grant_permissions(['geolocation'], origin=self.live_server_url)
        self.contexto.set_geolocation({'latitude': 20.6597, 'longitude': -103.3496})
        peticiones = []
        self.pagina.on('request', lambda p: peticiones.append(p.url + (p.post_data or '')))
        self.abrir('/destinos/')
        # Con el permiso ya concedido se ordena sola, sin preguntar.
        self.pagina.wait_for_selector('#cerca-destinos-lista .trip-card')
        self.assertTrue(self.pagina.is_hidden('#cerca-destinos-pedir'))
        tarjetas = self.pagina.locator('#cerca-destinos-lista .trip-card')
        self.assertEqual(tarjetas.count(), 3)
        self.assertEqual(tarjetas.first.get_attribute('data-slug'), 'bosque-cercano')
        self.assertIn('Zapopan · 6.9 km', tarjetas.first.inner_text())
        self.assertIn('Tapalpa · 92 km', tarjetas.nth(1).inner_text())
        self.assertIn('3 destinos más cercanos', self.pagina.inner_text('#cerca-destinos-estado'))
        # La lista normal sigue debajo y el mapa se centra en la persona.
        self.assertEqual(self.pagina.locator('.trip-grid:not(#cerca-destinos-lista) .trip-card').count(), 3)
        self.pagina.wait_for_selector('path.mi-ubicacion', state='attached')
        self.assertGreater(self.pagina.evaluate('InfoTripExplorador.map.getCenter().lat'), 20.2)
        # Una tarjeta cercana abre el destino en el mapa, igual que las de la lista.
        tarjetas.first.click()
        self.pagina.wait_for_selector('#place-name:has-text("Bosque cercano")')
        # La ubicación no sale del navegador ni se guarda.
        self.pagina.wait_for_load_state('networkidle')
        self.assertFalse([url for url in peticiones if '20.659' in url or '103.349' in url])
        self.assertNotIn('20.659', self.pagina.url + self.pagina.evaluate('JSON.stringify(localStorage)'))
        # Si después busca o filtra, manda su búsqueda.
        self.pagina.fill('#id_q', 'Lago')
        self.pagina.press('#id_q', 'Enter')
        self.pagina.wait_for_url(lambda url: 'q=Lago' in url)
        self.assertEqual(self.pagina.locator('#cerca-destinos').count(), 0)
        self.assertEqual(self.pagina.locator('.trip-card').count(), 1)

    def test_sin_permiso_se_pide_con_un_toque_y_un_rechazo_deja_la_lista(self):
        self.crear_destinos_para_cercania()
        self.pagina.set_viewport_size({'width': 375, 'height': 812})
        self.abrir('/destinos/')
        # Sin permiso no se pide la ubicación al cargar: se ofrece una tarjeta grande.
        boton = self.pagina.get_by_role('button', name=re.compile('Ver qué hay cerca de ti'))
        boton.wait_for()
        self.assertGreaterEqual(boton.bounding_box()['height'], 44)
        self.assertEqual(self.pagina.evaluate('document.documentElement.scrollWidth'), 375)
        self.assertEqual(self.pagina.locator('#cerca-destinos-lista .trip-card').count(), 0)
        # Chromium sin permiso responde como un rechazo: mensaje amable y la lista de siempre.
        boton.focus()
        self.pagina.keyboard.press('Enter')
        self.pagina.wait_for_selector('#cerca-destinos-estado:has-text("No diste permiso")')
        self.assertEqual(self.pagina.evaluate('document.activeElement.id'), 'cerca-destinos-titulo')
        self.assertEqual(self.pagina.locator('.explorer-list .trip-card').count(), 3)
        # Con el permiso concedido, al volver ya no pregunta: se ordena sola.
        self.contexto.grant_permissions(['geolocation'], origin=self.live_server_url)
        self.contexto.set_geolocation({'latitude': 21.49, 'longitude': -104.89})
        self.abrir('/destinos/')
        self.pagina.wait_for_selector('#cerca-destinos-lista .trip-card')
        self.assertEqual(self.pagina.locator('#cerca-destinos-lista .trip-card').first.get_attribute('data-slug'),
                         'lago-lejano')
        self.assertEqual(self.pagina.evaluate('document.documentElement.scrollWidth'), 375)

    def test_mover_el_mapa_no_cierra_el_lugar_abierto(self):
        Lugar.objects.create(nombre='Fonda Doña Ana', tipo='comer', subtipo='restaurant', latitud=19.9, longitud=-103.7)
        self.abrir('/destinos/')
        self.pagina.wait_for_selector('.pin', state='attached')
        self.pagina.evaluate('InfoTripExplorador.map.setView([19.9, -103.7], 15, {animate: false})')
        self.pagina.click('[data-lugar-tipo="comer"]')
        self.pagina.wait_for_selector('.pin-lugar', state='attached')
        self.pagina.click('.pin-lugar')
        self.pagina.wait_for_selector('.lugar-popup:has-text("Fonda Doña Ana")')
        # Abrir un recuadro cerca del borde mueve el mapa, y moverlo recarga los lugares de la zona.
        self.pagina.evaluate('InfoTripExplorador.map.panBy([20, 20], {animate: false})')
        self.pagina.wait_for_load_state('networkidle')
        self.pagina.wait_for_timeout(600)
        self.assertTrue(self.pagina.is_visible('.lugar-popup:has-text("Fonda Doña Ana")'))

    def test_resenar_un_lugar_y_responder_si_sigue_abierto(self):
        sitio = Lugar.objects.create(nombre='Fonda Doña Ana', tipo='comer', subtipo='restaurant', latitud=19.901, longitud=-103.701,
                                     osm_id='node/1')
        self.contexto.grant_permissions(['geolocation'], origin=self.live_server_url)
        self.contexto.set_geolocation({'latitude': 19.9011, 'longitude': -103.7011})
        self.iniciar_sesion()
        self.abrir(f'/lugares/{sitio.pk}/')
        self.pagina.wait_for_selector('#ficha-mapa .pin-lugar', state='attached')
        self.pagina.click('.estado-lugar[data-abierto="true"]')
        self.pagina.wait_for_selector('#estado-resumen:has-text("1 dice que sí")')
        self.pagina.click('#escribir-resena summary')
        self.pagina.fill('#resena-form [name="texto"]', 'Muy rico')
        self.pagina.fill('#resena-form [name="fecha_visita"]', '2026-01-15')
        self.pagina.fill('#resena-form [name="monto"]', '180')
        salida = BytesIO()
        Image.new('RGB', (40, 30), 'teal').save(salida, format='PNG')
        self.pagina.set_input_files('#resena-form [name="imagen"]', {'name': 'foto.png', 'mimeType': 'image/png', 'buffer': salida.getvalue()})
        self.pagina.check('#resena-form [name="comprobar"]')
        self.pagina.click('#resena-form button[type="submit"]')
        self.pagina.wait_for_selector('#resena-form .form-status:has-text("pendiente de revisión")')
        resena = sitio.resenas.get()
        self.assertTrue(resena.ubicacion_comprobada)
        self.assertEqual(resena.monto, 180)
        self.addCleanup(resena.miniatura.delete, False)
        self.addCleanup(resena.imagen.delete, False)
        moderar(resena, Usuario.objects.create_superuser('m@example.com', 'Mod', 'P', CLAVE), 'publicado', 'Revisada')
        # Al volver, la página recuerda lo que respondió y muestra la reseña publicada.
        self.abrir(f'/lugares/{sitio.pk}/')
        self.pagina.wait_for_selector('.visit-badge')
        self.pagina.wait_for_selector('.contribution-list img.community-photo')
        self.pagina.wait_for_selector('#resena-titulo:has-text("Editar mi reseña")')
        self.pagina.wait_for_selector('.estado-lugar[data-abierto="true"][aria-pressed="true"]')
        self.assertIn('Muy rico', self.pagina.inner_text('.contribution-list'))

    def test_proponer_un_lugar_y_aprobarlo(self):
        Lugar.objects.create(nombre='Fonda Doña Ana', tipo='comer', subtipo='restaurant', latitud=19.9, longitud=-103.7)
        self.contexto.grant_permissions(['geolocation'], origin=self.live_server_url)
        self.contexto.set_geolocation({'latitude': 19.9, 'longitude': -103.7})
        self.iniciar_sesion()
        self.abrir('/lugares/proponer/')
        self.pagina.fill('#propuesta-form [name="nombre"]', 'Fonda Dona Ana')
        self.pagina.select_option('#propuesta-form [name="subtipo"]', 'restaurant')
        # Sin punto no se envía nada.
        self.pagina.click('#propuesta-form button[type="submit"]')
        self.pagina.wait_for_selector('#propuesta-form .form-status:has-text("marcar dónde")')
        self.pagina.click('#propuesta-ubicacion')
        self.pagina.wait_for_selector('#propuesta-punto:has-text("Arrastra")')
        # Ya existe algo parecido: pregunta antes de guardar.
        self.pagina.click('#propuesta-form button[type="submit"]')
        self.pagina.wait_for_selector('#propuesta-parecidos:not([hidden])')
        self.assertIn('Fonda Doña Ana', self.pagina.inner_text('#propuesta-parecidos-lista'))
        self.assertFalse(PropuestaLugar.objects.exists())
        self.pagina.click('#propuesta-distinto')
        self.pagina.wait_for_selector('#propuesta-form .form-status:has-text("Recibimos")')
        propuesta = PropuestaLugar.objects.get()
        moderar(propuesta, Usuario.objects.create_superuser('m@example.com', 'Mod', 'P', CLAVE), 'publicado', 'Revisada')
        self.abrir(f'/lugares/{propuesta.lugar_id}/')
        self.pagina.wait_for_selector('text=Agregado por la comunidad')

    def preparar_direcciones(self, sugerir, inversa):
        """Intercepta nuestra API de direcciones; el navegador nunca debe llamar a OpenStreetMap directamente."""
        self.pagina.route('**/api/v1/direcciones/sugerir/**', sugerir)
        self.pagina.route('**/api/v1/direcciones/buscar/**', sugerir)
        self.pagina.route('**/api/v1/direcciones/inversa/**', inversa)

        def prohibida(ruta):
            self.problemas.append(f'Llamada directa a OpenStreetMap: {ruta.request.url}')
            ruta.abort()
        self.pagina.route(re.compile(r'https://(nominatim\.openstreetmap\.org|photon\.komoot\.io)/'), prohibida)

    def test_proponer_un_lugar_por_direccion(self):
        juarez = {'etiqueta': 'Avenida Juárez 976, Centro, Guadalajara, Jalisco', 'calle': 'Avenida Juárez 976',
                  'colonia': 'Centro', 'municipio': 'Guadalajara', 'estado': 'Jalisco', 'lat': 20.67412, 'lon': -103.34877}
        moreno = {**juarez, 'etiqueta': 'Pedro Moreno 1200, Americana, Guadalajara, Jalisco', 'calle': 'Pedro Moreno 1200'}
        consultas = []

        def sugerir(ruta):
            consultas.append(ruta.request.url)
            ruta.fulfill(json=[juarez])
        self.preparar_direcciones(sugerir, lambda ruta: ruta.fulfill(json=[moreno]))
        self.iniciar_sesion()
        self.abrir('/lugares/proponer/')
        self.pagina.fill('#propuesta-form [name="nombre"]', 'Tortas Ahogadas El Güero')
        self.pagina.select_option('#propuesta-form [name="subtipo"]', 'restaurant')
        # Escribir la dirección: sugerencias con espera y elegir con el teclado.
        campo = self.pagina.locator('#propuesta-direccion')
        campo.press_sequentially('juarez 976')
        self.pagina.get_by_role('option', name=re.compile('Avenida Juárez 976')).wait_for()
        self.assertLessEqual(len(consultas), 3)  # con la espera, no una petición por tecla
        self.assertNotIn('q=ju&', ' '.join(consultas) + '&')
        campo.press('ArrowDown')
        campo.press('Enter')
        # El punto cae en el mapa en la dirección elegida.
        self.pagina.wait_for_selector('#propuesta-punto:has-text("20.6741° N, 103.3488° O")')
        self.assertEqual(campo.input_value(), juarez['etiqueta'])
        self.assertEqual(campo.get_attribute('aria-expanded'), 'false')
        # Moverlo: busca la dirección del nuevo punto y, como la anterior la pusimos nosotros, la reemplaza.
        marcador = self.pagina.locator('.leaflet-marker-icon').first.bounding_box()
        x, y = marcador['x'] + marcador['width'] / 2, marcador['y'] + marcador['height'] / 2
        self.pagina.mouse.move(x, y)
        self.pagina.mouse.down()
        self.pagina.mouse.move(x + 40, y + 30, steps=8)
        self.pagina.mouse.up()
        self.pagina.wait_for_selector('#propuesta-direccion-estado:has-text("Dirección completada: Pedro Moreno")')
        self.assertEqual(campo.input_value(), moreno['etiqueta'])
        self.assertNotIn('20.6741° N, 103.3488° O', self.pagina.inner_text('#propuesta-punto'))
        # Lo que escribe la persona no se sobrescribe sin preguntar.
        campo.fill('Pedro Moreno 1200, local 3')
        mapa = self.pagina.locator('#propuesta-mapa').bounding_box()
        self.pagina.mouse.click(mapa['x'] + mapa['width'] / 2 - 60, mapa['y'] + mapa['height'] / 2 - 50)
        self.pagina.wait_for_selector('#propuesta-direccion-sugerida:not([hidden])')
        self.assertEqual(campo.input_value(), 'Pedro Moreno 1200, local 3')
        self.pagina.click('#propuesta-direccion-mantener')
        self.assertEqual(campo.input_value(), 'Pedro Moreno 1200, local 3')
        punto = self.pagina.inner_text('#propuesta-punto')
        self.pagina.click('#propuesta-form button[type="submit"]')
        self.pagina.wait_for_selector('#propuesta-form .form-status:has-text("Recibimos")')
        propuesta = PropuestaLugar.objects.get()
        self.assertEqual(propuesta.direccion, 'Pedro Moreno 1200, local 3')
        self.assertIn(f'{abs(float(propuesta.longitud)):.4f}° O', punto)
        self.assertNotAlmostEqual(float(propuesta.latitud), juarez['lat'], places=4)
        self.assertAlmostEqual(float(propuesta.latitud), juarez['lat'], places=1)

    def test_sin_servicio_de_direcciones_el_mapa_sigue_funcionando(self):
        caido = {'detail': 'El buscador de direcciones no responde ahora. Puedes marcar el punto directamente en el mapa.'}
        self.preparar_direcciones(lambda ruta: ruta.fulfill(status=503, json=caido),
                                  lambda ruta: ruta.fulfill(status=503, json=caido))
        self.abrir('/lugares/proponer/')
        campo = self.pagina.locator('#propuesta-direccion')
        campo.press_sequentially('juarez 976')
        self.pagina.wait_for_selector('#propuesta-direccion-estado:has-text("no responde ahora")')
        campo.press('Enter')  # Intro busca la dirección completa y no envía el formulario
        self.pagina.wait_for_selector('#propuesta-direccion-estado:has-text("no responde ahora")')
        self.pagina.locator('#propuesta-mapa').click()
        self.pagina.wait_for_selector('#propuesta-punto:has-text("Arrastra")')
        self.pagina.wait_for_selector('#propuesta-direccion-estado:has-text("puedes escribirla")')
        self.assertEqual(campo.input_value(), 'juarez 976')
        self.pagina.wait_for_load_state('networkidle')
        # Los 503 simulados son parte de la prueba.
        self.problemas = [p for p in self.problemas if '/api/v1/direcciones/' not in p]

    def test_enviar_un_comentario_desde_cualquier_pagina(self):
        self.abrir('/destinos/mirador/')
        self.pagina.click('footer a:has-text("Enviar comentarios")')
        self.pagina.wait_for_selector('#comentario-form')
        self.pagina.fill('#comentario-form [name="texto"]', 'El mapa tardó en cargar')
        self.pagina.click('#comentario-form button[type="submit"]')
        self.pagina.wait_for_selector('#comentario-form .form-status:has-text("Gracias")')
        comentario = Comentario.objects.get()
        self.assertEqual((comentario.pagina, comentario.tipo), ('/destinos/mirador/', 'problema'))

    def test_armar_una_ruta_y_guardarla_en_mis_viajes(self):
        self.destino.categorias.add(Categoria.objects.create(nombre='Miradores', slug='miradores'))
        Lugar.objects.create(nombre='Cabañas del Bosque', tipo='dormir', subtipo='hotel', latitud=19.901,
                             longitud=-103.701)
        self.iniciar_sesion()
        self.abrir('/planeador/')
        self.pagina.check('#ruta-form input[value="miradores"]')
        self.pagina.check('#ruta-form [name="dias"][value="2"]')
        self.pagina.click('#ruta-form .planeador-mas summary')
        self.pagina.uncheck('#ruta-form [name="regresar"]')
        self.pagina.click('#ruta-form button[type="submit"]')
        self.pagina.wait_for_selector('#ruta-detalle .parada')
        self.assertIn('Mirador', self.pagina.inner_text('#ruta-detalle'))
        self.assertIn('Cabañas del Bosque', self.pagina.inner_text('#ruta-detalle'))
        # Un marcador numerado por parada, más el de salida.
        self.assertEqual(self.pagina.locator('#ruta-mapa .pin-ruta').count(), 1)
        self.pagina.click('#ruta-guardar')
        # Se guarda como escapada y se abre en su editor.
        self.pagina.wait_for_selector('#trip-status:has-text("quedó guardada como escapada")')
        viaje = Viaje.objects.get(autor=self.usuario)
        self.assertEqual(list(viaje.lugares.all()), [self.destino])
        self.assertEqual(viaje.actividades[0]['titulo'], 'Mirador')
        self.assertIn('Dormir: Cabañas del Bosque', [a['titulo'] for a in viaje.actividades])
        self.assertEqual(self.pagina.input_value('#trip-form [name="nombre"]'), viaje.nombre)

    def test_guadalajara_a_tapalpa_cambiar_descansar_y_guardar_como_escapada(self):
        naturaleza = Categoria.objects.create(nombre='Naturaleza', slug='naturaleza')
        tapalpa = self.destino.municipio
        gdl = Municipio.objects.create(nombre='Guadalajara', slug='guadalajara', region=tapalpa.region)
        Destino.objects.create(nombre='Bosque Colomos', slug='bosque-colomos', municipio=gdl, descripcion='-',
                               latitud=20.705, longitud=-103.393).categorias.add(naturaleza)
        for i, (nombre, lat, lng) in enumerate([('Las Piedrotas', 19.965, -103.745),
                                                ('Presa del Nogal', 19.950, -103.770),
                                                ('Salto del Nogal', 19.920, -103.780),
                                                ('Bosque de Tapalpa', 19.940, -103.730),
                                                ('Valle de los Enigmas', 19.975, -103.760)]):
            Destino.objects.create(nombre=nombre, slug=f'sitio-{i}', municipio=tapalpa, descripcion='-',
                                   latitud=lat, longitud=lng).categorias.add(naturaleza)
        self.iniciar_sesion()
        self.abrir('/planeador/')
        self.pagina.select_option('#ruta-municipio', 'guadalajara')
        self.pagina.check('#ruta-form input[value="naturaleza"]')
        self.pagina.check('#ruta-form [name="dias"][value="1"]')
        self.pagina.fill('#ruta-destino', 'Tapalpa')
        self.pagina.locator('.buscador-opciones [role="option"]').filter(
            has=self.pagina.locator('.buscador-nombre', has_text=re.compile('^Tapalpa$'))).click()
        self.assertTrue(self.pagina.is_checked('#ruta-form [name="modo"][value="ida_vuelta"]'))
        self.pagina.click('#ruta-form .planeador-mas summary')
        self.pagina.fill('#ruta-form [name="hora_inicio"]', '08:00')
        self.pagina.fill('#ruta-form [name="hora_fin"]', '18:00')
        self.pagina.click('#ruta-form button[type="submit"]')
        self.pagina.wait_for_selector('#ruta-detalle .parada')
        # Al terminar, el foco va al resumen, que lo anuncia.
        self.assertEqual(self.pagina.evaluate('document.activeElement.id'), 'ruta-resumen')
        antes = self.pagina.locator('#ruta-detalle .parada h4').all_inner_texts()
        self.assertTrue(antes)

        # Cambiar la última parada del día (la que tiene más hueco) por otra que quepa.
        self.pagina.locator('#ruta-detalle .parada').last.locator('button:has-text("Cambiar por otro")').click()
        self.pagina.wait_for_selector('#ruta-detalle .parada-alternativa')
        opcion = self.pagina.locator('#ruta-detalle .parada-alternativa').first
        nueva = opcion.locator('a').inner_text()
        self.assertNotIn(nueva, antes)
        opcion.locator('button:has-text("Elegir")').click()
        self.pagina.wait_for_selector('#ruta-edicion-estado:has-text("Cambiamos")')
        despues = self.pagina.locator('#ruta-detalle .parada h4').all_inner_texts()
        self.assertIn(nueva, despues)
        self.assertNotIn(antes[-1], despues)
        self.assertEqual(self.pagina.evaluate('document.activeElement.id'), 'ruta-resumen')

        # Quitar otra parada y dejar ese rato libre.
        quitada = [nombre for nombre in despues if nombre != nueva][0]
        self.pagina.locator('#ruta-detalle .parada', has_text=quitada).locator(
            'button:has-text("Quitar y descansar")').click()
        self.pagina.wait_for_selector('#ruta-detalle .planeador-descanso:has-text("Tiempo libre")')
        self.assertNotIn(quitada, self.pagina.locator('#ruta-detalle .parada h4').all_inner_texts())
        self.assertIn(nueva, self.pagina.locator('#ruta-detalle .parada h4').all_inner_texts())

        # Guardar como escapada: se abre el editor con la agenda.
        self.pagina.click('#ruta-guardar')
        self.pagina.wait_for_selector('#trip-status:has-text("quedó guardada como escapada")')
        viaje = Viaje.objects.get(autor=self.usuario)
        self.assertEqual(viaje.nombre, 'Escapada a Tapalpa')
        nombres = set(viaje.lugares.values_list('nombre', flat=True))
        self.assertIn(nueva, nombres)
        self.assertNotIn(quitada, nombres)
        self.assertIn('Tiempo libre', [a['titulo'] for a in viaje.actividades])
        self.assertTrue(self.pagina.evaluate(
            "[...document.querySelectorAll('#trip-activities input')].some(e => e.value === 'Tiempo libre')"))
        # Desde ahí se puede invitar a amigos (el bote del grupo del módulo de amigos).
        self.pagina.click('#trip-status button:has-text("Invitar amigos")')
        self.pagina.wait_for_url(re.compile(rf'/mis-viajes/{viaje.pk}/bote/#bote-amigos$'))

    def test_compartir_una_ruta_por_enlace(self):
        self.armar_ruta_de_dos_dias()
        self.assertIn('google.com/maps/dir/', self.pagina.get_attribute('#ruta-detalle .planeador-dia-mapa a', 'href'))
        self.pagina.click('#ruta-compartir')
        self.pagina.wait_for_selector('#ruta-compartir-panel:not([hidden])')
        ruta = RutaCompartida.objects.get()
        enlace = self.pagina.input_value('#ruta-enlace')
        self.assertEqual(enlace, f'{self.live_server_url}/planeador/r/{ruta.enlace}/')
        # El foco queda en el enlace, listo para copiarlo; WhatsApp lleva el texto y el enlace, nada más.
        self.assertEqual(self.pagina.evaluate('document.activeElement.id'), 'ruta-enlace')
        whatsapp = self.pagina.get_attribute('#ruta-compartir-panel [data-whatsapp]', 'href')
        self.assertTrue(whatsapp.startswith('https://wa.me/?text='))
        self.assertIn(quote(enlace, safe=''), whatsapp)
        self.assertIn('hasta el', self.pagina.inner_text('#ruta-compartir-panel'))

        with self.pagina.expect_download() as descarga:
            self.pagina.click('#ruta-ics')
        self.assertIn('BEGIN:VEVENT', open(descarga.value.path(), encoding='utf-8').read())

        # Quien recibe el enlace ve la ruta sin cuenta, con su mapa, y puede armar la suya.
        self.abrir(f'/planeador/r/{ruta.enlace}/')
        self.assertIn('Ruta de 2 días desde Tapalpa', self.pagina.inner_text('h1'))
        self.assertIn('Mirador', self.pagina.inner_text('main'))
        self.pagina.wait_for_selector('#ruta-mapa .pin-ruta')
        self.assertEqual(self.pagina.get_attribute('meta[name="robots"]', 'content'), 'noindex')
        self.pagina.focus('.planeador-compartir [data-copiar]')
        self.pagina.keyboard.press('Enter')
        self.pagina.wait_for_selector('.planeador-compartir [data-compartir-estado]:not(:empty)')
        self.pagina.click('text=Armar mi propia ruta')
        self.pagina.wait_for_url('**/planeador/')

    def test_ruta_compartida_con_cuenta_se_borra_desde_el_perfil(self):
        self.iniciar_sesion()
        self.armar_ruta_de_dos_dias()
        self.pagina.click('#ruta-compartir')
        self.pagina.wait_for_selector('#ruta-compartir-panel:not([hidden])')
        self.assertIn('Queda en tu perfil', self.pagina.inner_text('#ruta-compartir-panel'))
        self.abrir('/perfil/')
        self.pagina.wait_for_selector('#my-shared-routes h3 a')
        self.pagina.on('dialog', lambda dialogo: dialogo.accept())
        self.pagina.click('#my-shared-routes button:has-text("Borrar")')
        self.pagina.wait_for_selector('#shared-routes-status:has-text("Ruta borrada")')
        self.assertFalse(RutaCompartida.objects.exists())

    def test_con_la_ruta_armada_el_formulario_se_pliega_y_se_puede_reabrir(self):
        self.armar_ruta_de_dos_dias()
        # El formulario deja su lugar a una fila con lo elegido y el resultado usa todo el ancho.
        self.assertTrue(self.pagina.locator('#ruta-form').is_hidden())
        resumen = self.pagina.inner_text('#ruta-plegado-texto')
        self.assertIn('2 días', resumen)
        self.assertIn('Miradores', resumen)
        self.assertEqual(self.pagina.get_attribute('#ruta-cambiar', 'aria-expanded'), 'false')
        ancho = self.pagina.evaluate("document.getElementById('ruta-resultado').offsetWidth / document.querySelector('.planeador-layout').offsetWidth")
        self.assertGreater(ancho, .95)
        self.assertGreaterEqual(self.pagina.locator('#ruta-cambiar').bounding_box()['height'], 44)
        # «Cambiar» lo vuelve a mostrar tal como estaba y lleva el foco al primer campo.
        self.pagina.click('#ruta-cambiar')
        self.assertTrue(self.pagina.locator('#ruta-form').is_visible())
        self.assertEqual(self.pagina.get_attribute('#ruta-cambiar', 'aria-expanded'), 'true')
        self.assertEqual(self.pagina.evaluate('document.activeElement.id'), 'ruta-municipio')
        self.assertTrue(self.pagina.is_checked('#ruta-form input[value="miradores"]'))
        self.assertTrue(self.pagina.locator('#ruta-aviso-edicion').is_hidden())
        self.pagina.click('#ruta-cambiar')
        self.assertTrue(self.pagina.locator('#ruta-form').is_hidden())
        # Un error al volver a armar deja el formulario abierto, con el error a la vista.
        self.pagina.click('#ruta-cambiar')
        self.pagina.fill('#ruta-form [name="hora_fin"]', '08:00')
        self.pagina.click('#ruta-form button[type="submit"]')
        self.pagina.wait_for_selector('#ruta-error-cuando:not([hidden])')
        self.assertTrue(self.pagina.locator('#ruta-form').is_visible())

    def armar_ruta_de_dos_dias(self):
        self.destino.categorias.add(Categoria.objects.create(nombre='Miradores', slug='miradores'))
        self.abrir('/planeador/')
        self.pagina.check('#ruta-form input[value="miradores"]')
        self.pagina.check('#ruta-form [name="dias"][value="2"]')
        self.pagina.click('#ruta-form button[type="submit"]')
        self.pagina.wait_for_selector('#ruta-detalle .parada-extra .parada-bloque')

    def test_dias_seleccionables_y_detalle_de_cada_parada(self):
        Colaboracion.objects.create(destino=self.destino, autor=self.usuario, tipo='correccion', campo='horarios',
                                    texto='Todos los días de 8 a 18 h', fuente='Ayuntamiento: https://tapalpa.gob.mx/',
                                    estado='publicado', fecha_dato=date.today())
        Aporte.objects.create(destino=self.destino, autor=self.usuario, tipo='resena', texto='Vista increíble al valle',
                              calificacion=5, fecha_visita=date.today(), estado='publicado')
        otra = Usuario.objects.create_user('beto@example.com', 'Beto', 'Prueba', CLAVE, es_verificado=True)
        Aporte.objects.create(destino=self.destino, autor=otra, tipo='resena', texto='Sin moderar todavía',
                              calificacion=1, fecha_visita=date.today(), estado='pendiente')
        self.armar_ruta_de_dos_dias()
        tarjetas = self.pagina.locator('#ruta-dias .planeador-dia-tarjeta')
        self.assertEqual(tarjetas.count(), 2)
        self.assertEqual(tarjetas.nth(0).get_attribute('aria-pressed'), 'true')
        self.assertIn('1 parada', tarjetas.nth(0).inner_text())
        self.assertIn('Sin paradas', tarjetas.nth(1).inner_text())
        # Las reseñas van plegadas dentro de la tarjeta de la parada.
        self.pagina.click('#ruta-detalle .parada-plegable summary')
        detalle = self.pagina.inner_text('#ruta-detalle')
        for texto in ['Lugar de prueba', 'Todos los días de 8 a 18 h', 'Ayuntamiento', 'Llegas', 'Sales',
                      'Vista increíble al valle', '5 de 5 estrellas']:
            self.assertIn(texto, detalle)
        self.assertNotIn('Sin moderar todavía', detalle)
        self.assertEqual(self.pagina.get_attribute('#ruta-detalle .parada-fuente a', 'href'), 'https://tapalpa.gob.mx/')
        self.assertEqual(self.pagina.get_attribute('#ruta-detalle .parada-acciones a.principal', 'href'),
                         '/destinos/mirador/')
        self.assertIn('google.com/maps/dir/',
                      self.pagina.get_attribute('#ruta-detalle .parada-acciones a[target="_blank"]', 'href'))
        # Con el teclado: Tab lleva a la tarjeta del día 2, que muestra su foco y se elige con Enter.
        tarjetas.nth(0).focus()
        self.pagina.keyboard.press('Tab')
        self.assertEqual(self.pagina.evaluate('document.activeElement.dataset.dia'), '1')
        self.assertEqual(self.pagina.evaluate('getComputedStyle(document.activeElement).outlineStyle'), 'solid')
        self.pagina.keyboard.press('Enter')
        self.assertEqual(tarjetas.nth(1).get_attribute('aria-pressed'), 'true')
        self.assertEqual(tarjetas.nth(0).get_attribute('aria-pressed'), 'false')
        self.assertIn('Día 2', self.pagina.inner_text('#ruta-detalle h3'))
        self.assertIn('no cabe ninguna visita', self.pagina.inner_text('#ruta-detalle'))

    def test_errores_comprensibles_y_lugar_sin_resenas(self):
        self.destino.categorias.add(Categoria.objects.create(nombre='Miradores', slug='miradores'))
        self.abrir('/planeador/')
        self.pagina.fill('#ruta-form [name="hora_fin"]', '08:00')
        self.pagina.click('#ruta-form button[type="submit"]')
        self.assertIn('al menos una cosa que te guste', self.pagina.inner_text('#ruta-error-intereses'))
        self.assertIn('después de la de empezar', self.pagina.inner_text('#ruta-error-cuando'))
        self.assertEqual(self.pagina.get_attribute('#ruta-paso-intereses', 'aria-invalid'), 'true')
        self.assertTrue(self.pagina.locator('#ruta-resultado').is_hidden())
        self.pagina.click('#ruta-form [data-inicio="09:00"]')
        self.pagina.check('#ruta-form input[value="miradores"]')
        self.assertTrue(self.pagina.locator('#ruta-error-intereses').is_hidden())
        self.pagina.click('#ruta-form button[type="submit"]')
        self.pagina.wait_for_selector('#ruta-detalle .parada-sin-resenas')
        self.assertIn('Aún no hay reseñas', self.pagina.inner_text('#ruta-detalle .parada-sin-resenas'))
        self.assertEqual(self.pagina.get_attribute('#ruta-detalle .parada-sin-resenas a', 'href'),
                         '/destinos/mirador/#reportar-gasto')

    def test_planeador_en_movil_legible_y_facil_de_tocar(self):
        self.pagina.set_viewport_size({'width': 375, 'height': 812})
        self.armar_ruta_de_dos_dias()
        self.assertEqual(self.pagina.evaluate('document.documentElement.scrollWidth'), 375)
        pequenos = self.pagina.evaluate('''[...document.querySelectorAll(
            '.planeador button, .planeador input:not([type="checkbox"]), .planeador select, .planeador summary,'
            + ' .planeador .parada-acciones a, .planeador label.planeador-chip, .planeador .planeador-check')]
            .filter(e => !e.closest('.leaflet-container'))
            .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.height < 44; })
            .map(e => e.outerHTML.slice(0, 80))''')
        self.assertEqual(pequenos, [])
        chicos = self.pagina.evaluate('''[...document.querySelectorAll('.planeador-layout *')]
            .filter(e => !e.closest('.leaflet-container') && !e.closest('.sr-only'))
            .filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
            .filter(e => parseFloat(getComputedStyle(e).fontSize) < 16)
            .map(e => e.tagName + '.' + e.className)''')
        self.assertEqual(chicos, [])

    def test_guardar_favorito_y_cerrar_sesion(self):
        self.iniciar_sesion()
        self.abrir('/destinos/mirador/')
        self.pagina.wait_for_selector('#favorite-toggle:not([disabled])')
        self.pagina.click('#favorite-toggle')
        self.pagina.wait_for_selector('#favorite-status:has-text("Guardado")')
        self.abrir('/favoritos/')
        self.pagina.wait_for_selector('#favorites-list h2')
        self.pagina.click('#account-toggle')
        self.pagina.click('#logoutBtn')
        self.pagina.wait_for_url(self.live_server_url + '/')
        self.abrir('/perfil/')
        self.pagina.wait_for_selector('#profile-login:not([hidden])')

    def test_los_avisos_sin_leer_se_ven_en_la_barra_y_el_menu_dice_mis_viajes(self):
        from apps.comunidad.models import Notificacion
        Notificacion.objects.create(usuario=self.usuario, texto='Publicamos tu reseña sobre Mirador.')
        Notificacion.objects.create(usuario=self.usuario, texto='Publicamos tu fotografía sobre Mirador.')
        # Sin sesión no hay enlace de avisos y el menú ya dice «Mis viajes» (un solo nombre, con o sin sesión).
        self.abrir('/planeador/')
        self.assertEqual(self.pagina.locator('.nav-links a[href="/mis-viajes/"]').inner_text(), 'Mis viajes')
        self.assertTrue(self.pagina.locator('#account-menu [data-avisos]').is_hidden())
        self.iniciar_sesion()
        # /planeador/ no carga cuenta-api.js: el número llega con el token que pide avisos-nav.js.
        self.abrir('/planeador/')
        self.pagina.wait_for_selector('#account-toggle.con-avisos')
        self.pagina.click('#account-toggle')
        numero = self.pagina.locator('#account-menu .nav-avisos')
        self.assertEqual(numero.inner_text(), '2')
        self.assertEqual(numero.get_attribute('aria-label'), '2 avisos sin leer')
        self.pagina.click('#account-menu [data-avisos]')
        # Mi perfil los muestra y los marca como leídos: el número desaparece ahí y en la siguiente página.
        self.pagina.wait_for_selector('#my-notices :text("Publicamos tu reseña")')
        self.assertFalse(self.pagina.locator('#account-toggle.con-avisos').count())
        self.pagina.wait_for_function('!document.querySelector("#profile-content").hidden')
        self.abrir('/destinos/mirador/')
        self.pagina.wait_for_selector('#account-menu [data-avisos]', state='attached')
        self.assertFalse(self.pagina.locator('#account-toggle.con-avisos').count())
        self.assertFalse(Notificacion.objects.filter(leida=False).exists())

    PAGINAS_LEGIBLES = ['/', '/destinos/', '/destinos/mirador/', '/destinos/mirador/costos/', '/costos/', '/misiones/',
                        '/mis-viajes/', '/login/', '/registro/', '/recuperar/', '/lugares/proponer/', '/negocios/',
                        '/comentarios/', '/privacidad/', '/creditos/']

    def test_en_movil_el_texto_mide_16_px_y_los_controles_44(self):
        self.pagina.set_viewport_size({'width': 375, 'height': 812})
        for ruta in self.PAGINAS_LEGIBLES:
            with self.subTest(ruta=ruta):
                self.abrir(ruta)
                self.pagina.wait_for_load_state('networkidle')
                # Los desplegables se abren para medir también lo que esconden.
                self.pagina.evaluate("document.querySelectorAll('main details').forEach(d => { d.open = true; })")
                chicos = self.pagina.evaluate('''[...document.querySelectorAll('body *')]
                    .filter(e => !e.closest('.leaflet-container, .sr-only, .skip-link, script, style, noscript'))
                    .filter(e => e.getClientRects().length)
                    .filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
                    .filter(e => parseFloat(getComputedStyle(e).fontSize) < 16)
                    .map(e => `${e.tagName}.${e.className} «${e.textContent.trim().slice(0, 30)}»`)''')
                self.assertEqual(sorted(set(chicos)), [])
                # Enlaces dentro de un párrafo quedan fuera (WCAG 2.5.8 los exceptúa); botones y campos, no.
                pequenos = self.pagina.evaluate('''[...document.querySelectorAll(
                    'button, select, summary, textarea, input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]):not([type="file"]), a')]
                    .filter(e => !e.closest('.sr-only, .skip-link'))
                    .filter(e => e.tagName !== 'A' || getComputedStyle(e).display !== 'inline')
                    .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.width > 0 && r.height < 44; })
                    .map(e => `${e.tagName}.${e.className} «${(e.textContent.trim() || e.getAttribute('aria-label') || e.name || '').slice(0, 30)}» ${Math.round(e.getBoundingClientRect().height)}`)''')
                self.assertEqual(sorted(set(pequenos)), [])
                self.assertLessEqual(self.pagina.evaluate('document.documentElement.scrollWidth'), 375)

    def test_el_indice_de_la_ficha_salta_a_cada_seccion_sin_taparla(self):
        self.pagina.set_viewport_size({'width': 375, 'height': 812})
        self.abrir('/destinos/mirador/')
        self.pagina.click('.indice-pagina a[href="#community-title"]')
        self.pagina.wait_for_function('scrollY > 200')
        self.pagina.wait_for_timeout(400)
        indice = self.pagina.locator('.indice-pagina').bounding_box()
        titulo = self.pagina.locator('#community-title').bounding_box()
        barra = self.pagina.locator('#navbar').bounding_box()
        # El índice sigue a la vista bajo la barra y el título queda justo debajo, no escondido detrás.
        self.assertAlmostEqual(indice['y'], barra['y'] + barra['height'], delta=2)
        self.assertGreaterEqual(titulo['y'], indice['y'] + indice['height'])
        self.assertLess(titulo['y'], 400)

    def test_mis_viajes_sugiere_destinos_y_pliega_agenda_y_pendientes(self):
        Viaje.objects.create(autor=self.usuario, nombre='Con agenda', destino='Tapalpa', personas=1, presupuesto=1,
                             fecha_inicio='2026-12-01', fecha_fin='2026-12-02',
                             actividades=[{'dia': 1, 'hora': '10:00', 'titulo': 'Caminar', 'notas': ''}])
        self.iniciar_sesion()
        self.abrir('/mis-viajes/')
        agenda, pendientes = self.pagina.locator('.trip-bloque').all()
        self.assertIsNone(agenda.get_attribute('open'))
        # El destino propone lugares del catálogo, pero elegir uno solo llena el campo: no sale de la página.
        self.pagina.fill('[name="destino"]', 'Mira')
        self.pagina.click('.buscador-opciones [role="option"]:has-text("Mirador")')
        self.assertEqual(self.pagina.input_value('[name="destino"]'), 'Mirador')
        self.assertTrue(self.pagina.url.endswith('/mis-viajes/'))
        # Al editar una escapada con agenda, ese bloque se abre solo y dice cuántas actividades tiene.
        self.pagina.on('dialog', lambda dialogo: dialogo.accept())
        self.pagina.locator('.trip-card button', has_text='Editar').click()
        self.assertIsNotNone(agenda.get_attribute('open'))
        self.assertEqual(agenda.locator('[data-cuenta]').inner_text(), '(1)')
        self.assertIsNone(pendientes.get_attribute('open'))

    def test_axo_se_aparta_mientras_se_escribe_en_un_formulario(self):
        self.pagina.set_viewport_size({'width': 375, 'height': 812})
        self.abrir('/mis-viajes/')
        axo = self.pagina.locator('#trip-chat')
        self.pagina.focus('[name="fecha_fin"]')
        self.assertEqual(axo.evaluate('el => getComputedStyle(el).opacity'), '0')
        self.assertEqual(axo.evaluate('el => getComputedStyle(el).pointerEvents'), 'none')
        # Al salir del campo vuelve, y sigue alcanzándose con el teclado.
        self.pagina.focus('#trip-chat-toggle')
        self.assertEqual(axo.evaluate('el => getComputedStyle(el).opacity'), '1')

    def abrir_con_saludo(self, ancho=1280, alto=800):
        self.contexto.close()
        self.contexto = self.nuevo_contexto(saludo=True, viewport={'width': ancho, 'height': alto})
        self.pagina = self.contexto.new_page()
        self.pagina.on('pageerror', lambda error: self.problemas.append(f'Error de página: {error}'))
        self.pagina.on('console', self.revisar_consola)
        self.abrir('/')
        self.pagina.locator('#trip-chat-saludo').wait_for(state='visible')

    def test_axo_saluda_una_vez_al_dia_y_la_burbuja_abre_el_chat(self):
        self.abrir_con_saludo()
        # La burbuja avisa sin robar el foco.
        self.assertFalse(self.pagina.evaluate("!!document.activeElement.closest('#trip-chat')"))
        self.pagina.click('#trip-chat-saludo-abrir')
        self.pagina.wait_for_selector('#trip-chat-panel:not([hidden])')
        self.assertTrue(self.pagina.locator('#trip-chat-saludo').is_hidden())
        self.assertIn('Axo', self.pagina.inner_text('#trip-chat-log'))
        # Ese mismo día ya no vuelve a aparecer.
        self.abrir('/destinos/')
        self.pagina.wait_for_timeout(2500)
        self.assertTrue(self.pagina.locator('#trip-chat-saludo').is_hidden())

    def test_la_burbuja_se_cierra_con_escape_y_no_desborda_en_movil(self):
        self.abrir_con_saludo(375, 812)
        caja = self.pagina.locator('#trip-chat-saludo').bounding_box()
        self.assertGreaterEqual(caja['x'], 0)
        self.assertLessEqual(caja['x'] + caja['width'], 375)
        self.assertLess(caja['width'], 300)
        self.assertEqual(self.pagina.evaluate('document.documentElement.scrollWidth'), 375)
        self.pagina.keyboard.press('Escape')
        self.assertTrue(self.pagina.locator('#trip-chat-saludo').is_hidden())

    def preguntar_a_axo(self, texto, espera):
        self.pagina.fill('#trip-chat-input', texto)
        self.pagina.press('#trip-chat-input', 'Enter')
        self.pagina.wait_for_selector(f'#trip-chat-log .trip-chat-message:not(.trip-chat-message-user):has-text("{espera}")')
        return self.pagina.locator('#trip-chat-log .trip-chat-message:not(.trip-chat-message-user)').last

    def test_axo_entiende_texto_libre_y_solo_muestra_destinos_reales(self):
        self.abrir('/')
        self.pagina.click('#trip-chat-toggle')
        respuesta = self.preguntar_a_axo('Quiero ir a Tapalpa', 'Encontré 1 destino')
        self.assertEqual(respuesta.locator('a').get_attribute('href'), '/destinos/mirador/')
        self.assertIn('Tapalpa', respuesta.inner_text())
        self.preguntar_a_axo('Narnia', 'No encontré «Narnia»')
        respuesta = self.preguntar_a_axo('¿Cuánto cuesta ir a Mirador?', 'costos reportados')
        self.assertEqual(respuesta.locator('a').get_attribute('href'), '/destinos/mirador/costos/')
        self.assertIn('INEGI', self.preguntar_a_axo('¿De dónde salen los datos?', 'OpenStreetMap').inner_text())
        self.preguntar_a_axo('costos', 'al menos 3 reportes')
        self.assertEqual(self.pagina.get_attribute('#trip-chat-options a', 'href'), '/costos/')
        self.preguntar_a_axo('olvidé mi contraseña', 'Recuperar contraseña')
        self.assertEqual(self.pagina.locator('#trip-chat-options a[href="/recuperar/"]').count(), 1)
        self.preguntar_a_axo('¿eres una IA?', 'No soy una inteligencia artificial')
        self.pagina.click('#trip-chat-reset')
        self.pagina.click('#trip-chat-options button:has-text("Planear mi escapada")')
        self.pagina.click('#trip-chat-options a:has-text("Abrir el planeador")')
        self.pagina.wait_for_url('**/planeador/')

    def test_axo_busca_lugares_cerca_con_la_ubicacion(self):
        Lugar.objects.create(nombre='Fonda Doña Ana', tipo='comer', subtipo='restaurant', latitud=19.901, longitud=-103.701,
                             osm_id='node/1')
        self.contexto.grant_permissions(['geolocation'], origin=self.live_server_url)
        self.contexto.set_geolocation({'latitude': 19.9, 'longitude': -103.7})
        self.abrir('/destinos/')
        self.pagina.click('#trip-chat-toggle')
        self.pagina.click('#trip-chat-options button:has-text("¿Qué hay cerca de mí?")')
        self.pagina.click('#trip-chat-options button:has-text("Buscar con mi ubicación")')
        self.pagina.wait_for_selector('#trip-chat-log a:has-text("Fonda Doña Ana")')
        fila = self.pagina.locator('.trip-chat-results li').first.inner_text()
        self.assertIn('Fuente: OpenStreetMap', fila)
        self.assertNotIn('Fuente: Fuente', fila)
        self.assertIn('m', fila)

    def test_axo_se_usa_con_teclado_y_es_comodo_de_tocar(self):
        self.abrir('/')
        self.pagina.focus('#trip-chat-toggle')
        self.pagina.keyboard.press('Enter')
        self.pagina.wait_for_selector('#trip-chat-panel:not([hidden])')
        self.assertEqual(self.pagina.evaluate('document.activeElement.id'), 'trip-chat-input')
        self.assertEqual(self.pagina.get_attribute('#trip-chat-log', 'aria-live'), 'polite')
        self.assertEqual(self.pagina.get_attribute('#trip-chat-toggle', 'aria-expanded'), 'true')
        pequenos = self.pagina.evaluate("""[...document.querySelectorAll('#trip-chat button, #trip-chat a, #trip-chat input')]
            .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.height < 44; })
            .map(e => e.textContent || e.id)""")
        self.assertEqual(pequenos, [])
        letra = self.pagina.evaluate("""[...document.querySelectorAll('#trip-chat-panel *')]
            .filter(e => e.offsetHeight > 1 && e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
            .filter(e => parseFloat(getComputedStyle(e).fontSize) < 16).map(e => e.textContent)""")
        self.assertEqual(letra, [])
        self.pagina.keyboard.press('Shift+Tab')
        self.assertEqual(self.pagina.evaluate('getComputedStyle(document.activeElement).outlineStyle'), 'solid')
        self.pagina.keyboard.press('Escape')
        self.assertTrue(self.pagina.locator('#trip-chat-panel').is_hidden())
        self.assertEqual(self.pagina.evaluate('document.activeElement.id'), 'trip-chat-toggle')

    def test_en_movil_el_panel_de_axo_cabe_bajo_la_barra(self):
        self.pagina.set_viewport_size({'width': 375, 'height': 812})
        self.abrir('/destinos/')
        self.pagina.click('#trip-chat-toggle')
        panel = self.pagina.locator('#trip-chat-panel').bounding_box()
        barra = self.pagina.locator('#navbar').bounding_box()
        self.assertGreaterEqual(panel['y'], barra['y'] + barra['height'])
        self.assertLessEqual(panel['x'] + panel['width'], 375)
        self.assertEqual(self.pagina.evaluate('document.documentElement.scrollWidth'), 375)

    def test_axo_no_se_mueve_con_movimiento_reducido(self):
        self.contexto.close()
        self.contexto = self.nuevo_contexto(reduced_motion='reduce')
        self.pagina = self.contexto.new_page()
        self.abrir('/')
        animacion = self.pagina.evaluate("getComputedStyle(document.querySelector('#trip-chat-toggle .pj-cuerpo')).animationName")
        self.assertEqual(animacion, 'none')

    def test_autocompletar_con_errores_y_solo_teclado(self):
        Destino.objects.create(nombre='Tlaquepaque', slug='tlaquepaque', municipio=self.destino.municipio,
                               descripcion='Pueblo de artesanos', latitud=20.6, longitud=-103.3)
        self.abrir('/')
        campo = self.pagina.locator('#destination-query')
        campo.press_sequentially('tlakepake')
        lista = self.pagina.locator('#' + campo.get_attribute('aria-controls'))
        opcion = lista.get_by_role('option', name=re.compile('Tlaquepaque'))
        opcion.first.wait_for()
        self.assertEqual(campo.get_attribute('aria-expanded'), 'true')
        campo.press('ArrowDown')
        primera = lista.get_by_role('option').first
        self.assertEqual(campo.get_attribute('aria-activedescendant'), primera.get_attribute('id'))
        campo.press('Escape')
        self.assertEqual(campo.get_attribute('aria-expanded'), 'false')
        campo.press('ArrowDown')
        campo.press('ArrowDown')
        campo.press('Enter')
        self.pagina.wait_for_url(re.compile('/destinos/tlaquepaque/'))

    def test_explorar_sugiere_cuando_hay_errores_y_conserva_filtros(self):
        self.abrir('/destinos/?q=tapqlpa')
        self.assertIn('¿Quisiste decir', self.pagina.locator('.search-suggestion').inner_text())
        self.pagina.locator('.search-suggestion a').click()
        self.pagina.wait_for_url(re.compile(r'q=Tapalpa'))
        campo = self.pagina.locator('#id_q')
        self.assertEqual(campo.get_attribute('role'), 'combobox')
        campo.fill('')
        campo.press_sequentially('mira')
        self.pagina.locator('[role="option"]', has_text='Mirador').first.wait_for()
