from datetime import timedelta
from io import StringIO
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.comunidad.models import Aporte
from apps.usuarios.models import Usuario
from .fotos import FOTOS_CATALOGO
from .models import Categoria, Destino, Region, Municipio, Servicio


class PaginasDestinoTests(TestCase):
    def crear_destino(self, **cambios):
        region, _ = Region.objects.get_or_create(nombre='Región prueba', slug='region-prueba')
        municipio, _ = Municipio.objects.get_or_create(nombre='Municipio prueba', slug='municipio-prueba', region=region)
        campos = dict(nombre='Lugar de prueba', slug='lugar-prueba', descripcion='Senderos y descanso', municipio=municipio,
                      latitud='20.123456', longitud='-103.654321', direccion='Calle de prueba 10')
        campos.update(cambios)
        return Destino.objects.create(**campos)

    def test_portada_breve_con_enlaces_editoriales(self):
        respuesta = self.client.get('/')
        self.assertContains(respuesta, 'name="q"')
        self.assertContains(respuesta, '/destinos/tequila/')
        self.assertNotContains(respuesta, 'id="resenas"')
        self.assertEqual(len(respuesta.context['lugares']), 2)

    def test_detalle_editorial_y_404(self):
        respuesta = self.client.get('/destinos/tequila/')
        self.assertContains(respuesta, 'Selección de inspiración')
        self.assertContains(respuesta, 'google.com/maps/dir/')
        self.assertEqual(self.client.get('/destinos/no-existe/').status_code, 404)

    def test_busqueda_editorial_y_vacia(self):
        respuesta = self.client.get('/destinos/', {'q': 'TEQUILA'})
        self.assertEqual(len(respuesta.context['lugares']), 1)
        self.assertEqual(respuesta.context['lugares'][0]['slug'], 'tequila')
        self.assertContains(self.client.get('/destinos/', {'q': 'no-existe'}), 'No hay destinos para mostrar')

    def test_detalle_real_servicios_coordenadas_y_escapado(self):
        destino = self.crear_destino(descripcion='<script>alert(1)</script>')
        servicio = Servicio.objects.create(nombre='Estacionamiento', slug='estacionamiento')
        destino.servicios.add(servicio)
        respuesta = self.client.get(reverse('destino-detalle', kwargs={'slug': destino.slug}))
        self.assertContains(respuesta, 'Estacionamiento')
        self.assertContains(respuesta, '20.123456%2C-103.654321')
        self.assertContains(respuesta, 'Calle de prueba 10')
        self.assertContains(respuesta, '&lt;script&gt;')
        self.assertNotContains(respuesta, '<script>alert(1)</script>')
        self.assertContains(respuesta, 'Las fotografías de este destino estarán disponibles pronto.')

    def test_no_reaparece_destino_inactivo_como_editorial(self):
        self.crear_destino(slug='tequila', es_activo=False)
        self.assertEqual(self.client.get('/destinos/tequila/').status_code, 404)
        self.assertEqual(len(self.client.get('/').context['lugares']), 0)
        self.assertEqual(len(self.client.get('/destinos/').context['lugares']), 0)

    def test_portada_maximo_tres_y_busqueda_en_catalogo(self):
        for numero in range(10):
            self.crear_destino(nombre=f'Destino {numero}', slug=f'destino-{numero}')
        self.assertEqual(len(self.client.get('/').context['lugares']), 3)
        respuesta = self.client.get('/destinos/', {'q': 'Municipio prueba', 'page': 2})
        self.assertEqual(len(respuesta.context['lugares']), 2)
        self.assertEqual(respuesta.context['pagina'].paginator.count, 10)
        self.assertContains(respuesta, 'q=Municipio+prueba')

    def test_mapa_editorial_y_catalogo_usan_destino_correcto(self):
        lugares = self.client.get('/').context['exploracion']
        tequila = next(lugar for lugar in lugares if lugar['slug'] == 'tequila')
        self.assertIn('q=Tequila%2C+Jalisco', tequila['mapa_embed'])
        self.crear_destino()
        respuesta = self.client.get('/')
        self.assertIn('q=20.123456%2C-103.654321', respuesta.context['exploracion'][0]['mapa_embed'])
        self.assertContains(respuesta, 'id="preview-map"')
        self.assertNotContains(respuesta, '<iframe src=')

    def test_datos_interactivos_escapan_contenido_y_excluyen_inactivos(self):
        self.crear_destino(nombre='</script><script>alert(1)</script>')
        self.crear_destino(slug='oculto', es_activo=False)
        respuesta = self.client.get('/')
        self.assertEqual(len(respuesta.context['exploracion']), 1)
        self.assertNotContains(respuesta, '</script><script>alert(1)</script>')

class ExploracionMapaTests(TestCase):
    crear_destino = PaginasDestinoTests.crear_destino

    def test_filtros_combinados_y_paginacion(self):
        categoria = Categoria.objects.create(nombre='Naturaleza', slug='naturaleza')
        servicio = Servicio.objects.create(nombre='Baños', slug='banos')
        for numero in range(10):
            destino = self.crear_destino(nombre=f'Bosque {numero}', slug=f'bosque-{numero}')
            destino.categorias.add(categoria)
            destino.servicios.add(servicio)
        self.crear_destino(slug='sin-servicio')
        respuesta = self.client.get('/destinos/', {'categoria': 'naturaleza', 'servicio': 'banos',
            'municipio': 'municipio-prueba', 'region': 'region-prueba', 'page': 2})
        self.assertEqual(respuesta.context['pagina'].paginator.count, 10)
        self.assertEqual(len(respuesta.context['puntos_mapa']), 2)
        self.assertContains(respuesta, 'servicio=banos')
        self.assertContains(respuesta, 'municipio=municipio-prueba')

    def test_filtro_invalido_no_devuelve_catalogo_completo(self):
        self.crear_destino()
        respuesta = self.client.get('/destinos/', {'municipio': 'desconocido'})
        self.assertTrue(respuesta.context['formulario'].errors)
        self.assertEqual(respuesta.context['puntos_mapa'], [])
        self.assertEqual(respuesta.context['pagina'].paginator.count, 0)

    def test_marcadores_solo_activos_y_json_seguro(self):
        self.crear_destino(nombre='</script><script>alert(1)</script>')
        self.crear_destino(slug='oculto', es_activo=False)
        respuesta = self.client.get('/destinos/')
        self.assertEqual(len(respuesta.context['puntos_mapa']), 1)
        self.assertEqual(respuesta.context['puntos_mapa'][0]['latitud'], '20.123456')
        self.assertNotContains(respuesta, '</script><script>alert(1)</script>')

    def test_editorial_filtrada_sin_coordenadas_inventadas(self):
        respuesta = self.client.get('/destinos/', {'municipio': 'tequila', 'categoria': 'pueblos'})
        self.assertEqual(respuesta.context['pagina'].paginator.count, 1)
        self.assertEqual(respuesta.context['puntos_mapa'], [])
        self.assertContains(respuesta, 'no tienen coordenadas registradas')


class FiltrosCompartidosTests(TestCase):
    """La API y la exploración HTML filtran con FiltroDestinos y deben coincidir."""

    def setUp(self):
        hoy = timezone.localdate()
        autor = Usuario.objects.create_user('filtros@example.com', 'Ana', 'Prueba', 'Clave-segura-483!')
        norte = Region.objects.create(nombre='Norte', slug='norte')
        sur = Region.objects.create(nombre='Sur', slug='sur')
        municipios = [Municipio.objects.create(nombre=f'Municipio {r.slug}', slug=f'municipio-{r.slug}', region=r)
                      for r in (norte, sur)]
        naturaleza = Categoria.objects.create(nombre='Naturaleza', slug='naturaleza')
        pueblos = Categoria.objects.create(nombre='Pueblos', slug='pueblos')
        banos = Servicio.objects.create(nombre='Baños', slug='banos')
        for numero in range(6):
            destino = Destino.objects.create(
                nombre=f'Lugar {numero}', slug=f'lugar-{numero}', municipio=municipios[numero % 2],
                descripcion='Cascada escondida' if numero < 3 else 'Plaza principal', latitud=20, longitud=-103)
            destino.categorias.add(naturaleza if numero % 3 else pueblos)
            if numero % 2:
                destino.servicios.add(banos)
            Aporte.objects.create(autor=autor, destino=destino, tipo='resena', texto='Reseña', fecha_visita=hoy,
                                  calificacion=numero % 5 + 1, estado='publicado')
            Aporte.objects.create(autor=autor, destino=destino, tipo='gasto', texto='Gasto', fecha_visita=hoy - timedelta(days=5),
                                  monto=100 * (numero + 1), concepto='comida', estado='publicado')
        Destino.objects.create(nombre='Lugar oculto', slug='oculto', municipio=municipios[0], descripcion='Cascada',
                               latitud=20, longitud=-103, es_activo=False)

    def slugs_api(self, filtros):
        respuesta = self.client.get('/api/v1/destinos/', filtros)
        self.assertEqual(respuesta.status_code, 200)
        return {destino['slug'] for destino in respuesta.data['results']}

    def slugs_web(self, filtros):
        respuesta = self.client.get('/destinos/', filtros)
        self.assertFalse(respuesta.context['formulario'].errors)
        return {lugar['slug'] for lugar in respuesta.context['lugares']}

    def test_api_y_web_devuelven_los_mismos_destinos(self):
        casos = [
            {}, {'q': 'cascada'}, {'q': 'municipio norte'}, {'categoria': 'naturaleza'}, {'region': 'sur'},
            {'municipio': 'municipio-norte', 'servicio': 'banos'}, {'calificacion_min': '3'},
            {'concepto': 'comida'}, {'concepto': 'comida', 'precio_max': '350'},
            {'q': 'plaza', 'categoria': 'naturaleza', 'calificacion_min': '4'},
        ]
        for filtros in casos:
            with self.subTest(filtros=filtros):
                api, web = self.slugs_api(filtros), self.slugs_web(filtros)
                self.assertEqual(api, web)
                self.assertNotIn('oculto', api)
        self.assertEqual(self.slugs_api({'concepto': 'comida', 'precio_max': '350'}), {'lugar-0', 'lugar-1', 'lugar-2'})


class CatalogoInicialTests(TestCase):
    def test_carga_15_destinos_con_municipio_correcto_y_es_idempotente(self):
        call_command('cargar_destinos_iniciales', stdout=StringIO())
        call_command('cargar_destinos_iniciales', stdout=StringIO())
        self.assertEqual(Destino.objects.count(), 15)
        self.assertEqual(Destino.objects.get(slug='ajijic').municipio.nombre, 'Chapala')
        self.assertEqual(Destino.objects.get(slug='guachimontones').municipio.nombre, 'Teuchitlán')
        self.assertEqual(Destino.objects.get(slug='tonala').municipio.nombre, 'Tonalá')

    def test_las_fotos_del_catalogo_existen_y_llevan_credito(self):
        for slug, foto in FOTOS_CATALOGO.items():
            with self.subTest(slug=slug):
                self.assertIsNotNone(finders.find(foto['imagen']))
                self.assertTrue(foto['autor'] and foto['licencia_url'] and foto['alt'])
        call_command('cargar_destinos_iniciales', stdout=StringIO())
        ficha = self.client.get('/destinos/guachimontones/')
        self.assertContains(ficha, 'Esteban Tucci')
        self.assertContains(ficha, 'images/destinos/guachimontones.jpg')
        creditos = self.client.get('/creditos/')
        self.assertContains(creditos, 'Esteban Tucci')
        self.assertContains(creditos, 'CC BY-SA 4.0')

    def test_la_foto_de_la_comunidad_reemplaza_a_la_del_catalogo_sin_su_credito(self):
        call_command('cargar_destinos_iniciales', stdout=StringIO())
        destino = Destino.objects.get(slug='guachimontones')
        autor = Usuario.objects.create_user('f@example.com', 'Ana', 'P', 'Prueba-segura-493!')
        Aporte.objects.create(autor=autor, destino=destino, tipo='foto', texto='Mi foto', imagen='comunidad/x.jpg',
                              fecha_visita=timezone.localdate(), estado='publicado')
        ficha = self.client.get('/destinos/guachimontones/')
        self.assertEqual(ficha.context['lugar']['alt'], 'Mi foto')
        self.assertNotContains(ficha, 'Esteban Tucci')


class FiltrosSinValorTests(TestCase):
    def test_una_casilla_sin_marcar_no_cuenta_como_filtro(self):
        self.assertEqual(self.client.get('/destinos/').context['filtros'], '')
        self.assertContains(self.client.get('/destinos/'), 'data-activos="false"')
        self.assertContains(self.client.get('/destinos/', {'q': 'lago'}), 'data-activos="true"')
