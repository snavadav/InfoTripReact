"""Caché del catálogo (R13): menos consultas por visita y por tecla, y nada atrasado al editar."""
from datetime import date
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.comunidad.models import Aporte
from apps.usuarios.models import Usuario
from . import cache_catalogo
from .models import Categoria, Destino, Municipio, Region


class CacheCatalogoTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nombre='Sierra', slug='sierra')
        self.tapalpa = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=region)
        self.bosque = Categoria.objects.create(nombre='Naturaleza', slug='naturaleza')
        for nombre in ['Piedrotas', 'Presa del Nogal', 'Salto del Nogal']:
            self.crear(nombre)

    def crear(self, nombre, **campos):
        destino = Destino.objects.create(nombre=nombre, slug=nombre.lower().replace(' ', '-'), municipio=self.tapalpa,
                                         descripcion='Bosque y senderos.', latitud='19.95', longitud='-103.75',
                                         **campos)
        destino.categorias.add(self.bosque)
        return destino

    def consultas(self, url, parametros=None):
        with CaptureQueriesContext(connection) as contexto:
            respuesta = self.client.get(url, parametros or {})
        self.assertEqual(respuesta.status_code, 200)
        return len(contexto), respuesta

    def test_sugerencias_repetidas_consultan_menos(self):
        primera, respuesta = self.consultas('/api/v1/sugerencias/', {'q': 'nogal'})
        segunda, _ = self.consultas('/api/v1/sugerencias/', {'q': 'noga'})
        self.assertEqual({r['nombre'] for r in respuesta.json()['resultados'] if r['tipo'] == 'destino'},
                         {'Presa del Nogal', 'Salto del Nogal'})
        # Documentos, categorías y municipios quedan guardados; siguen los centros, los destinos y los lugares.
        self.assertLess(segunda, primera)
        self.assertLessEqual(segunda, 3)

    def test_un_destino_nuevo_aparece_en_la_siguiente_sugerencia(self):
        self.client.get('/api/v1/sugerencias/', {'q': 'nogal'})
        self.crear('Mirador del Nogal')
        nombres = {r['nombre'] for r in self.client.get('/api/v1/sugerencias/', {'q': 'nogal'}).json()['resultados']}
        self.assertIn('Mirador del Nogal', nombres)
        Destino.objects.filter(slug='mirador-del-nogal').update(es_activo=False)  # Sin señal: no invalida…
        cache_catalogo.invalidar()  # …hasta que algo cambie la versión (o caduque, DURACION).
        nombres = {r['nombre'] for r in self.client.get('/api/v1/sugerencias/', {'q': 'nogal'}).json()['resultados']}
        self.assertNotIn('Mirador del Nogal', nombres)

    def test_filtros_de_explorar_guardados_y_al_dia(self):
        self.client.get('/destinos/')
        _, respuesta = self.consultas('/destinos/')
        self.assertContains(respuesta, 'value="tapalpa"')
        otra = Municipio.objects.create(nombre='Mazamitla', slug='mazamitla', region=self.tapalpa.region)
        Destino.objects.create(nombre='Cascada', slug='cascada', municipio=otra, descripcion='-',
                               latitud='19.9', longitud='-103.0')
        self.assertContains(self.client.get('/destinos/'), 'value="mazamitla"')

    def test_sitemap_guardado_hasta_que_cambia_un_destino(self):
        primera = self.client.get('/sitemap.xml')
        self.assertContains(primera, '/destinos/piedrotas/')
        with self.assertNumQueries(0):
            segunda = self.client.get('/sitemap.xml')
        self.assertEqual(segunda.content, primera.content)
        self.assertEqual(segunda['Content-Type'], primera['Content-Type'])
        self.crear('Cascada')
        self.assertContains(self.client.get('/sitemap.xml'), '/destinos/cascada/')

    def test_misiones_guardadas_por_municipio_sin_guardar_lo_inventado(self):
        self.client.get('/misiones/')
        repetida, respuesta = self.consultas('/misiones/')
        self.assertContains(respuesta, 'Piedrotas')
        self.assertLessEqual(repetida, 2)  # Sesión y nada más del catálogo.
        with patch.object(cache_catalogo, 'guardado', wraps=cache_catalogo.guardado) as guardado:
            self.client.get('/misiones/', {'municipio': 'no-existe'})
        self.assertNotIn('misiones:no-existe', [llamada.args[0] for llamada in guardado.call_args_list])

    def test_un_gasto_publicado_cambia_la_tabla_de_costos(self):
        self.client.get('/costos/')
        autor = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', 'Prueba-segura-493!', es_verificado=True)
        destino = Destino.objects.get(slug='piedrotas')
        version = cache_catalogo.version()
        Aporte.objects.create(destino=destino, autor=autor, tipo='gasto', concepto='entrada', monto=50,
                              fecha_visita=date.today(), estado='publicado')
        self.assertNotEqual(cache_catalogo.version(), version)
