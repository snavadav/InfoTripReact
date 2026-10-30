"""Lugares útiles: importación, búsqueda por zona, "Cerca de mí" y ficha. Nunca consulta la red."""
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APITestCase

from .lugares import cerca_de
from .models import Destino, Lugar, Municipio, Region
from .osm import interpretar_lugares
from .test_osm import TAPALPA, TLAQUEPAQUE, lugar, respuesta


class InterpretarTests(TestCase):
    def test_clasifica_y_limpia_los_datos(self):
        lugares, omitidos = interpretar_lugares(respuesta(
            lugar(1, 'Fonda', 19.9, -103.5, amenity='restaurant', phone='+52 33 1234', website='https://fonda.mx',
                  opening_hours='Mo-Su 09:00-18:00'),
            lugar(2, 'Motel', 19.9, -103.5, tourism='motel', website='javascript:alert(1)'),
            lugar(3, 'Pemex', 20.9, -103.5, amenity='fuel', **{'contact:phone': '555', 'addr:street': 'Juárez', 'addr:housenumber': '5'}),
        ))
        por_nombre = {sitio['nombre']: sitio for sitio in lugares}
        fonda = por_nombre['Fonda']
        self.assertEqual((fonda['tipo'], fonda['subtipo'], fonda['telefono'], fonda['sitio_web'], fonda['horario']),
                         ('comer', 'restaurant', '+52 33 1234', 'https://fonda.mx', 'Mo-Su 09:00-18:00'))
        self.assertEqual(fonda['municipio'], 'Tapalpa')
        self.assertEqual((por_nombre['Motel']['tipo'], por_nombre['Motel']['sitio_web']), ('dormir', ''))
        pemex = por_nombre['Pemex']
        self.assertEqual((pemex['tipo'], pemex['municipio'], pemex['telefono'], pemex['direccion']),
                         ('gasolina', 'San Pedro Tlaquepaque', '555', 'Juárez 5'))
        self.assertEqual(omitidos, 0)

    def test_omite_lo_que_no_aplica(self):
        lugares, omitidos = interpretar_lugares(respuesta(
            lugar(1, 'Fuera', 40, -103.5, amenity='pharmacy'),
            lugar(2, 'Tipo ajeno', 19.9, -103.5, amenity='school'),
            {'type': 'node', 'id': 3, 'lat': 19.9, 'lon': -103.5, 'tags': {'amenity': 'bank'}},
        ))
        self.assertEqual((lugares, omitidos), ([], 3))

    def test_un_punto_fuera_del_recuadro_no_recorre_el_contorno(self):
        with patch('apps.destinos.osm._dentro', wraps=lambda *a: False) as dentro:
            interpretar_lugares({'elements': [lugar(1, 'Lejos', 40, -103.5, amenity='bank'), TAPALPA, TLAQUEPAQUE]})
        dentro.assert_not_called()


class ComandoTests(TestCase):
    def importar(self, datos, **opciones):
        salida = StringIO()
        with patch('apps.destinos.management.commands.importar_lugares.descargar', return_value=datos):
            call_command('importar_lugares', stdout=salida, **opciones)
        return salida.getvalue()

    def test_crea_publicado_con_municipio_y_origen(self):
        self.importar(respuesta(lugar(1, 'Fonda', 19.9, -103.5, amenity='restaurant')))
        registro = Lugar.objects.get()
        self.assertTrue(registro.es_activo)
        self.assertEqual((registro.osm_id, registro.municipio.nombre), ('node/1', 'Tapalpa'))

    def test_repetir_actualiza_sin_duplicar(self):
        self.importar(respuesta(lugar(1, 'Fonda', 19.9, -103.5, amenity='restaurant')))
        salida = self.importar(respuesta(lugar(1, 'Fonda Nueva', 19.9, -103.5, amenity='restaurant', phone='123')))
        registro = Lugar.objects.get()
        self.assertEqual((registro.nombre, registro.telefono), ('Fonda Nueva', '123'))
        self.assertIn('Actualizados: 1', salida)

    def test_lo_editado_en_el_admin_no_se_toca_ni_lo_oculto_se_publica(self):
        self.importar(respuesta(lugar(1, 'Fonda', 19.9, -103.5, amenity='restaurant'),
                                lugar(2, 'Bar', 19.9, -103.5, amenity='bar')))
        Lugar.objects.filter(osm_id='node/1').update(nombre='Fonda corregida', protegido=True)
        Lugar.objects.filter(osm_id='node/2').update(es_activo=False)
        self.importar(respuesta(lugar(1, 'Fonda', 19.9, -103.5, amenity='restaurant'),
                                lugar(2, 'Bar', 19.9, -103.5, amenity='bar')))
        self.assertEqual(Lugar.objects.get(osm_id='node/1').nombre, 'Fonda corregida')
        self.assertFalse(Lugar.objects.get(osm_id='node/2').es_activo)

    def test_retirar_ausentes_solo_si_se_pide(self):
        self.importar(respuesta(lugar(1, 'Fonda', 19.9, -103.5, amenity='restaurant'),
                                lugar(2, 'Bar', 19.9, -103.5, amenity='bar')))
        solo_uno = respuesta(lugar(1, 'Fonda', 19.9, -103.5, amenity='restaurant'))
        self.importar(solo_uno)
        self.assertTrue(Lugar.objects.get(osm_id='node/2').es_activo)
        self.assertIn('Retirados: 1', self.importar(solo_uno, retirar_ausentes=True))
        self.assertFalse(Lugar.objects.get(osm_id='node/2').es_activo)

    def test_respuesta_vacia_no_cambia_nada(self):
        self.importar(respuesta(lugar(1, 'Fonda', 19.9, -103.5, amenity='restaurant')))
        with self.assertRaises(CommandError):
            self.importar(respuesta(), retirar_ausentes=True)
        self.assertTrue(Lugar.objects.get().es_activo)

    def test_simular_no_guarda_nada(self):
        self.assertIn('Se crearían 1', self.importar(respuesta(lugar(1, 'Fonda', 19.9, -103.5, amenity='restaurant')), simular=True))
        self.assertFalse(Lugar.objects.exists())
        self.assertFalse(Municipio.objects.exists())

    def test_no_interfiere_con_la_exploracion_de_destinos(self):
        self.importar(respuesta(lugar(1, 'Fonda', 19.9, -103.5, amenity='restaurant')))
        opciones = [slug for slug, _ in self.client.get('/destinos/').context['formulario'].fields['municipio'].choices]
        self.assertNotIn('tapalpa', opciones)


class BaseLugares(APITestCase):
    def setUp(self):
        cache.clear()
        self.tapalpa = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa',
                                                region=Region.objects.create(nombre='Sierra', slug='sierra'))

    def crear(self, nombre, latitud=19.95, longitud=-103.75, tipo='comer', subtipo='restaurant', **campos):
        return Lugar.objects.create(nombre=nombre, latitud=latitud, longitud=longitud, tipo=tipo, subtipo=subtipo,
                                    municipio=self.tapalpa, **campos)


class ZonaTests(BaseLugares):
    URL = '/api/v1/lugares/'
    ZONA = {'sur': 19.9, 'oeste': -103.8, 'norte': 20.0, 'este': -103.7}

    def test_solo_lo_visible_activo_y_del_tipo(self):
        self.crear('Dentro', osm_id='node/1')
        self.crear('Fuera', latitud=21)
        self.crear('Oculto', es_activo=False)
        self.crear('Hotel', tipo='dormir', subtipo='hotel')
        datos = self.client.get(self.URL, {**self.ZONA, 'tipo': 'comer'}).data
        self.assertEqual([sitio['nombre'] for sitio in datos['resultados']], ['Dentro'])
        self.assertFalse(datos['truncado'])
        sitio = datos['resultados'][0]
        self.assertEqual((sitio['subtipo_nombre'], sitio['municipio'], sitio['osm_url']),
                         ('Restaurante', 'Tapalpa', 'https://www.openstreetmap.org/node/1'))
        self.assertIn('OpenStreetMap', sitio['atribucion'])
        self.assertEqual(len(self.client.get(self.URL, self.ZONA).data['resultados']), 2)

    def test_zona_invalida_o_enorme(self):
        for cambio in [{'norte': 19}, {'este': -104}, {'sur': 10}, {'tipo': 'inventado'}, {'sur': 'x'}]:
            self.assertEqual(self.client.get(self.URL, {**self.ZONA, **cambio}).status_code, 400, cambio)

    def test_avisa_si_quedaron_fuera(self):
        with patch('apps.destinos.lugares.MAXIMO_EN_ZONA', 1):
            self.crear('Uno')
            self.crear('Dos')
            datos = self.client.get(self.URL, self.ZONA).data
        self.assertEqual(len(datos['resultados']), 1)
        self.assertTrue(datos['truncado'])

    def test_consultas_acotadas(self):
        for numero in range(5):
            self.crear(f'Lugar {numero}')
        with self.assertNumQueries(1):
            self.client.get(self.URL, self.ZONA)


class CercaTests(BaseLugares):
    URL = '/api/v1/lugares/cerca/'
    AQUI = {'latitud': 19.95, 'longitud': -103.75}

    def test_ordena_por_distancia_y_respeta_el_radio(self):
        self.crear('Lejos', latitud=19.98)
        self.crear('Aqui')
        self.crear('Muy lejos', latitud=20.5)
        self.crear('Oculto', es_activo=False)
        datos = self.client.post(self.URL, self.AQUI, format='json').data
        self.assertEqual([sitio['nombre'] for sitio in datos['resultados']], ['Aqui', 'Lejos'])
        self.assertEqual(datos['resultados'][0]['distancia_km'], 0)
        self.assertAlmostEqual(datos['resultados'][1]['distancia_km'], 3.34, delta=.05)
        ampliado = self.client.post(self.URL, {**self.AQUI, 'radio_km': 25}, format='json').data
        self.assertEqual(len(ampliado['resultados']), 2)

    def test_filtra_por_tipo(self):
        self.crear('Fonda')
        self.crear('Hotel', tipo='dormir', subtipo='hotel')
        datos = self.client.post(self.URL, {**self.AQUI, 'tipo': 'dormir'}, format='json').data
        self.assertEqual([sitio['nombre'] for sitio in datos['resultados']], ['Hotel'])

    def test_no_acepta_get_ni_valores_invalidos(self):
        self.assertEqual(self.client.get(self.URL, self.AQUI).status_code, 405)
        for datos in [{}, {'latitud': 91, 'longitud': 0}, {**self.AQUI, 'radio_km': 26}, {**self.AQUI, 'radio_km': 0}]:
            self.assertEqual(self.client.post(self.URL, datos, format='json').status_code, 400, datos)

    def test_no_guarda_la_ubicacion(self):
        campos = {campo.name for campo in Lugar._meta.get_fields()}
        self.crear('Fonda')
        antes = list(Lugar.objects.values())
        self.client.post(self.URL, {'latitud': 19.951234, 'longitud': -103.751234}, format='json')
        self.assertEqual(list(Lugar.objects.values()), antes)
        self.assertFalse(campos & {'usuario', 'autor'})

    def test_limite(self):
        for numero in range(4):
            self.crear(f'L{numero}', latitud=19.95 + numero / 1000)
        self.assertEqual([sitio.nombre for sitio in cerca_de(19.95, -103.75, limite=2)], ['L0', 'L1'])


class FichaTests(BaseLugares):
    def setUp(self):
        super().setUp()
        self.destino = Destino.objects.create(nombre='Centro', slug='centro', municipio=self.tapalpa, descripcion='-',
                                              latitud='19.95', longitud='-103.75')

    def test_muestra_lo_cercano_por_grupo_con_credito(self):
        self.crear('Fonda Doña Ana', telefono='3312345678', sitio_web='https://fonda.mx', osm_id='node/1')
        self.crear('Hotel Sierra', tipo='dormir', subtipo='hotel')
        self.crear('Muy lejos', latitud=21)
        ficha = self.client.get('/destinos/centro/')
        self.assertContains(ficha, 'Dónde comer')
        self.assertContains(ficha, 'Fonda Doña Ana')
        self.assertContains(ficha, 'Dónde dormir')
        self.assertContains(ficha, 'tel:3312345678')
        self.assertContains(ficha, 'https://fonda.mx')
        self.assertContains(ficha, 'colaboradores de OpenStreetMap')
        self.assertNotContains(ficha, 'Muy lejos')
        self.assertNotContains(ficha, 'Farmacias')
        self.assertContains(ficha, '0 m')
        self.assertNotContains(ficha, '0.0 km')

    def test_distancia_legible(self):
        sitio = self.crear('Fonda')
        for km, texto in [(0.34, '340 m'), (0.999, '1000 m'), (2.34, '2.3 km')]:
            sitio.distancia_km = km
            self.assertEqual(sitio.distancia_legible, texto)

    def test_sin_lugares_no_aparece_la_seccion(self):
        self.assertNotContains(self.client.get('/destinos/centro/'), 'id="cerca-de-aqui"')


class AdminTests(BaseLugares):
    def test_editar_protege_el_lugar_de_la_siguiente_importacion(self):
        sitio = self.crear('Fonda', osm_id='node/1')
        self.client.force_login(get_user_model().objects.create_superuser('m@example.com', 'Mod', 'P', 'Prueba-segura-493!'))
        self.assertContains(self.client.get('/admin/destinos/lugar/'), 'Fonda')
        respuesta_admin = self.client.post(f'/admin/destinos/lugar/{sitio.pk}/change/', {
            'nombre': 'Fonda corregida', 'tipo': 'comer', 'subtipo': 'restaurant', 'latitud': '19.95', 'longitud': '-103.75',
            'municipio': self.tapalpa.pk, 'es_activo': 'on',
        })
        self.assertEqual(respuesta_admin.status_code, 302)
        sitio.refresh_from_db()
        self.assertTrue(sitio.protegido)
        self.assertEqual(sitio.nombre, 'Fonda corregida')
