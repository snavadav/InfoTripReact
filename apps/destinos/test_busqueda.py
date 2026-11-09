"""Búsqueda tolerante: errores de escritura, acentos, sinónimos, sugerencias y que los filtros sigan igual."""
from unittest import skipUnless

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from .busqueda import fonetica, interpretar, sin_acentos
from .models import Categoria, Destino, Lugar, Municipio, Region, Servicio


class NormalizacionTests(SimpleTestCase):
    def test_acentos_mayusculas_y_signos(self):
        self.assertEqual(sin_acentos('  ¡MAZAMITLA!  Teuchitlán '), 'mazamitla teuchitlan')

    def test_clave_fonetica_del_espanol(self):
        for escrito, catalogo in [('tlakepake', 'tlaquepaque'), ('masamitla', 'mazamitla'), ('ajijik', 'ajijic'),
                                  ('bayarta', 'vallarta'), ('lagos', 'lago'), ('miradores', 'mirador'),
                                  ('piramides', 'piramide')]:
            with self.subTest(escrito=escrito):
                self.assertEqual(fonetica(escrito), fonetica(catalogo))

    def test_ch_no_se_confunde_con_c(self):
        self.assertNotEqual(fonetica('chapala'), fonetica('capala'))

    def test_palabras_vacias_y_abreviaturas(self):
        self.assertEqual([p for _, p in interpretar('Chapala y el lago').palabras], ['chapala', 'lago'])
        self.assertEqual([p for _, p in interpretar('GDL').palabras], ['guadalajara'])
        self.assertTrue(interpretar('pueblos mágicos').sinonimos)


class BusquedaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        centro = Region.objects.create(nombre='Centro de Jalisco', slug='centro')
        sur = Region.objects.create(nombre='Sierra de Jalisco', slug='sierra')
        ribera = Region.objects.create(nombre='Ribera de Chapala', slug='ribera')
        costa_region = Region.objects.create(nombre='Costa de Jalisco', slug='costa-de-jalisco')
        cls.municipios = {
            slug: Municipio.objects.create(nombre=nombre, slug=slug, region=region)
            for slug, nombre, region in [
                ('tlaquepaque', 'Tlaquepaque', centro), ('guadalajara', 'Guadalajara', centro),
                ('mazamitla', 'Mazamitla', sur), ('chapala', 'Chapala', ribera),
                ('teuchitlan', 'Teuchitlán', centro), ('talpa', 'Talpa de Allende', sur),
                ('tapalpa', 'Tapalpa', sur), ('cihuatlan', 'Cihuatlán', costa_region),
            ]
        }
        cls.pueblos = Categoria.objects.create(nombre='Pueblos', slug='pueblos')
        cls.lago = Categoria.objects.create(nombre='Lago', slug='lago')
        cls.costa = Categoria.objects.create(nombre='Costa', slug='costa')
        cls.servicio = Servicio.objects.create(nombre='Estacionamiento', slug='estacionamiento')

        def destino(nombre, slug, municipio, descripcion='Un lugar para visitar.', categorias=(), activo=True):
            nuevo = Destino.objects.create(nombre=nombre, slug=slug, descripcion=descripcion, latitud=20,
                                           longitud=-103, municipio=cls.municipios[municipio], es_activo=activo)
            nuevo.categorias.set(categorias)
            return nuevo

        cls.tlaquepaque = destino('Tlaquepaque', 'tlaquepaque', 'tlaquepaque', categorias=[cls.pueblos])
        cls.museo = destino('Museo del Premio Nacional de la Cerámica', 'museo-ceramica', 'tlaquepaque')
        cls.mazamitla = destino('Mazamitla', 'mazamitla', 'mazamitla', 'Pueblo de la sierra con bosque.',
                                [cls.pueblos])
        cls.letras = destino('Letras MAZAMITLA', 'letras-mazamitla', 'mazamitla')
        cls.cascada = destino('Cascada El Salto', 'cascada-el-salto', 'mazamitla')
        cls.chapala = destino('Chapala', 'chapala', 'chapala', 'Malecón junto al lago.', [cls.lago])
        cls.ajijic = destino('Ajijic', 'ajijic', 'chapala', 'Pueblo a la orilla del lago.', [cls.lago])
        cls.catedral = destino('Catedral de Guadalajara', 'catedral', 'guadalajara')
        cls.guachimontones = destino('Guachimontones', 'guachimontones', 'teuchitlan', 'Zona arqueológica.')
        cls.talpa = destino('Talpa de Allende', 'talpa-de-allende', 'talpa', categorias=[cls.pueblos])
        cls.tapalpa = destino('Tapalpa', 'tapalpa', 'tapalpa', categorias=[cls.pueblos])
        cls.melaque = destino('Barra de Navidad', 'barra-de-navidad', 'cihuatlan', 'Bahía tranquila.', [cls.costa])
        cls.oculto = destino('Mazamitla secreta', 'mazamitla-secreta', 'mazamitla', activo=False)
        cls.mazamitla.servicios.add(cls.servicio)

    def buscar(self, q, **filtros):
        respuesta = self.client.get('/api/v1/destinos/', {'q': q, **filtros})
        self.assertEqual(respuesta.status_code, 200)
        return [destino['slug'] for destino in respuesta.data['results']], respuesta.data['sugerencia']

    def test_errores_de_escritura_tipicos(self):
        for q, esperado in [('tlakepake', 'tlaquepaque'), ('tlaque', 'tlaquepaque'), ('mazamtla', 'mazamitla'),
                            ('masamitla', 'mazamitla'), ('guachimontonez', 'guachimontones'),
                            ('ajijik', 'ajijic')]:
            with self.subTest(q=q):
                resultados, _ = self.buscar(q)
                self.assertEqual(resultados[0], esperado)

    def test_mayusculas_y_acentos(self):
        for q in ['mazamitla', 'MAZAMITLA', 'Mazamítla', '  mazamitla  ']:
            with self.subTest(q=q):
                self.assertEqual(self.buscar(q)[0][0], 'mazamitla')
        # El municipio se llama «Teuchitlán»; escrito sin acento también aparece.
        self.assertIn('guachimontones', self.buscar('teuchitlan')[0])

    def test_relevancia_nombre_exacto_luego_municipio(self):
        resultados, _ = self.buscar('mazamitla')
        self.assertEqual(resultados[0], 'mazamitla')
        self.assertEqual(set(resultados), {'mazamitla', 'letras-mazamitla', 'cascada-el-salto'})
        self.assertLess(resultados.index('letras-mazamitla'), resultados.index('cascada-el-salto'))

    def test_varias_palabras(self):
        resultados, _ = self.buscar('chapala lago')
        self.assertEqual(resultados[0], 'chapala')
        self.assertIn('ajijic', resultados)
        self.assertNotIn('tapalpa', resultados)

    def test_sinonimos(self):
        resultados, _ = self.buscar('pueblo magico')
        # Lista oficial de Pueblos Mágicos (comunidad.selectors.PUEBLOS_MAGICOS), no la categoría.
        self.assertEqual(set(resultados), {'tlaquepaque', 'mazamitla', 'talpa-de-allende', 'tapalpa', 'ajijic'})
        self.assertEqual(set(self.buscar('Pueblos Mágicos')[0]), set(resultados))
        self.assertEqual(self.buscar('playa')[0], ['barra-de-navidad'])
        self.assertEqual(self.buscar('gdl')[0], ['catedral'])
        self.assertEqual(self.buscar('piramides')[0], [])  # Sin categoría de arqueología no inventa resultados.

    def test_una_palabra_exacta_no_se_corrige(self):
        # «talpa» existe tal cual: no debe traer «Tapalpa» por parecido.
        resultados, sugerencia = self.buscar('talpa')
        self.assertEqual(resultados, ['talpa-de-allende'])
        self.assertEqual(sugerencia, '')

    def test_quisiste_decir(self):
        _, sugerencia = self.buscar('mazamtla')
        self.assertEqual(sugerencia, 'Mazamitla')
        self.assertEqual(self.buscar('mazamitla')[1], '')
        resultados, sugerencia = self.buscar('xyzqw')
        self.assertEqual((resultados, sugerencia), ([], ''))

    def test_sugerencia_sin_resultados(self):
        resultados, sugerencia = self.buscar('mazamitla tapalpa')
        self.assertEqual(resultados, [])
        self.assertIn(sugerencia, {'Mazamitla', 'Tapalpa'})

    def test_no_muestra_destinos_ocultos(self):
        self.assertNotIn('mazamitla-secreta', self.buscar('secreta')[0])

    def test_filtros_siguen_funcionando_con_busqueda(self):
        self.assertEqual(set(self.buscar('lago', categoria='lago')[0]), {'chapala', 'ajijic'})
        self.assertEqual(self.buscar('mazamitla', servicio='estacionamiento')[0], ['mazamitla'])
        self.assertEqual(self.buscar('mazamitla', municipio='chapala')[0], [])
        self.assertEqual(self.buscar('', region='ribera')[0], ['ajijic', 'chapala'])
        respuesta = self.client.get('/api/v1/destinos/', {'q': 'mazamitla', 'orden': 'recientes'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 3)

    def test_explorar_ordena_y_sugiere(self):
        respuesta = self.client.get('/destinos/', {'q': 'mazamtla', 'categoria': 'pueblos'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual([lugar['slug'] for lugar in respuesta.context['lugares']], ['mazamitla'])
        self.assertContains(respuesta, '¿Quisiste decir <a href="?q=Mazamitla&amp;categoria=pueblos">Mazamitla</a>?',
                            html=False)
        respuesta = self.client.get('/destinos/', {'q': 'chapala lago'})
        self.assertEqual(respuesta.context['lugares'][0]['slug'], 'chapala')
        self.assertNotContains(respuesta, 'Quisiste decir')

    def test_explorar_sin_texto_conserva_orden_curado(self):
        respuesta = self.client.get('/destinos/')
        self.assertEqual(respuesta.context['pagina'].paginator.count, 12)


class SugerenciasTests(TestCase):
    """Autocompletado: GET /api/v1/sugerencias/?q=…"""

    @classmethod
    def setUpTestData(cls):
        BusquedaTests.setUpTestData.__func__(cls)
        municipio = Municipio.objects.get(slug='mazamitla')
        for nombre, tipo, subtipo in [('Birriería Don Chuy', 'comer', 'restaurant'),
                                      ('Hotel Mazamitla Centro', 'dormir', 'hotel'),
                                      ('Farmacia del Bosque', 'farmacia', 'pharmacy')]:
            Lugar.objects.create(nombre=nombre, tipo=tipo, subtipo=subtipo, municipio=municipio,
                                 latitud=19.9, longitud=-103.0)
        Lugar.objects.create(nombre='Hotel cerrado', tipo='dormir', subtipo='hotel', latitud=19.9,
                             longitud=-103.0, es_activo=False)

    def sugerencias(self, q):
        respuesta = self.client.get('/api/v1/sugerencias/', {'q': q})
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.json()

    def test_propone_destinos_municipios_y_lugares(self):
        datos = self.sugerencias('mazamitla')
        por_tipo = {}
        for resultado in datos['resultados']:
            por_tipo.setdefault(resultado['tipo'], []).append(resultado)
        self.assertEqual(por_tipo['municipio'][0]['url'], '/destinos/?municipio=mazamitla')
        self.assertEqual(por_tipo['destino'][0]['url'], '/destinos/mazamitla/')
        self.assertEqual([lugar['nombre'] for lugar in por_tipo['lugar']], ['Hotel Mazamitla Centro'])
        self.assertTrue(por_tipo['lugar'][0]['url'].startswith('/lugares/'))
        self.assertEqual(datos['sugerencia'], '')

    def test_errores_y_sinonimos(self):
        nombres = [resultado['nombre'] for resultado in self.sugerencias('tlakepake')['resultados']]
        self.assertIn('Tlaquepaque', nombres)
        tipos = {resultado['tipo']: resultado for resultado in self.sugerencias('pueblos magicos')['resultados']}
        self.assertEqual(tipos['coleccion']['nombre'], 'Pueblos Mágicos')
        self.assertEqual(self.sugerencias('playa')['resultados'][0]['url'], '/destinos/?categoria=costa')

    def test_lugares_sin_acentos_y_solo_activos(self):
        nombres = [r['nombre'] for r in self.sugerencias('birrieria')['resultados'] if r['tipo'] == 'lugar']
        self.assertEqual(nombres, ['Birriería Don Chuy'])
        nombres = [r['nombre'] for r in self.sugerencias('hotel')['resultados'] if r['tipo'] == 'lugar']
        self.assertEqual(nombres, ['Hotel Mazamitla Centro'])

    def test_texto_corto_o_vacio(self):
        for q in ['', 'a', '  ', '¿?']:
            with self.subTest(q=q):
                self.assertEqual(self.sugerencias(q), {'resultados': [], 'sugerencia': ''})

    def test_texto_largo_se_recorta(self):
        self.assertEqual(self.client.get('/api/v1/sugerencias/', {'q': 'x' * 5000}).status_code, 200)

    def test_tiene_limite_de_peticiones(self):
        from .views import SugerenciasThrottle
        self.assertEqual(SugerenciasThrottle.rate, '120/min')


@skipUnless(connection.vendor == 'postgresql', 'Solo en PostgreSQL')
class PostgresBusquedaTests(TestCase):
    def test_extensiones_e_indice_de_trigramas(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT extname FROM pg_extension WHERE extname IN ('unaccent', 'pg_trgm')")
            self.assertEqual({fila[0] for fila in cursor.fetchall()}, {'unaccent', 'pg_trgm'})
            cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'lugar_nombre_trgm_idx'")
            self.assertIn('gin_trgm_ops', cursor.fetchone()[0])

    def test_la_busqueda_de_lugares_puede_usar_el_indice(self):
        from .busqueda import lugares_por_nombre
        with CaptureQueriesContext(connection) as consultas:
            lugares_por_nombre('birrieria')
        sql = consultas[-1]['sql']
        # UPPER(nombre) LIKE impediría usar el índice GIN: deben ser ~* y %> sobre la columna.
        self.assertIn('~*', sql)
        self.assertIn('%>', sql)
        self.assertNotIn('UPPER("destinos_lugar"."nombre")', sql)
