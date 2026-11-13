"""Museos y parques como lugares del mapa: de OpenStreetMap, con su propio botón. Nunca consulta la red."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.curador.muestreo import TIPOS as TIPOS_DEL_CURADOR
from .models import Destino, Lugar, Municipio, Region
from .osm import CONSULTA_LUGARES, CONSULTA_MUSEOS_PARQUES, interpretar_lugares
from .test_osm import TAPALPA, TLAQUEPAQUE, lugar, respuesta

ZONA = {'sur': 19.8, 'oeste': -103.8, 'norte': 20, 'este': -103.4}


class InterpretarTests(TestCase):
    def test_clasifica_museos_parques_y_areas_naturales(self):
        lugares, omitidos = interpretar_lugares(respuesta(
            lugar(1, 'Museo del Pueblo', 19.9, -103.5, tourism='museum'),
            lugar(2, 'Parque Los Colomos', 19.9, -103.5, leisure='park'),
            lugar(3, 'Bosque La Primavera', 19.9, -103.5, leisure='nature_reserve'),
            lugar(4, 'Parque', 19.9, -103.5, leisure='park'),
            lugar(5, 'Área verde', 19.9, -103.5, leisure='park'),
            lugar(6, 'Gimnasio Fuerte', 19.9, -103.5, leisure='fitness_centre'),
        ))
        self.assertEqual({sitio['nombre']: (sitio['tipo'], sitio['subtipo']) for sitio in lugares}, {
            'Museo del Pueblo': ('museo', 'museum'), 'Parque Los Colomos': ('parque', 'park'),
            'Bosque La Primavera': ('parque', 'nature_reserve'),
        })
        # Un parque sin nombre propio no ayuda a encontrarlo; lo que no es parque ni museo no entra.
        self.assertEqual(omitidos, 3)

    def test_las_consultas_los_piden(self):
        for consulta in (CONSULTA_LUGARES, CONSULTA_MUSEOS_PARQUES):
            self.assertIn('museum', consulta)
            self.assertIn('"leisure"~"^(park|nature_reserve)$"', consulta)


class ImportarTests(TestCase):
    DATOS = {'elements': [lugar(1, 'Museo del Pueblo', 19.9, -103.5, tourism='museum'),
                          lugar(2, 'Parque Central', 19.9, -103.5, leisure='park'),
                          lugar(3, 'Farmacia', 19.9, -103.5, amenity='pharmacy'), TAPALPA, TLAQUEPAQUE]}

    def importar(self, **opciones):
        with patch('apps.destinos.management.commands.importar_lugares.descargar',
                   return_value=self.DATOS) as descargar:
            call_command('importar_lugares', stdout=StringIO(), **opciones)
        return descargar

    def test_solo_museos_y_parques_no_toca_lo_demas(self):
        fonda = Lugar.objects.create(nombre='Fonda', tipo='comer', subtipo='restaurant', latitud=19.9,
                                     longitud=-103.5, osm_id='node/50')
        viejo = Lugar.objects.create(nombre='Parque Viejo', tipo='parque', subtipo='park', latitud=19.9,
                                     longitud=-103.5, osm_id='node/60')
        descargar = self.importar(solo_museos_parques=True, retirar_ausentes=True)
        self.assertEqual(descargar.call_args.args[0], CONSULTA_MUSEOS_PARQUES)
        self.assertEqual(set(Lugar.objects.filter(es_activo=True).values_list('nombre', 'tipo')),
                         {('Fonda', 'comer'), ('Museo del Pueblo', 'museo'), ('Parque Central', 'parque')})
        fonda.refresh_from_db()
        viejo.refresh_from_db()
        self.assertTrue(fonda.es_activo)
        self.assertFalse(viejo.es_activo)

    def test_la_importacion_normal_tambien_los_trae(self):
        self.importar()
        self.assertEqual(Lugar.objects.filter(tipo__in=['museo', 'parque']).count(), 2)

    def test_una_sola_importacion_parcial_a_la_vez(self):
        with self.assertRaises(CommandError):
            self.importar(solo_museos_parques=True, solo_mercados=True)


class MapaTests(TestCase):
    def test_el_mapa_ofrece_museos_y_parques(self):
        pagina = self.client.get('/destinos/')
        self.assertContains(pagina, 'data-lugar-tipo="museo"')
        self.assertContains(pagina, 'data-lugar-tipo="parque"')

    def test_la_zona_filtra_por_los_tipos_nuevos(self):
        Lugar.objects.create(nombre='Museo', tipo='museo', subtipo='museum', latitud=19.9, longitud=-103.5)
        Lugar.objects.create(nombre='Parque', tipo='parque', subtipo='nature_reserve', latitud=19.9, longitud=-103.5)
        museos = self.client.get('/api/v1/lugares/', {**ZONA, 'tipo': 'museo'}).json()['resultados']
        parques = self.client.get('/api/v1/lugares/', {**ZONA, 'tipo': 'parque'}).json()['resultados']
        self.assertEqual([(sitio['nombre'], sitio['tipo']) for sitio in museos], [('Museo', 'museo')])
        self.assertEqual([(sitio['nombre'], sitio['tipo']) for sitio in parques], [('Parque', 'parque')])
        ficha = self.client.get(f"/api/v1/lugares/{parques[0]['id']}/").json()
        self.assertEqual((ficha['tipo_nombre'], ficha['subtipo_nombre']), ('Parque', 'Área natural'))

    def test_un_museo_que_ya_es_destino_enlaza_la_ficha_del_destino(self):
        region = Region.objects.create(nombre='Sierra', slug='sierra')
        municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=region)
        Destino.objects.create(nombre='Museo Regional', slug='museo-regional', descripcion='-', municipio=municipio,
                               latitud=19.9, longitud=-103.5, osm_id='node/7')
        Destino.objects.create(nombre='Museo Oculto', slug='museo-oculto', descripcion='-', municipio=municipio,
                               latitud=19.9, longitud=-103.5, osm_id='node/8', es_activo=False)
        con_ficha = Lugar.objects.create(nombre='Museo Regional', tipo='museo', subtipo='museum', latitud=19.9,
                                         longitud=-103.5, osm_id='node/7')
        oculto = Lugar.objects.create(nombre='Museo Oculto', tipo='museo', subtipo='museum', latitud=19.9,
                                      longitud=-103.5, osm_id='node/8')
        propuesto = Lugar.objects.create(nombre='Museo Nuevo', tipo='museo', subtipo='museum', latitud=19.9,
                                         longitud=-103.5)
        # La zona trae solo lo del marcador; la dirección de la ficha llega al abrir el lugar.
        urls = {sitio.pk: self.client.get(f'/api/v1/lugares/{sitio.pk}/').json()['url']
                for sitio in (con_ficha, oculto, propuesto)}
        self.assertEqual(urls, {con_ficha.pk: '/destinos/museo-regional/', oculto.pk: f'/lugares/{oculto.pk}/',
                                propuesto.pk: f'/lugares/{propuesto.pk}/'})

    def test_se_pueden_proponer_y_tienen_ficha(self):
        self.assertContains(self.client.get('/lugares/proponer/'), 'value="museum"')
        parque = Lugar.objects.create(nombre='Parque Central', tipo='parque', subtipo='park', latitud=19.9,
                                      longitud=-103.5)
        self.assertContains(self.client.get(f'/lugares/{parque.pk}/'), 'Parque Central')

    def test_el_curador_no_pide_etiquetarlos(self):
        self.assertEqual({clave for clave, _ in TIPOS_DEL_CURADOR},
                         {clave for clave, _ in Lugar.TIPOS} - {'museo', 'parque'})
