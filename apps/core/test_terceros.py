"""R15: Leaflet y las fuentes se sirven desde el sitio; la CSP ya no admite unpkg ni Google Fonts."""
import re

from django.contrib.staticfiles import finders
from django.test import TestCase

from apps.destinos.models import Destino, Municipio, Region

DOMINIOS_RETIRADOS = ('unpkg.com', 'fonts.googleapis.com', 'fonts.gstatic.com')


class SinTercerosTests(TestCase):
    def setUp(self):
        municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa',
                                             region=Region.objects.create(nombre='Sierra', slug='sierra'))
        Destino.objects.create(nombre='Piedrotas', slug='piedrotas', municipio=municipio, descripcion='-',
                               latitud='19.95', longitud='-103.75')

    def test_la_csp_no_admite_los_dominios_retirados(self):
        for url in ['/', '/sw.js']:
            with self.subTest(url=url):
                csp = self.client.get(url)['Content-Security-Policy']
                for dominio in DOMINIOS_RETIRADOS:
                    self.assertNotIn(dominio, csp)

    def test_paginas_con_mapa_y_fuentes_cargan_todo_del_sitio(self):
        for url in ['/', '/destinos/', '/destinos/piedrotas/', '/planeador/', '/login/', '/registro/']:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                for dominio in DOMINIOS_RETIRADOS:
                    self.assertNotIn(dominio, html)
                for recurso in re.findall(r'(?:src|href)="/static/((?:vendor|fonts|css/fuentes)[^"]+)"', html):
                    self.assertTrue(finders.find(recurso), recurso)

    def test_archivos_propios_con_su_licencia(self):
        for ruta in ['vendor/leaflet-1.9.4/leaflet.js', 'vendor/leaflet-1.9.4/leaflet.css',
                     'vendor/leaflet-1.9.4/images/layers.png', 'vendor/leaflet-1.9.4/LICENSE.txt',
                     'vendor/leaflet.markercluster-1.5.3/leaflet.markercluster.js',
                     'vendor/leaflet.markercluster-1.5.3/MarkerCluster.css',
                     'vendor/leaflet.markercluster-1.5.3/MIT-LICENCE.txt',
                     'fonts/geist/geist-latin.woff2', 'fonts/geist/geist-mono-latin.woff2', 'fonts/geist/OFL.txt']:
            with self.subTest(ruta=ruta):
                self.assertTrue(finders.find(ruta))
