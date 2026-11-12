"""Accesibilidad automática con axe-core (WCAG 2.2 A y AA) en Chromium.

axe se carga desde e2e/vendor/ (versión fija, sin CDN): solo existe en las pruebas, nunca en producción.
Cada página se revisa en tema claro y oscuro, en escritorio y en móvil. Fallan las violaciones
`serious` y `critical`; las `moderate` y `minor` se listan en docs/auditoria-accesibilidad.md.

Ejecución:  E2E=1 python manage.py test e2e --settings=infotrip.settings.test
"""
import json
import os
import re
from datetime import date
from pathlib import Path
from unittest import skipUnless

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache

from apps.comunidad.models import Aporte
from apps.destinos.models import Categoria, Destino, Municipio, Region
from apps.usuarios.models import Usuario

AXE = Path(__file__).parent / 'vendor' / 'axe-4.10.3.min.js'
ETIQUETAS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
GRAVES = {'serious', 'critical'}
SIN_SALUDO = "try { localStorage.setItem('infotrip_axo_saludo', new Date().toLocaleDateString('en-CA')); } catch {}"
TEMA = "try { localStorage.setItem('infotrip_tema', '%s'); } catch {}"
# Describe el elemento enfocado: si se ve (dentro de la ventana y sin taparse) y si tiene indicador de foco.
FOCO = '''(() => {
  const e = document.activeElement;
  if (!e || e === document.body) return null;
  const r = e.getBoundingClientRect();
  // El indicador puede estar en el propio elemento o en su contenedor (p. ej. la barra de búsqueda con :has()).
  const marcado = n => { const s = getComputedStyle(n);
    return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 2) || s.boxShadow !== 'none'; };
  const indicador = [e, e.parentElement, e.parentElement?.parentElement].some(n => n && marcado(n));
  const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1);
  const y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
  const encima = document.elementFromPoint(x, y);
  const visible = r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0
    && r.left < innerWidth && !!encima && (e.contains(encima) || encima.contains(e)
    || !!encima.closest('.leaflet-container') && !!e.closest('.leaflet-container'));
  const nombre = (e.getAttribute('aria-label') || e.textContent || e.name || '').trim().replace(/\\s+/g, ' ');
  return {clave: e.tagName + '#' + e.id + '.' + e.className + ':' + nombre.slice(0, 40), indicador, visible,
          tapa: encima ? encima.tagName + '#' + encima.id + '.' + encima.className : null,
          contorno: getComputedStyle(e).outline, foco_visible: e.matches(':focus-visible')};
})()'''


def armar_ruta(pagina):
    pagina.check('#ruta-form input[value="miradores"]')
    pagina.check('#ruta-form [name="dias"][value="2"]')
    pagina.click('#ruta-form button[type="submit"]')
    pagina.wait_for_selector('#ruta-detalle .parada')


def abrir_chat(pagina):
    pagina.click('#trip-chat-toggle')
    pagina.wait_for_selector('#trip-chat-panel:not([hidden])')
    pagina.fill('#trip-chat-input', 'Quiero ir a Tapalpa')
    pagina.press('#trip-chat-input', 'Enter')
    pagina.wait_for_selector('#trip-chat-log a[href="/destinos/mirador/"]')


VARIANTES = {
    'claro-escritorio': {'tema': 'light', 'viewport': {'width': 1280, 'height': 800}},
    'oscuro-escritorio': {'tema': 'dark', 'viewport': {'width': 1280, 'height': 800}},
    'claro-movil': {'tema': 'light', 'viewport': {'width': 375, 'height': 812}, 'has_touch': True},
    'oscuro-movil': {'tema': 'dark', 'viewport': {'width': 375, 'height': 812}, 'has_touch': True},
}


@skipUnless(os.environ.get('E2E'), 'Pruebas de navegador: definir E2E=1')
class AccesibilidadTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
        from playwright.sync_api import sync_playwright
        super().setUpClass()
        cls.axe = AXE.read_text(encoding='utf-8')
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
        self.destino.categorias.add(Categoria.objects.create(nombre='Miradores', slug='miradores'))
        autor = Usuario.objects.create_user('ana@example.com', 'Ana', 'Prueba', 'Prueba-segura-493!',
                                            es_verificado=True)
        # Tres gastos publicados: la página de costos muestra su resumen en lugar del aviso vacío.
        for numero, monto in enumerate([120, 150, 180]):
            Aporte.objects.create(destino=self.destino, autor=autor if numero == 0 else Usuario.objects.create_user(
                f'u{numero}@example.com', 'U', 'P', 'Prueba-segura-493!', es_verificado=True),
                tipo='gasto', concepto='comida', monto=monto, texto='Comida', fecha_visita=date.today(),
                estado='publicado')

    def revisar(self, ruta, preparar=None):
        """Abre `ruta` en cada variante, ejecuta `preparar(pagina)` y devuelve las violaciones graves."""
        for nombre, variante in VARIANTES.items():
            with self.subTest(ruta=ruta, variante=nombre):
                opciones = {k: v for k, v in variante.items() if k != 'tema'}
                contexto = self.navegador.new_context(color_scheme=variante['tema'], reduced_motion='reduce',
                                                      **opciones)
                contexto.add_init_script(SIN_SALUDO)
                contexto.add_init_script(TEMA % variante['tema'])
                pagina = contexto.new_page()
                try:
                    pagina.goto(self.live_server_url + ruta)
                    pagina.wait_for_load_state('networkidle')
                    if preparar:
                        preparar(pagina)
                    self.assertEqual(pagina.evaluate('document.documentElement.dataset.theme'), variante['tema'])
                    graves = self.violaciones(pagina)
                finally:
                    pagina.wait_for_load_state('networkidle')
                    contexto.close()
                self.assertEqual(graves, [], f'{ruta} ({nombre})')

    def violaciones(self, pagina):
        # evaluate() corre fuera de la CSP de la página: no hace falta relajarla para inyectar axe.
        pagina.evaluate(self.axe)
        resultado = pagina.evaluate('''etiquetas => axe.run(document, {runOnly: {type: 'tag', values: etiquetas}})
            .then(r => r.violations.map(v => ({id: v.id, impacto: v.impact,
                nodos: v.nodes.map(n => n.target.join(' ') + (n.failureSummary ? ' :: ' + n.failureSummary
                    .replace(/\\s+/g, ' ').slice(0, 160) : ''))})))''', ETIQUETAS)
        if os.environ.get('AXE_INFORME'):
            # Para el informe: guarda también las moderadas y menores, que no hacen fallar la prueba.
            with open(os.environ['AXE_INFORME'], 'a', encoding='utf-8') as archivo:
                archivo.write(json.dumps({'url': pagina.url, 'violaciones': resultado}, ensure_ascii=False) + '\n')
        return [v for v in resultado if v['impacto'] in GRAVES]

    def pagina_nueva(self, ruta, tema='light', saludo=False, sin_fuentes=False, **opciones):
        contexto = self.navegador.new_context(color_scheme=tema, **opciones)
        if not saludo:
            contexto.add_init_script(SIN_SALUDO)
        if sin_fuentes:
            # La llegada de Geist (static/fonts/) también mueve el texto: se compara con la fuente del sistema.
            contexto.route(re.compile(r'.*/fonts/geist/.*\.woff2$'), lambda ruta: ruta.abort())
        contexto.add_init_script(TEMA % tema)
        self.addCleanup(contexto.close)
        pagina = contexto.new_page()
        pagina.goto(self.live_server_url + ruta)
        pagina.wait_for_load_state('networkidle')
        return pagina

    def recorrer_con_tab(self, pagina, maximo=120):
        """Pulsa Tab hasta dar la vuelta; devuelve los elementos sin foco visible o fuera de la pantalla."""
        problemas, vistos = [], []
        for _ in range(maximo):
            pagina.keyboard.press('Tab')
            estado = pagina.evaluate(FOCO)
            if estado is None or estado['clave'] in vistos[:1]:
                break
            vistos.append(estado['clave'])
            if not estado['indicador'] or not estado['visible']:
                problemas.append(estado)
        return vistos, problemas

    def test_portada(self):
        self.revisar('/')

    def test_explorar_destinos(self):
        self.revisar('/destinos/')

    def test_ficha_de_destino(self):
        self.revisar('/destinos/mirador/')

    def test_costos_de_un_destino(self):
        self.revisar('/destinos/mirador/costos/')

    def test_costos(self):
        self.revisar('/costos/')

    def test_planeador_vacio(self):
        self.revisar('/planeador/')

    def test_planeador_con_ruta(self):
        self.revisar('/planeador/', armar_ruta)

    def test_pasaporte(self):
        self.revisar('/pasaporte/')

    def test_login(self):
        self.revisar('/login/')

    def test_registro(self):
        self.revisar('/registro/')

    def test_privacidad(self):
        self.revisar('/privacidad/')

    def test_perfil_publico(self):
        Usuario.objects.filter(email='ana@example.com').update(username='ana', visibilidad='publico')
        self.revisar('/u/ana/', lambda pagina: pagina.wait_for_selector('#perfil-pasaporte:not([hidden])'))

    def test_amigos_y_elegir_usuario_sin_sesion(self):
        self.revisar('/amigos/')
        self.revisar('/elegir-usuario/')

    def test_chatbot_abierto(self):
        self.revisar('/', abrir_chat)


PAGINAS = ['/', '/destinos/', '/destinos/mirador/', '/destinos/mirador/costos/', '/costos/', '/planeador/',
           '/pasaporte/', '/login/', '/registro/', '/privacidad/']


@skipUnless(os.environ.get('E2E'), 'Pruebas de navegador: definir E2E=1')
class RevisionManualTests(AccesibilidadTests):
    """Lo que axe no ve: recorrido con el teclado, foco visible y no tapado, reflow y movimiento reducido."""

    # Las pruebas de axe ya corren en la clase madre; aquí no se repiten.
    test_portada = test_explorar_destinos = test_ficha_de_destino = test_costos_de_un_destino = None
    test_costos = test_planeador_vacio = test_planeador_con_ruta = test_pasaporte = None
    test_login = test_registro = test_privacidad = test_chatbot_abierto = None
    test_perfil_publico = test_amigos_y_elegir_usuario_sin_sesion = None

    def test_con_tab_todo_se_alcanza_y_el_foco_se_ve(self):
        casos = [(ruta, None) for ruta in PAGINAS] + [('/planeador/', armar_ruta), ('/', abrir_chat)]
        for ruta, preparar in casos:
            for nombre, viewport in [('escritorio', {'width': 1280, 'height': 800}),
                                     ('movil', {'width': 375, 'height': 812})]:
                with self.subTest(ruta=ruta, preparar=getattr(preparar, '__name__', ''), variante=nombre):
                    pagina = self.pagina_nueva(ruta, viewport=viewport)
                    if preparar:
                        preparar(pagina)
                        # Desde lo que se acaba de abrir, el recorrido sigue y da la vuelta a toda la página.
                        self.assertNotEqual(pagina.evaluate('document.activeElement.tagName'), 'BODY')
                        _, problemas = self.recorrer_con_tab(pagina)
                        self.assertEqual(problemas, [])
                        continue
                    vistos, problemas = self.recorrer_con_tab(pagina)
                    # Con barra de navegación, el primer Tab lleva al enlace para saltarla (WCAG 2.4.1).
                    if pagina.locator('#navbar').count():
                        self.assertTrue(vistos and vistos[0].startswith('A#.skip-link'), vistos[:1])
                        # Y lleva de verdad al contenido principal.
                        pagina.focus('.skip-link')
                        pagina.keyboard.press('Enter')
                        self.assertEqual(pagina.evaluate('document.activeElement.tagName'), 'MAIN')
                    self.assertEqual(problemas, [])

    def test_al_armar_la_ruta_el_foco_no_cae_al_inicio(self):
        # El botón se deshabilita mientras se arma la ruta y Chromium manda el foco a <body>; al terminar,
        # planeador.js enfoca el resumen (role=status), que anuncia el resultado. Con Tab se sigue desde ahí.
        pagina = self.pagina_nueva('/planeador/')
        pagina.check('#ruta-form input[value="miradores"]')
        pagina.focus('#ruta-form button[type="submit"]')
        pagina.keyboard.press('Enter')
        pagina.wait_for_selector('#ruta-detalle .parada')
        self.assertEqual(pagina.evaluate('document.activeElement.id'), 'ruta-resumen')
        self.assertEqual(pagina.get_attribute('#ruta-resumen', 'role'), 'status')

    def test_el_saludo_de_axo_no_mueve_la_pagina(self):
        # Lighthouse medía un CLS de 0,032 en cada página: la burbuja agrandaba el contenedor de Axo.
        # El cambio de fuente se deja fuera (pendiente en docs/auditoria-accesibilidad.md).
        for viewport in ({'width': 1280, 'height': 800}, {'width': 375, 'height': 812}):
            with self.subTest(ancho=viewport['width']):
                pagina = self.pagina_nueva('/', saludo=True, sin_fuentes=True, viewport=viewport)
                pagina.evaluate('''window.__cls = 0; new PerformanceObserver(lista => lista.getEntries()
                    .forEach(e => { if (!e.hadRecentInput) window.__cls += e.value; }))
                    .observe({type: 'layout-shift', buffered: true})''')
                pagina.locator('#trip-chat-saludo').wait_for(state='visible')
                pagina.wait_for_timeout(500)
                self.assertLess(pagina.evaluate('window.__cls'), 0.01)

    def test_sin_scroll_horizontal_con_zoom(self):
        # 320 px de ancho equivalen a 1280 px con zoom al 400 % (WCAG 1.4.10); 640 px, al 200 %.
        for ruta in PAGINAS:
            for ancho in (640, 320):
                with self.subTest(ruta=ruta, ancho=ancho):
                    pagina = self.pagina_nueva(ruta, viewport={'width': ancho, 'height': 720})
                    desbordan = pagina.evaluate('''ancho => [...document.querySelectorAll('body *')]
                        .filter(e => !e.closest('.leaflet-container, .sr-only, [hidden]'))
                        .filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > ancho + 1; })
                        .filter(e => !e.parentElement.closest('*') || getComputedStyle(e.parentElement).overflowX
                            === 'visible')
                        .map(e => e.tagName + '.' + e.className).slice(0, 5)''', ancho)
                    self.assertEqual(pagina.evaluate('document.documentElement.scrollWidth'), ancho, desbordan)

    def test_movimiento_reducido_detiene_animaciones(self):
        for ruta in PAGINAS:
            with self.subTest(ruta=ruta):
                pagina = self.pagina_nueva(ruta, reduced_motion='reduce')
                moviendose = pagina.evaluate('''document.getAnimations()
                    .filter(a => a.playState === 'running' && (a.effect.getComputedTiming().duration > 1
                        || a.effect.getComputedTiming().iterations === Infinity))
                    .map(a => (a.animationName || a.transitionProperty) + ' @ ' + a.effect.target.className)''')
                self.assertEqual(moviendose, [])
