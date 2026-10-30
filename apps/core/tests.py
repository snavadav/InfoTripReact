"""Fase 5: endpoint de salud y registros (logging) en los puntos clave."""
from smtplib import SMTPException
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from redis.exceptions import RedisError
from rest_framework.test import APITestCase

from apps.comunidad.models import Aporte
from apps.comunidad.moderacion import moderar
from apps.core.limites import LimiteAnonimo
from apps.destinos.models import Destino, Municipio, Region
from apps.destinos.views import RegionListView
from apps.usuarios.models import Usuario
from infotrip.settings import base


class SaludTests(TestCase):
    def test_sano(self):
        respuesta = self.client.get('/health/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {'estado': 'ok', 'base_de_datos': 'ok', 'cache': 'ok'})
        self.assertIn('no-cache', respuesta.headers['Cache-Control'])

    def test_base_de_datos_caida(self):
        with patch('apps.core.views.connection.cursor', side_effect=OSError('sin conexión')), \
                self.assertLogs('infotrip.salud', 'ERROR'):
            respuesta = self.client.get('/health/')
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta.json()['base_de_datos'], 'error')

    def test_cache_caida(self):
        with patch('apps.core.views.cache.set', side_effect=ConnectionError('redis')), \
                self.assertLogs('infotrip.salud', 'ERROR'):
            respuesta = self.client.get('/health/')
        self.assertEqual((respuesta.status_code, respuesta.json()['cache']), (503, 'error'))

    def test_solo_get(self):
        self.assertEqual(self.client.post('/health/').status_code, 405)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RegistrosTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.usuario = Usuario.objects.create_user('registro@example.com', 'Ana', 'Prueba', 'Prueba-segura-493!')

    def test_bloqueo_de_cuenta_sin_el_correo(self):
        with self.assertLogs('infotrip.seguridad', 'WARNING') as registros:
            for intento in range(5):
                self.client.post('/api/v1/auth/login/', {'email': self.usuario.email, 'password': 'mal'},
                                 REMOTE_ADDR=f'203.0.113.{intento}')
        self.assertEqual(len(registros.output), 1)
        self.assertIn('Cuenta bloqueada', registros.output[0])
        self.assertNotIn('registro@example.com', registros.output[0])

    def test_fallo_de_smtp_en_login_y_recuperacion(self):
        credenciales = {'email': self.usuario.email, 'password': 'Prueba-segura-493!'}
        with patch('apps.usuarios.verificacion.send_mail', side_effect=SMTPException('caído')), \
                self.assertLogs('infotrip.correo', 'ERROR') as registros:
            self.assertEqual(self.client.post('/api/v1/auth/login/', credenciales).status_code, 503)
        self.assertIn(f'usuario {self.usuario.pk}', registros.output[0])
        with patch('apps.usuarios.recuperacion.send_mail', side_effect=SMTPException('caído')), \
                self.assertLogs('infotrip.correo', 'ERROR') as registros:
            self.client.post('/api/v1/auth/recuperar/', {'email': self.usuario.email})
        self.assertNotIn('registro@example.com', ''.join(registros.output))

    def test_decision_de_moderacion(self):
        moderador = Usuario.objects.create_superuser('mod@example.com', 'Leo', 'Prueba', 'Prueba-segura-493!')
        municipio = Municipio.objects.create(nombre='M', slug='m', region=Region.objects.create(nombre='R', slug='r'))
        destino = Destino.objects.create(nombre='D', slug='d', municipio=municipio, descripcion='-',
                                         latitud=20, longitud=-103)
        aporte = Aporte.objects.create(autor=self.usuario, destino=destino, tipo='resena', texto='Bien',
                                       fecha_visita=timezone.localdate(), calificacion=5)
        with self.assertLogs('infotrip.moderacion', 'INFO') as registros:
            moderar(aporte, moderador, 'publicado', 'Revisado')
        self.assertIn(f'Aporte {aporte.pk}: pendiente → publicado por el moderador {moderador.pk}', registros.output[0])


class DocumentacionApiTests(TestCase):
    def test_esquema_valido_y_sin_avisos(self):
        # --fail-on-warn hace fallar la prueba si una vista nueva queda sin documentar.
        with TemporaryDirectory() as carpeta:
            call_command('spectacular', '--validate', '--fail-on-warn', '--file', f'{carpeta}/esquema.yml')

    def test_esquema_publico_con_las_rutas_y_la_autenticacion(self):
        esquema = self.client.get('/api/v1/esquema/', HTTP_ACCEPT='application/json').json()
        for ruta in ['/api/v1/destinos/', '/api/v1/auth/login/', '/api/v1/colaboraciones/{id}/confirmar/',
                     '/api/v1/notificaciones/']:
            self.assertIn(ruta, esquema['paths'])
        self.assertEqual(esquema['components']['securitySchemes']['jwt']['scheme'], 'bearer')
        parametros = {p['name'] for p in esquema['paths']['/api/v1/destinos/']['get']['parameters']}
        self.assertLessEqual({'q', 'categoria', 'orden', 'datos_recientes'}, parametros)

    def test_swagger_compatible_con_la_csp(self):
        respuesta = self.client.get('/api/v1/docs/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotRegex(respuesta.content.decode(), r'<script(?![^>]*\ssrc=)[^>]*>')


class PaginasDeErrorTests(TestCase):
    def test_404_en_espanol_con_salida(self):
        respuesta = self.client.get('/no-existe/')
        self.assertEqual(respuesta.status_code, 404)
        self.assertContains(respuesta, 'No encontramos esta página', status_code=404)
        self.assertContains(respuesta, 'href="/destinos/"', status_code=404)

    def test_500_en_espanol_sin_depender_de_la_base_de_datos(self):
        self.client.raise_request_exception = False
        with patch('apps.core.views.connection.cursor', side_effect=OSError), \
                patch('apps.core.views.JsonResponse', side_effect=RuntimeError('fallo')), \
                self.assertLogs('django.request', 'ERROR'), self.assertLogs('infotrip.salud', 'ERROR'), \
                self.assertNumQueries(0):
            respuesta = self.client.get('/health/')
        self.assertEqual(respuesta.status_code, 500)
        self.assertContains(respuesta, 'Algo salió mal', status_code=500)


class LimiteGlobalTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_configurado_en_la_base(self):
        self.assertEqual(base.REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'],
                         ('apps.core.limites.LimiteAnonimo', 'apps.core.limites.LimiteUsuario'))

    def test_limita_y_tolera_la_caida_de_redis(self):
        limite = type('LimitePrueba', (LimiteAnonimo,), {'rate': '2/min'})
        with patch.object(RegionListView, 'throttle_classes', [limite]):
            self.assertEqual([self.client.get('/api/v1/regiones/').status_code for _ in range(3)], [200, 200, 429])
            cache.clear()
            with patch.object(limite, 'get_cache_key', side_effect=RedisError('caído')), \
                    self.assertLogs('infotrip.salud', 'ERROR'):
                self.assertEqual(self.client.get('/api/v1/regiones/').status_code, 200)
