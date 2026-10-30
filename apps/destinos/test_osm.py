"""Importación desde OpenStreetMap. Nunca consulta la red: usa respuestas de ejemplo."""
import json
import os
import tempfile
import urllib.error
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase

from apps.usuarios.models import Usuario
from .admin import DestinoAdmin
from .models import Categoria, Destino, Municipio, Region
from .osm import ErrorOverpass, descargar, interpretar


def municipio(nombre, lat, lon, lado=1.0):
    """Un cuadrado, con sus lados como tramos separados y desordenados, como los entrega Overpass."""
    a, b, c, d = (lat, lon), (lat, lon + lado), (lat + lado, lon + lado), (lat + lado, lon)

    def tramo(p, q):
        return {'type': 'way', 'role': 'outer', 'geometry': [{'lat': p[0], 'lon': p[1]}, {'lat': q[0], 'lon': q[1]}]}

    return {'type': 'relation', 'id': abs(hash(nombre)) % 1000, 'tags': {'boundary': 'administrative', 'name': nombre},
            'members': [tramo(c, d), tramo(a, b), tramo(d, a), tramo(b, c)]}


def lugar(identificador, nombre, lat, lon, **etiquetas):
    return {'type': 'node', 'id': identificador, 'lat': lat, 'lon': lon, 'tags': {'name': nombre, **etiquetas}}


TAPALPA = municipio('Tapalpa', 19.5, -104.0)
TLAQUEPAQUE = municipio('San Pedro Tlaquepaque', 20.5, -104.0)


def respuesta(*lugares):
    return {'elements': [*lugares, TAPALPA, TLAQUEPAQUE]}


class InterpretarTests(TestCase):
    def test_asigna_el_municipio_segun_su_ubicacion(self):
        lugares, omitidos = interpretar(respuesta(
            lugar(1, 'Museo A', 19.9, -103.5, tourism='museum'),
            lugar(2, 'Museo B', 20.9, -103.5, tourism='museum'),
        ))
        self.assertEqual([(sitio['nombre'], sitio['municipio']) for sitio in lugares],
                         [('Museo A', 'Tapalpa'), ('Museo B', 'San Pedro Tlaquepaque')])
        self.assertEqual(omitidos, 0)

    def test_usa_el_centro_de_lineas_y_areas(self):
        via = {'type': 'way', 'id': 7, 'center': {'lat': 19.9, 'lon': -103.5}, 'tags': {'name': 'Playa', 'natural': 'beach'}}
        self.assertEqual(interpretar(respuesta(via))[0][0]['osm_id'], 'way/7')

    def test_omite_lo_que_no_tiene_datos_suficientes(self):
        lugares, omitidos = interpretar(respuesta(
            {'type': 'node', 'id': 1, 'lat': 19.9, 'lon': -103.5, 'tags': {'tourism': 'museum'}},
            lugar(2, 'Fuera de los municipios', 40, -103.5, tourism='museum'),
            lugar(3, 'Tipo ajeno', 19.9, -103.5, tourism='hotel'),
            {'type': 'way', 'id': 4, 'tags': {'name': 'Sin coordenadas', 'tourism': 'museum'}},
        ))
        self.assertEqual((lugares, omitidos), ([], 4))

    def test_cascada_etiquetada_con_waterway(self):
        self.assertEqual(interpretar(respuesta(lugar(1, 'Salto', 19.9, -103.5, waterway='waterfall')))[0][0]['tipo'], 'waterfall')

    def test_respuesta_incompleta_no_se_importa(self):
        with self.assertRaises(ErrorOverpass):
            interpretar({'remark': 'runtime error: Query timed out', 'elements': [TAPALPA]})
        with self.assertRaises(ErrorOverpass):
            interpretar({'elements': [lugar(1, 'Sin municipios', 19.9, -103.5, tourism='museum')]})


class DescargarTests(TestCase):
    def test_identifica_la_aplicacion_y_devuelve_los_datos(self):
        contenido = MagicMock()
        contenido.__enter__.return_value = StringIO(json.dumps({'elements': []}))
        with patch('apps.destinos.osm.urllib.request.urlopen', return_value=contenido) as abrir:
            self.assertEqual(descargar(), {'elements': []})
        pedido = abrir.call_args[0][0]
        self.assertIn('InfoTrip', pedido.get_header('User-agent'))
        self.assertIn(b'MX-JAL', pedido.data)

    def test_errores_del_servidor_se_explican(self):
        errores = [
            urllib.error.HTTPError('u', 429, 'Too Many', {}, None), urllib.error.URLError('sin red'), TimeoutError('tiempo'),
        ]
        for error in errores:
            with self.subTest(error=error), patch('apps.destinos.osm.urllib.request.urlopen', side_effect=error):
                with self.assertRaises(ErrorOverpass):
                    descargar()


class ComandoTests(TestCase):
    def importar(self, datos, **opciones):
        salida = StringIO()
        with patch('apps.destinos.management.commands.importar_osm.descargar', return_value=datos):
            call_command('importar_osm', stdout=salida, **opciones)
        return salida.getvalue()

    def test_crea_destinos_ocultos_con_categoria_y_texto_neutro(self):
        self.importar(respuesta(lugar(1, 'Museo del Pueblo', 19.9, -103.5, tourism='museum')))
        destino = Destino.objects.get()
        self.assertFalse(destino.es_activo)
        self.assertEqual((destino.osm_id, destino.slug), ('node/1', 'museo-del-pueblo'))
        self.assertEqual(destino.categorias.get().nombre, 'Ciudad y cultura')
        self.assertIn('Museo en Tapalpa, Jalisco', destino.descripcion)
        self.assertEqual(destino.municipio.region.nombre, 'Otras zonas de Jalisco')

    def test_usa_la_descripcion_de_osm_y_atraccion_sin_categoria(self):
        self.importar(respuesta(lugar(1, 'Piedra', 19.9, -103.5, tourism='attraction', description='Una gran piedra')))
        destino = Destino.objects.get()
        self.assertEqual(destino.descripcion, 'Una gran piedra')
        self.assertFalse(destino.categorias.exists())

    def test_reutiliza_municipios_y_su_region_incluido_el_alias(self):
        sierra = Region.objects.create(nombre='Sierra', slug='sierra')
        Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=sierra)
        centro = Region.objects.create(nombre='Centro', slug='centro')
        Municipio.objects.create(nombre='Tlaquepaque', slug='tlaquepaque', region=centro)
        self.importar(respuesta(lugar(1, 'A', 19.9, -103.5, tourism='museum'), lugar(2, 'B', 20.9, -103.5, tourism='museum')))
        self.assertEqual(Destino.objects.get(osm_id='node/1').municipio.region, sierra)
        self.assertEqual(Destino.objects.get(osm_id='node/2').municipio.nombre, 'Tlaquepaque')
        self.assertEqual(Municipio.objects.count(), 2)

    def test_repetir_no_duplica_ni_pisa_ediciones_ni_republica(self):
        datos = respuesta(lugar(1, 'Museo', 19.9, -103.5, tourism='museum'))
        self.importar(datos)
        Destino.objects.update(descripcion='Editado por el equipo', nombre='Museo Regional', es_activo=True)
        salida = self.importar(datos)
        destino = Destino.objects.get()
        self.assertEqual((destino.descripcion, destino.nombre), ('Editado por el equipo', 'Museo Regional'))
        self.assertIn('Creados 0', salida)
        self.assertIn('Ya importados: 1', salida)

    def test_no_duplica_un_destino_cercano_con_el_mismo_nombre(self):
        region = Region.objects.create(nombre='Sierra', slug='sierra')
        tapalpa = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=region)
        Destino.objects.create(nombre='Las Piedras', slug='las-piedras', municipio=tapalpa, descripcion='-',
                               latitud='19.9', longitud='-103.5')
        salida = self.importar(respuesta(lugar(1, 'Las Piedras', 19.901, -103.5, tourism='attraction')))
        self.assertIn('Duplicados: 1', salida)
        self.assertEqual(Destino.objects.count(), 1)

    def test_un_nombre_que_empieza_igual_no_es_duplicado(self):
        self.importar(respuesta(lugar(1, 'Mirador del Matemático', 19.9, -103.5, tourism='viewpoint'),
                                lugar(2, 'Mirador', 19.901, -103.5, tourism='viewpoint')))
        self.assertEqual(Destino.objects.count(), 2)

    def test_el_mismo_lugar_como_punto_y_como_area_se_importa_una_vez(self):
        area = {'type': 'way', 'id': 2, 'center': {'lat': 19.901, 'lon': -103.5}, 'tags': {'name': 'Museo', 'tourism': 'museum'}}
        self.importar(respuesta(lugar(1, 'Museo', 19.9, -103.5, tourism='museum'), area))
        self.assertEqual(Destino.objects.count(), 1)

    def test_mismo_nombre_lejos_es_otro_lugar_con_otro_slug(self):
        self.importar(respuesta(lugar(1, 'Mirador', 19.9, -103.5, tourism='viewpoint'),
                                lugar(2, 'Mirador', 20.9, -103.5, tourism='viewpoint')))
        self.assertEqual(set(Destino.objects.values_list('slug', flat=True)),
                         {'mirador', 'mirador-san-pedro-tlaquepaque'})

    def test_el_nombre_del_municipio_no_es_un_lugar(self):
        self.assertIn('Duplicados: 1', self.importar(respuesta(lugar(1, 'Tapalpa', 19.9, -103.5, tourism='attraction'))))
        self.assertFalse(Destino.objects.exists())

    def test_nombre_sin_letras_latinas_no_se_toma_por_duplicado(self):
        Destino.objects.create(nombre='Otro', slug='otro', descripcion='-', latitud='19.9', longitud='-103.5',
                               municipio=Municipio.objects.create(
                                   nombre='Tapalpa', slug='tapalpa',
                                   region=Region.objects.create(nombre='Sierra', slug='sierra')))
        self.importar(respuesta(lugar(1, '博物館', 19.9, -103.5, tourism='museum')))
        self.assertEqual(Destino.objects.get(osm_id='node/1').slug, 'lugar')

    def test_simular_no_guarda_nada(self):
        salida = self.importar(respuesta(lugar(1, 'Museo', 19.9, -103.5, tourism='museum')), simular=True)
        self.assertIn('Se crearían 1', salida)
        self.assertFalse(Destino.objects.exists())
        self.assertFalse(Municipio.objects.exists())
        self.assertFalse(Categoria.objects.exists())

    def test_guardar_y_leer_un_archivo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, 'osm.json')
            self.importar(respuesta(lugar(1, 'Museo', 19.9, -103.5, tourism='museum')), guardar=ruta, simular=True)
            with patch('apps.destinos.management.commands.importar_osm.descargar', side_effect=AssertionError('sin red')):
                call_command('importar_osm', archivo=ruta, stdout=StringIO())
        self.assertEqual(Destino.objects.count(), 1)

    def test_si_el_servidor_falla_no_importa_nada_y_lo_explica(self):
        with patch('apps.destinos.management.commands.importar_osm.descargar', side_effect=ErrorOverpass('saturado')):
            with self.assertRaisesMessage(CommandError, 'saturado'):
                call_command('importar_osm', stdout=StringIO())
        self.assertFalse(Destino.objects.exists())

    def test_avisa_si_no_hay_nada_publicado(self):
        self.assertIn('No hay destinos publicados', self.importar(respuesta(lugar(1, 'M', 19.9, -103.5, tourism='museum'))))


class PublicacionYCreditoTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(nombre='Sierra', slug='sierra')
        self.tapalpa = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=self.region)
        self.vacio = Municipio.objects.create(nombre='Sin publicar', slug='sin-publicar', region=self.region)
        self.propio = Destino.objects.create(nombre='Propio', slug='propio', municipio=self.tapalpa, descripcion='-',
                                             latitud=19.9, longitud=-103.5)
        self.importado = Destino.objects.create(nombre='Importado', slug='importado', municipio=self.vacio, descripcion='-',
                                                latitud=19.9, longitud=-103.5, es_activo=False, osm_id='node/42')

    def admin_y_peticion(self):
        peticion = RequestFactory().post('/admin/')
        peticion.user = Usuario.objects.create_superuser('m@example.com', 'Mod', 'P', 'Prueba-segura-493!')
        return DestinoAdmin(Destino, AdminSite()), peticion

    def test_oculto_no_aparece_en_publico(self):
        self.assertEqual(self.client.get('/destinos/importado/').status_code, 404)
        self.assertNotContains(self.client.get('/destinos/'), 'Importado')

    def test_publicar_y_ocultar_desde_el_admin(self):
        admin, peticion = self.admin_y_peticion()
        admin.publicar(peticion, Destino.objects.filter(pk=self.importado.pk))
        self.importado.refresh_from_db()
        self.assertTrue(self.importado.es_activo)
        admin.ocultar(peticion, Destino.objects.filter(pk=self.importado.pk))
        self.importado.refresh_from_db()
        self.assertFalse(self.importado.es_activo)

    def test_el_admin_filtra_por_origen(self):
        self.client.force_login(self.admin_y_peticion()[1].user)
        pendientes = self.client.get('/admin/destinos/destino/', {'origen': 'osm_pendiente'})
        self.assertContains(pendientes, 'Importado')
        self.assertNotContains(pendientes, 'Propio')
        propios = self.client.get('/admin/destinos/destino/', {'origen': 'propio'})
        self.assertContains(propios, 'Propio')
        self.assertNotContains(propios, 'Importado</a>')

    def test_la_ficha_y_la_api_atribuyen_solo_lo_importado(self):
        Destino.objects.filter(pk=self.importado.pk).update(es_activo=True)
        ficha = self.client.get('/destinos/importado/')
        self.assertContains(ficha, 'colaboradores de OpenStreetMap')
        self.assertContains(ficha, 'https://www.openstreetmap.org/node/42')
        self.assertNotContains(self.client.get('/destinos/propio/'), 'colaboradores de OpenStreetMap')
        resultados = {d['slug']: d for d in self.client.get('/api/v1/destinos/').data['results']}
        self.assertIn('OpenStreetMap', resultados['importado']['atribucion'])
        self.assertIsNone(resultados['propio']['atribucion'])
        self.assertContains(self.client.get('/creditos/'), 'OpenStreetMap')

    def test_los_filtros_solo_ofrecen_lo_que_tiene_destinos_publicados(self):
        formulario = self.client.get('/destinos/').context['formulario']
        opciones = [slug for slug, _ in formulario.fields['municipio'].choices]
        self.assertIn('tapalpa', opciones)
        self.assertNotIn('sin-publicar', opciones)
