"""SEO: metadatos, canonical, datos estructurados, sitemap y robots."""
import json
import re

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.comunidad.models import Aporte
from apps.usuarios.models import Usuario
from .models import Destino, Municipio, Region


@override_settings(PUBLIC_BASE_URL='https://infotrip.example')
class SeoTests(TestCase):
    def setUp(self):
        municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa',
                                             region=Region.objects.create(nombre='Sierra', slug='sierra'))
        self.destino = Destino.objects.create(
            nombre='Mirador', slug='mirador', municipio=municipio, latitud='19.9', longitud='-103.7',
            descripcion='Un mirador </script><script>alert(1)</script> ' + 'con vista ' * 30)
        Destino.objects.create(nombre='Oculto', slug='oculto', municipio=municipio, descripcion='-',
                               latitud=19, longitud=-103, es_activo=False)

    def estructurados(self, html):
        return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))

    def test_ficha_con_titulo_descripcion_canonical_y_open_graph(self):
        html = self.client.get('/destinos/mirador/', {'preguntas': 2}).content.decode()
        self.assertIn('<title>Mirador, Tapalpa, Jalisco: qué saber antes de ir — InfoTrip</title>', html)
        self.assertIn('<link rel="canonical" href="https://infotrip.example/destinos/mirador/">', html)
        self.assertIn('<meta property="og:title" content="Mirador, Tapalpa, Jalisco', html)
        descripcion = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
        self.assertLessEqual(len(descripcion), 200)
        self.assertNotIn('<script', descripcion)

    def test_datos_estructurados_seguros_y_con_calificacion_solo_si_existe(self):
        html = self.client.get('/destinos/mirador/').content.decode()
        self.assertNotIn('</script><script>alert', html)
        datos = self.estructurados(html)
        self.assertEqual(datos['@type'], 'TouristAttraction')
        self.assertEqual(datos['geo']['latitude'], '19.900000')
        self.assertNotIn('aggregateRating', datos)
        autor = Usuario.objects.create_user('a@example.com', 'Ana', 'P', 'Prueba-segura-493!')
        Aporte.objects.create(autor=autor, destino=self.destino, tipo='resena', texto='Bien', calificacion=4,
                              fecha_visita=timezone.localdate(), estado='publicado')
        datos = self.estructurados(self.client.get('/destinos/mirador/').content.decode())
        self.assertEqual((datos['aggregateRating']['ratingValue'], datos['aggregateRating']['reviewCount']), (4.0, 1))

    def test_listado_filtrado_canoniza_sin_parametros(self):
        self.assertContains(self.client.get('/destinos/', {'q': 'mirador'}),
                            '<link rel="canonical" href="https://infotrip.example/destinos/">')

    def test_paginas_privadas_no_se_indexan(self):
        for ruta in ['/perfil/', '/favoritos/', '/mis-viajes/', '/recuperar/', '/login/', '/registro/']:
            with self.subTest(ruta=ruta):
                self.assertContains(self.client.get(ruta), '<meta name="robots" content="noindex">')
        self.assertNotContains(self.client.get('/destinos/mirador/'), 'noindex')

    def test_sitemap_solo_con_destinos_activos(self):
        respuesta = self.client.get('/sitemap.xml')
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, '/destinos/mirador/</loc>')
        self.assertContains(respuesta, '/destinos/</loc>')
        self.assertNotContains(respuesta, 'oculto')

    def test_robots(self):
        respuesta = self.client.get('/robots.txt')
        self.assertEqual(respuesta['Content-Type'], 'text/plain')
        self.assertContains(respuesta, 'Disallow: /admin/')
        self.assertContains(respuesta, 'Disallow: /api/')
        self.assertContains(respuesta, 'Sitemap: https://infotrip.example/sitemap.xml')
