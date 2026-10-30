"""Importación del DENUE. Nunca consulta la red y la clave no debe aparecer en ningún mensaje."""
import urllib.error
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from .denue import ErrorDenue, _pedir, descargar, es_generico, interpretar, nombre_legible
from .models import Lugar, TIPO_DE_SUBTIPO

CLAVE = 'clave-secreta-de-prueba'
COMANDO = 'apps.destinos.management.commands.importar_denue.descargar'


def registro(identificador=1, nombre='HOTEL SIERRA', clase='721111', **campos):
    return {'Id': str(identificador), 'Nombre': nombre, 'CLASE_ACTIVIDAD_ID': clase, 'Clase_actividad': 'Hoteles',
            'Estrato': '6 a 10 personas', 'Tipo': 'Fijo', 'Ubicacion': 'TAPALPA,Tapalpa,JALISCO', 'Latitud': '19.945',
            'Longitud': '-103.757', 'Tipo_vialidad': 'CALLE', 'Calle': 'MORELOS', 'Num_Exterior': '10', 'Colonia': 'CENTRO',
            'Telefono': '3312345678', 'Sitio_internet': 'WWW.SIERRA.MX', 'Correo_e': 'dueno@example.com',
            'Razon_social': 'JUAN PEREZ LOPEZ', **campos}


def interpreta(*registros):
    return interpretar(list(registros), TIPO_DE_SUBTIPO)


class InterpretarTests(TestCase):
    def test_convierte_campos_y_no_trae_datos_de_personas(self):
        lugares, omitidos = interpreta(registro())
        sitio = lugares[0]
        self.assertEqual(omitidos, 0)
        self.assertEqual((sitio['nombre'], sitio['tipo'], sitio['subtipo'], sitio['municipio'], sitio['telefono'], sitio['sitio_web']),
                         ('Hotel Sierra', 'dormir', 'hotel', 'Tapalpa', '3312345678', 'https://www.sierra.mx'))
        self.assertEqual(sitio['direccion'], 'Calle Morelos 10, Centro')
        texto = str(sitio)
        self.assertNotIn('dueno@example.com', texto)
        self.assertNotIn('PEREZ', texto)

    def test_clasifica_por_actividad(self):
        casos = [('721112', 'Moteles', 'motel', 'dormir'), ('722511', 'Restaurantes a la carta', 'restaurant', 'comer'),
                 ('722513', 'Restaurantes de tacos y tortas', 'fast_food', 'comer'), ('722515', 'Cafeterías', 'cafe', 'comer'),
                 ('722412', 'Bares y cantinas', 'bar', 'comer'), ('468411', 'Gasolineras', 'fuel', 'gasolina'),
                 ('464111', 'Farmacias', 'pharmacy', 'farmacia'), ('522110', 'Banca', 'bank', 'cajero'),
                 ('465912', 'Artesanías', 'craft', 'comprar')]
        for clase, descripcion, subtipo, tipo in casos:
            sitio = interpreta(registro(clase=clase, Clase_actividad=descripcion))[0][0]
            self.assertEqual((sitio['subtipo'], sitio['tipo']), (subtipo, tipo), clase)

    def test_omite_lo_que_no_sirve(self):
        for cambio in [{'clase': '722310', 'Clase_actividad': 'Comedores'}, {'clase': '999999'}, {'nombre': 'RESTAURANTE'},
                       {'nombre': 'SIN NOMBRE'}, {'nombre': ''}, {'Latitud': ''}, {'Tipo': 'Semifijo'}, {'Ubicacion': 'x'}]:
            self.assertEqual(interpreta(registro(**cambio))[0], [], cambio)

    def test_comida_pequena_solo_se_omite_en_la_zona_metropolitana(self):
        comida = {'clase': '722511', 'Estrato': '0 a 5 personas'}
        self.assertEqual(interpreta(registro(Ubicacion='ZAPOPAN,Zapopan,JALISCO', **comida))[0], [])
        self.assertEqual(len(interpreta(registro(**comida))[0]), 1)
        self.assertEqual(len(interpreta(registro(Ubicacion='ZAPOPAN,Zapopan,JALISCO', clase='722511'))[0]), 1)
        # El tamaño solo filtra comida: un hotel pequeño en la ciudad se queda.
        self.assertEqual(len(interpreta(registro(Ubicacion='ZAPOPAN,Zapopan,JALISCO', Estrato='0 a 5 personas'))[0]), 1)

    def test_sitio_web_solo_si_es_valido(self):
        for valor, esperado in [('www.a.mx', 'https://www.a.mx'), ('http://a.mx', 'http://a.mx'), ('javascript:alert(1)', ''),
                                ('no tiene', ''), ('', '')]:
            self.assertEqual(interpreta(registro(Sitio_internet=valor))[0][0]['sitio_web'], esperado, valor)

    def test_nombres(self):
        self.assertEqual(nombre_legible(' HOTEL  DE LA SIERRA '), 'Hotel de la Sierra')
        self.assertEqual(nombre_legible("MARY'S"), "Mary's")
        self.assertEqual(nombre_legible('EL MEXICANO'), 'El Mexicano')
        self.assertTrue(es_generico('Farmacia'))
        self.assertFalse(es_generico('Farmacia Tapalpa'))


class DescargaTests(TestCase):
    @override_settings(DENUE_TOKEN=CLAVE)
    def test_los_errores_nunca_muestran_la_clave(self):
        errores = [urllib.error.HTTPError(f'https://x/{CLAVE}', 500, 'Error', {}, None), urllib.error.URLError('sin red'), TimeoutError()]
        for error in errores:
            with patch('apps.destinos.denue.urllib.request.urlopen', side_effect=error):
                with self.assertRaises(ErrorDenue) as contexto:
                    _pedir('Cuantificar/721/14/0')
            self.assertNotIn(CLAVE, str(contexto.exception))
            self.assertIsNone(contexto.exception.__cause__)

    @override_settings(DENUE_TOKEN='')
    def test_sin_clave_lo_explica(self):
        with self.assertRaisesMessage(ErrorDenue, 'DENUE_TOKEN'):
            _pedir('x')

    @override_settings(DENUE_TOKEN=CLAVE)
    def test_descarga_incompleta_no_devuelve_nada(self):
        with patch('apps.destinos.denue.ACTIVIDADES', [('721', '72/721/0/0')]), patch('apps.destinos.denue.contar', return_value=100), \
                patch('apps.destinos.denue._pedir', return_value=[registro()]):
            with self.assertRaisesMessage(ErrorDenue, 'llegaron 1 de 100'):
                descargar(espera=0)

    @override_settings(DENUE_TOKEN=CLAVE)
    def test_recorre_las_paginas(self):
        paginas = [[registro(i) for i in range(3)], [registro(9)]]
        with patch('apps.destinos.denue.ACTIVIDADES', [('721', '72/721/0/0')]), patch('apps.destinos.denue.contar', return_value=4), \
                patch('apps.destinos.denue.POR_PAGINA', 3), patch('apps.destinos.denue._pedir', side_effect=paginas) as pedir:
            self.assertEqual(len(descargar(espera=0)), 4)
        self.assertIn('/4/6/', pedir.call_args_list[1][0][0])


class ComandoTests(TestCase):
    def importar(self, *registros, **opciones):
        salida = StringIO()
        with patch(COMANDO, return_value=list(registros)):
            call_command('importar_denue', stdout=salida, **opciones)
        return salida.getvalue()

    def osm(self, nombre='Hotel Sierra', latitud='19.945', longitud='-103.757'):
        return Lugar.objects.create(nombre=nombre, tipo='dormir', subtipo='hotel', latitud=latitud, longitud=longitud, osm_id='node/1')

    def test_crea_publicado_y_repetir_actualiza_sin_duplicar(self):
        self.importar(registro())
        sitio = Lugar.objects.get()
        self.assertTrue(sitio.es_activo)
        self.assertEqual((sitio.denue_id, sitio.osm_id, sitio.municipio.nombre), ('1', None, 'Tapalpa'))
        salida = self.importar(registro(Telefono='555'))
        self.assertEqual(Lugar.objects.get().telefono, '555')
        self.assertIn('Actualizados: 1', salida)

    def test_no_duplica_lo_que_ya_existe_de_osm(self):
        self.osm()
        self.assertIn('Ya existían: 1', self.importar(registro()))
        self.assertEqual(Lugar.objects.count(), 1)

    def test_mismo_nombre_lejos_u_otro_nombre_cerca_si_se_crea(self):
        self.osm(latitud='19.960')
        self.importar(registro())
        self.importar(registro(2, nombre='PENSION AZUL'))
        self.assertEqual(Lugar.objects.count(), 3)

    def test_lo_editado_en_el_admin_no_se_toca_y_lo_oculto_sigue_oculto(self):
        self.importar(registro())
        Lugar.objects.update(nombre='Corregido', protegido=True, es_activo=False)
        self.assertIn('sin tocar: 1', self.importar(registro()))
        sitio = Lugar.objects.get()
        self.assertEqual((sitio.nombre, sitio.es_activo), ('Corregido', False))

    def test_retirar_ausentes_no_toca_otras_fuentes(self):
        self.osm(latitud='20')
        self.importar(registro(), registro(2, nombre='OTRO HOTEL', Latitud='19.99'))
        salida = self.importar(registro(), retirar_ausentes=True)
        self.assertIn('Retirados: 1', salida)
        self.assertFalse(Lugar.objects.get(denue_id='2').es_activo)
        self.assertTrue(Lugar.objects.get(osm_id='node/1').es_activo)

    def test_descarga_vacia_no_cambia_nada_y_el_error_se_explica(self):
        self.importar(registro())
        with self.assertRaises(CommandError):
            self.importar(retirar_ausentes=True)
        self.assertTrue(Lugar.objects.get().es_activo)
        with patch(COMANDO, side_effect=ErrorDenue('sin red')), self.assertRaisesMessage(CommandError, 'sin red'):
            call_command('importar_denue', stdout=StringIO())

    def test_simular_no_guarda_nada(self):
        self.assertIn('Se crearían 1', self.importar(registro(), simular=True))
        self.assertFalse(Lugar.objects.exists())


class AtribucionTests(APITestCase):
    def setUp(self):
        self.sitio = Lugar.objects.create(nombre='Hotel Sierra', tipo='dormir', subtipo='hotel', latitud='19.945',
                                          longitud='-103.757', denue_id='7')

    def test_ficha_y_api_citan_al_inegi_y_aclaran_que_no_es_oficial(self):
        ficha = self.client.get(f'/lugares/{self.sitio.pk}/')
        self.assertContains(ficha, 'Fuente: INEGI')
        self.assertContains(ficha, 'no representa una postura del INEGI')
        self.assertNotContains(ficha, 'Agregado por la comunidad')
        self.assertNotContains(ficha, 'colaboradores de OpenStreetMap')
        datos = self.client.get('/api/v1/lugares/', {'sur': 19.9, 'oeste': -103.8, 'norte': 20, 'este': -103.7}).data['resultados'][0]
        self.assertIn('INEGI', datos['atribucion'])
        self.assertContains(self.client.get('/creditos/'), 'DENUE')

    def test_la_clave_nunca_llega_al_navegador(self):
        with override_settings(DENUE_TOKEN=CLAVE):
            for ruta in ('/', '/destinos/', f'/lugares/{self.sitio.pk}/', '/creditos/'):
                self.assertNotContains(self.client.get(ruta), CLAVE)

    def test_cerca_de_mi_con_muchos_lugares_consulta_acotado(self):
        for numero in range(60):
            Lugar.objects.create(nombre=f'L{numero}', tipo='comer', subtipo='restaurant', latitud='19.945', longitud=f'-103.75{numero:02d}')
        with self.assertNumQueries(2):
            respuesta = self.client.post('/api/v1/lugares/cerca/', {'latitud': 19.945, 'longitud': -103.75}, format='json')
        self.assertEqual(len(respuesta.data['resultados']), 50)
        distancias = [fila['distancia_km'] for fila in respuesta.data['resultados']]
        self.assertEqual(distancias, sorted(distancias))
