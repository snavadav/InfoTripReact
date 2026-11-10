"""Direcciones con OpenStreetMap. Photon y Nominatim siempre simulados: ninguna prueba sale a la red."""
import io
import json
import logging
import urllib.error
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from redis.exceptions import RedisError
from rest_framework.test import APIClient

from apps.destinos import direcciones
from apps.usuarios.models import Usuario

SUGERIR, BUSCAR, INVERSA = '/api/v1/direcciones/sugerir/', '/api/v1/direcciones/buscar/', '/api/v1/direcciones/inversa/'
TURNO = 'direcciones:turno:nominatim'


def rasgo_photon(nombre, lat, lon, estado='Jalisco', pais='MX', **extra):
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
            'properties': {'name': nombre, 'state': estado, 'countrycode': pais, 'city': 'Guadalajara', **extra}}


def lugar_nominatim(lat, lon, calle='Avenida Juárez', numero='976', estado='Jalisco', **extra):
    return {'lat': str(lat), 'lon': str(lon), 'name': '', 'display_name': f'{calle} {numero}, Guadalajara, {estado}, México',
            'address': {'road': calle, 'house_number': numero, 'suburb': 'Centro', 'city': 'Guadalajara',
                        'state': estado, 'country_code': 'mx', **extra}}


PHOTON = {'features': [
    rasgo_photon('Catedral de Guadalajara', 20.67678, -103.34698, street='Avenida Alcalde', district='Centro'),
    rasgo_photon('Catedral de Morelia', 19.70251, -101.19234, estado='Michoacán'),  # dentro del recuadro, otro estado
    rasgo_photon('Catedral de Tepic', 21.50951, -104.89569, estado='Nayarit'),
    rasgo_photon('Catedral de Madrid', 40.41578, -3.71435, estado='Madrid', pais='ES'),
    rasgo_photon('Catedral de León', 21.12345, -101.68234, estado='Guanajuato'),
]}


class SimuladorDeRed:
    """Sustituye a urlopen: registra cada petición y devuelve lo que se le indique por servicio."""

    def __init__(self, photon=None, nominatim=None, error=None):
        self.photon, self.nominatim, self.error = photon, nominatim, error
        self.peticiones = []

    def __call__(self, pedido, timeout=None):
        self.peticiones.append(pedido)
        self.timeout = timeout
        if self.error:
            raise self.error
        datos = self.photon if 'photon' in pedido.full_url else self.nominatim
        return io.BytesIO(json.dumps(datos).encode())

    def parametros(self, indice=-1):
        return {clave: valores[0] for clave, valores in parse_qs(urlsplit(self.peticiones[indice].full_url).query).items()}


class NormalizacionTests(SimpleTestCase):
    def test_minusculas_sin_acentos_y_espacios_colapsados(self):
        self.assertEqual(direcciones.normalizar('  Av.  JUÁREZ   976,\tGuadalajara '), 'av. juarez 976, guadalajara')
        self.assertEqual(direcciones.normalizar('Ñuñoa'), 'nunoa')

    def test_redondea_a_cinco_decimales(self):
        self.assertEqual(direcciones.redondear(20.674567891), 20.67457)

    def test_respuesta_de_nominatim_normalizada(self):
        resultado = direcciones.desde_nominatim(lugar_nominatim(20.6741234567, -103.3487654321))
        self.assertEqual(resultado, {
            'etiqueta': 'Avenida Juárez 976, Centro, Guadalajara, Jalisco', 'calle': 'Avenida Juárez 976',
            'colonia': 'Centro', 'municipio': 'Guadalajara', 'estado': 'Jalisco', 'lat': 20.67412, 'lon': -103.34877})


@override_settings(GEOCODIFICACION_PROVEEDOR='apps.destinos.direcciones.OSMPublico',
                   GEOCODIFICACION_SEGUNDOS_ENTRE_PETICIONES=1, CONTACTO_GEOCODIFICACION='equipo@example.org')
class DireccionesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.cliente = APIClient()
        self.red = SimuladorDeRed(photon=PHOTON, nominatim=[lugar_nominatim(20.67412, -103.34877)])
        parche = mock.patch('urllib.request.urlopen', self.red)
        parche.start()
        self.addCleanup(parche.stop)
        # Esperar turno no detiene la prueba: cada espera simula que ya pasó el segundo.
        espera = mock.patch('apps.destinos.direcciones.time.sleep', side_effect=lambda _s: cache.delete(TURNO))
        self.espera = espera.start()
        self.addCleanup(espera.stop)

    # ─── Sugerencias (Photon) ───

    def test_sugerir_usa_photon_limitado_a_jalisco(self):
        respuesta = self.cliente.get(SUGERIR, {'q': 'catedral'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual([r['etiqueta'] for r in respuesta.json()],
                         ['Catedral de Guadalajara, Avenida Alcalde, Centro, Guadalajara, Jalisco'])
        self.assertEqual(set(respuesta.json()[0]), {'etiqueta', 'calle', 'colonia', 'municipio', 'estado', 'lat', 'lon'})
        self.assertEqual(len(self.red.peticiones), 1)
        self.assertIn('photon.komoot.io', self.red.peticiones[0].full_url)
        self.assertEqual(self.red.parametros()['bbox'], '-105.75,18.85,-101.45,22.8')

    def test_nunca_autocompleta_con_nominatim(self):
        for texto in ['cat', 'cate', 'catedr', 'catedral de gua']:
            self.cliente.get(SUGERIR, {'q': texto})
        self.assertTrue(self.red.peticiones)
        self.assertFalse([p for p in self.red.peticiones if 'nominatim' in p.full_url])

    def test_menos_de_tres_caracteres_no_consulta(self):
        respuesta = self.cliente.get(SUGERIR, {'q': ' Gu '})
        self.assertEqual(respuesta.json(), [])
        self.assertEqual(self.red.peticiones, [])
        self.assertEqual(self.cliente.get(SUGERIR).status_code, 400)

    def test_maximo_cinco_resultados(self):
        self.red.photon = {'features': [rasgo_photon(f'Calle {n}', 20.6 + n / 100, -103.3) for n in range(10)]}
        self.assertEqual(len(self.cliente.get(SUGERIR, {'q': 'calle'}).json()), 5)

    # ─── Caché ───

    def test_cache_por_consulta_normalizada(self):
        primera = self.cliente.get(SUGERIR, {'q': 'Catedral  Guadalajara'}).json()
        segunda = self.cliente.get(SUGERIR, {'q': ' catedral guadalajara'}).json()
        tercera = self.cliente.get(SUGERIR, {'q': 'CATEDRAL GUADALAJARA'}).json()
        self.assertEqual(primera, segunda)
        self.assertEqual(primera, tercera)
        self.assertEqual(len(self.red.peticiones), 1)
        # Otra operación con el mismo texto no comparte resultado.
        self.cliente.get(BUSCAR, {'q': 'catedral guadalajara'})
        self.assertEqual(len(self.red.peticiones), 2)

    def test_cache_dura_treinta_dias_y_no_guarda_el_texto(self):
        with mock.patch('apps.destinos.direcciones.cache.set') as guardar:
            self.cliente.get(SUGERIR, {'q': 'Catedral Guadalajara'})
        clave, _valor = guardar.call_args.args
        self.assertEqual(guardar.call_args.kwargs['timeout'], 30 * 24 * 3600)
        self.assertNotIn('catedral', clave.lower())

    # ─── Búsqueda e inversa (Nominatim) ───

    def test_buscar_con_nominatim_dentro_de_jalisco(self):
        respuesta = self.cliente.get(BUSCAR, {'q': 'Av. Juárez 976, Guadalajara'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()[0]['calle'], 'Avenida Juárez 976')
        parametros = self.red.parametros()
        self.assertTrue(self.red.peticiones[0].full_url.startswith('https://nominatim.openstreetmap.org/search?'))
        self.assertEqual(parametros['format'], 'jsonv2')
        self.assertEqual(parametros['countrycodes'], 'mx')
        self.assertEqual(parametros['bounded'], '1')
        self.assertEqual(parametros['viewbox'], '-105.75,22.8,-101.45,18.85')
        self.assertEqual(parametros['accept-language'], 'es')

    def test_buscar_descarta_otros_estados(self):
        self.red.nominatim = [lugar_nominatim(19.70, -101.19, estado='Michoacán'), lugar_nominatim(20.67, -103.35)]
        self.assertEqual([r['estado'] for r in self.cliente.get(BUSCAR, {'q': 'juarez 976'}).json()], ['Jalisco'])

    def test_inversa_redondea_las_coordenadas(self):
        self.red.nominatim = lugar_nominatim(20.6741234, -103.3487654)
        respuesta = self.cliente.get(INVERSA, {'lat': '20.674123456789', 'lon': '-103.348765432109'})
        self.assertEqual(respuesta.json()[0]['etiqueta'], 'Avenida Juárez 976, Centro, Guadalajara, Jalisco')
        parametros = self.red.parametros()
        self.assertIn('/reverse?', self.red.peticiones[0].full_url)
        self.assertEqual((parametros['lat'], parametros['lon']), ('20.67412', '-103.34877'))
        self.assertEqual(respuesta.json()[0]['lat'], 20.67412)

    def test_inversa_fuera_de_jalisco_no_consulta(self):
        self.assertEqual(self.cliente.get(INVERSA, {'lat': 19.43, 'lon': -99.13}).json(), [])
        self.assertEqual(self.red.peticiones, [])

    def test_inversa_sin_direccion(self):
        self.red.nominatim = {'error': 'Unable to geocode'}
        self.assertEqual(self.cliente.get(INVERSA, {'lat': 20.5, 'lon': -103.5}).json(), [])

    def test_inversa_valida_las_coordenadas(self):
        self.assertEqual(self.cliente.get(INVERSA, {'lat': 'abc', 'lon': -103}).status_code, 400)
        self.assertEqual(self.cliente.get(INVERSA, {'lat': 91, 'lon': -103}).status_code, 400)

    # ─── Identificación ───

    def test_user_agent_y_email_con_el_contacto(self):
        self.cliente.get(BUSCAR, {'q': 'juarez 976'})
        self.cliente.get(SUGERIR, {'q': 'catedral'})
        for pedido in self.red.peticiones:
            self.assertEqual(pedido.get_header('User-agent'), 'InfoTrip/1.0 (+https://infotrip.online; equipo@example.org)')
        self.assertEqual(self.red.parametros(0)['email'], 'equipo@example.org')
        self.assertEqual(self.red.timeout, 5)

    def test_el_contacto_sale_de_la_configuracion(self):
        with self.settings(CONTACTO_GEOCODIFICACION=''):
            self.cliente.get(BUSCAR, {'q': 'juarez 976'})
        self.assertEqual(self.red.peticiones[0].get_header('User-agent'), 'InfoTrip/1.0 (+https://infotrip.online)')
        self.assertNotIn('email', self.red.parametros())
        # Ningún correo escrito a mano en el módulo.
        fuente = Path(direcciones.__file__).read_text(encoding='utf-8')
        self.assertNotRegex(fuente, r'[\w.+-]+@[\w-]+\.[\w.]+')

    # ─── Límite de 1 por segundo a Nominatim ───

    def test_nominatim_espera_su_turno(self):
        self.cliente.get(BUSCAR, {'q': 'juarez 976'})
        self.assertEqual(self.espera.call_count, 0)
        self.cliente.get(BUSCAR, {'q': 'hidalgo 10'})  # el turno sigue tomado: espera una vez y sigue
        self.assertEqual(self.espera.call_count, 1)
        self.assertEqual(len(self.red.peticiones), 2)

    def test_sin_turno_responde_503_amable(self):
        self.espera.side_effect = None  # el segundo nunca pasa
        self.assertEqual(self.cliente.get(BUSCAR, {'q': 'juarez 976'}).status_code, 200)
        respuesta = self.cliente.get(INVERSA, {'lat': 20.6, 'lon': -103.3})
        self.assertEqual(respuesta.status_code, 503)
        self.assertIn('Intenta de nuevo', respuesta.json()['detail'])
        self.assertEqual(len(self.red.peticiones), 1)
        self.assertEqual(self.espera.call_count, direcciones.INTENTOS_POR_TURNO - 1)

    def test_el_turno_es_de_un_segundo_en_la_cache_compartida(self):
        with mock.patch('apps.destinos.direcciones.cache.add', return_value=True) as tomar:
            self.cliente.get(BUSCAR, {'q': 'juarez 976'})
        tomar.assert_called_once_with(TURNO, 1, timeout=1)

    def test_photon_no_usa_el_turno_de_nominatim(self):
        cache.add(TURNO, 1, timeout=60)
        self.espera.side_effect = None
        self.assertEqual(self.cliente.get(SUGERIR, {'q': 'catedral'}).status_code, 200)

    def test_sin_redis_no_se_consulta_nominatim(self):
        with mock.patch('apps.destinos.direcciones.cache.add', side_effect=RedisError('caído')):
            respuesta = self.cliente.get(BUSCAR, {'q': 'juarez 976'})
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(self.red.peticiones, [])

    # ─── Errores del servicio ───

    def test_timeout_o_error_responden_503_amable_y_no_se_guardan(self):
        for error in [TimeoutError(), urllib.error.URLError('sin red'),
                      urllib.error.HTTPError('https://x', 429, 'Too Many', {}, None)]:
            with self.subTest(error=type(error).__name__):
                cache.clear()
                self.red.error = error
                respuesta = self.cliente.get(SUGERIR, {'q': 'catedral'})
                self.assertEqual(respuesta.status_code, 503)
                self.assertIn('marcar el punto directamente en el mapa', respuesta.json()['detail'])
        self.red.error = None
        self.assertEqual(self.cliente.get(SUGERIR, {'q': 'catedral'}).status_code, 200)

    def test_respuesta_que_no_es_json(self):
        with mock.patch('urllib.request.urlopen', return_value=io.BytesIO(b'<html>')):
            self.assertEqual(self.cliente.get(SUGERIR, {'q': 'catedral'}).status_code, 503)

    # ─── Privacidad ───

    def test_las_coordenadas_no_aparecen_en_los_registros(self):
        salida = io.StringIO()
        manejador = logging.StreamHandler(salida)
        manejador.setFormatter(logging.Formatter('%(name)s %(message)s %(args)s'))
        registros = [logging.getLogger(), logging.getLogger('infotrip'), logging.getLogger('django')]
        niveles = [r.level for r in registros]
        for r in registros:
            r.addHandler(manejador)
            r.setLevel(logging.DEBUG)
        try:
            self.red.nominatim = lugar_nominatim(20.6741234, -103.3487654)
            self.cliente.get(INVERSA, {'lat': '20.6748123', 'lon': '-103.3489321'})
            self.red.error = TimeoutError()
            self.cliente.get(INVERSA, {'lat': '20.6758123', 'lon': '-103.3499321'})
            self.red.error = urllib.error.HTTPError('https://n/reverse?lat=20.6768123', 500, 'Error', {}, None)
            self.cliente.get(INVERSA, {'lat': '20.6768123', 'lon': '-103.3509321'})
            self.cliente.get(INVERSA, {'lat': '120.6778123', 'lon': '-103.3519321'})
        finally:
            for r, nivel in zip(registros, niveles):
                r.removeHandler(manejador)
                r.setLevel(nivel)
        texto = salida.getvalue()
        self.assertIn('/api/v1/direcciones/inversa/', texto)  # sí se registró algo de esas peticiones
        for fragmento in ['20.67', '-103.3', '120.67', '103.35']:
            self.assertNotIn(fragmento, texto)

    def test_el_registro_de_accesos_no_guarda_la_consulta(self):
        raiz = Path(settings.BASE_DIR)
        gunicorn = (raiz / 'gunicorn.conf.py').read_text(encoding='utf-8')
        self.assertIn('%(U)s', gunicorn)
        self.assertNotIn('%(r)s', gunicorn)
        self.assertNotIn('%(q)s', gunicorn)
        for nombre in ['nginx.conf', 'nginx-https.conf']:
            nginx = (raiz / 'docker' / nombre).read_text(encoding='utf-8')
            self.assertIn('access_log /var/log/nginx/access.log sin_consulta;', nginx)
            self.assertNotIn('$request ', nginx)
            self.assertNotIn('$args', nginx)

    def test_no_se_guarda_quien_busco(self):
        usuario = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', 'Prueba-segura-493!')
        self.cliente.force_authenticate(usuario)
        respuesta = self.cliente.get(SUGERIR, {'q': 'Catedral Guadalajara'}, REMOTE_ADDR='10.1.2.3')
        claves = [clave for clave in cache._cache if 'direcciones:sugerir' in clave]
        self.assertEqual(len(claves), 1)
        # Solo la huella de la consulta y los resultados: ni el texto, ni la cuenta, ni la IP.
        self.assertRegex(claves[0], r'direcciones:sugerir:[0-9a-f]{32}$')
        self.assertEqual(cache.get(claves[0].split(':', 2)[2]), respuesta.json())
        self.assertNotIn('10.1.2.3', str(cache.get(claves[0].split(':', 2)[2])))

    # ─── Proveedor intercambiable ───

    def test_otro_nominatim_solo_con_configuracion(self):
        with self.settings(GEOCODIFICACION_NOMINATIM_URL='https://geo.example.org/', GEOCODIFICACION_CLAVE='k',
                           GEOCODIFICACION_SEGUNDOS_ENTRE_PETICIONES=0):
            self.cliente.get(BUSCAR, {'q': 'juarez 976'})
        self.assertTrue(self.red.peticiones[0].full_url.startswith('https://geo.example.org/search?'))
        self.assertEqual(self.red.parametros()['key'], 'k')

    def test_proveedor_desactivado_no_sale_a_la_red(self):
        with self.settings(GEOCODIFICACION_PROVEEDOR='apps.destinos.direcciones.Desactivado'):
            self.assertEqual(self.cliente.get(BUSCAR, {'q': 'juarez 976'}).json(), [])
            self.assertEqual(self.cliente.get(INVERSA, {'lat': 20.6, 'lon': -103.3}).json(), [])
        self.assertEqual(self.red.peticiones, [])


class LimitePorPersonaTests(TestCase):
    """Throttle por usuario o IP (con el proveedor desactivado de las pruebas)."""

    def setUp(self):
        cache.clear()

    def test_limite_por_ip_y_por_usuario(self):
        usuario = Usuario.objects.create_user('luis@example.com', 'Luis', 'P', 'Prueba-segura-493!')
        for vista, limite in [(SUGERIR, direcciones.LimiteSugerir), (BUSCAR, direcciones.LimiteBuscar),
                              (INVERSA, direcciones.LimiteInversa)]:
            with self.subTest(vista=vista), mock.patch.object(limite, 'rate', '2/min'):
                cache.clear()
                anonimo = APIClient()
                datos = {'lat': 20.6, 'lon': -103.3} if vista == INVERSA else {'q': 'catedral'}
                self.assertEqual([anonimo.get(vista, datos).status_code for _ in range(3)], [200, 200, 429])
                # Otra IP no comparte el límite.
                self.assertEqual(APIClient(REMOTE_ADDR='10.0.0.9').get(vista, datos).status_code, 200)
                # Una persona con cuenta tiene el suyo aunque venga de la misma IP.
                conectado = APIClient()
                conectado.force_authenticate(usuario)
                self.assertEqual(conectado.get(vista, datos).status_code, 200)


class PaginasTests(TestCase):
    def test_creditos_y_proponer(self):
        creditos = self.client.get('/creditos/').content.decode()
        self.assertIn('Direcciones: <a href="https://www.openstreetmap.org/copyright"', creditos)
        self.assertIn('vía <a href="https://nominatim.org/"', creditos)
        self.assertIn('(ODbL)', creditos)
        proponer = self.client.get('/lugares/proponer/').content.decode()
        self.assertIn('js/direcciones.js', proponer)
        self.assertIn('id="propuesta-direccion" name="direccion"', proponer)
        # Todo sale de nuestro dominio: ni la página ni la CSP mencionan los servicios de OSM.
        self.assertNotIn('nominatim', proponer.lower())
        self.assertNotIn('photon', proponer.lower())
