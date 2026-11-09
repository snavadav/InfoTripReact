"""Lo que llega a Sentry cuando falla una petición no debe llevar datos personales."""
import json
import logging
from unittest import mock

import sentry_sdk
from django.core.handlers.wsgi import WSGIHandler
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import path
from sentry_sdk.transport import Transport

from infotrip.monitoreo import iniciar, limpiar_evento

CORREO = 'persona.real@ejemplo.mx'
TOKEN = 'token-de-baja-que-identifica-a-una-cuenta'


def vista_que_falla(request):
    token = request.GET.get('t')  # noqa: F841 (variable local con un dato de la cuenta: no debe enviarse)
    logging.getLogger('infotrip.prueba').warning('Aviso para %s', CORREO)
    raise ValueError(f'Llave duplicada: (email)=({CORREO})')


def vista_bien(request):
    return HttpResponse('ok')


urlpatterns = [path('falla/', vista_que_falla), path('bien/', vista_bien)]


class TransporteEnMemoria(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.eventos = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type in ('event', 'transaction'):
                self.eventos.append(item.payload.json)


@override_settings(ROOT_URLCONF='infotrip.test_monitoreo', DEBUG_PROPAGATE_EXCEPTIONS=False)
class MonitoreoSinDatosPersonalesTests(SimpleTestCase):
    def setUp(self):
        self.transporte = TransporteEnMemoria()
        iniciar('https://clave@sentry.ejemplo.mx/1', transport=self.transporte)
        self.addCleanup(sentry_sdk.init, dsn=None)

    def evento_de_peticion_que_falla(self):
        # Por el manejador WSGI real, como gunicorn: así Sentry ve la URL, las cabeceras y la IP.
        environ = RequestFactory().get(
            '/falla/', {'t': TOKEN}, HTTP_COOKIE='sessionid=secreta', HTTP_X_FORWARDED_FOR='203.0.113.9',
            REMOTE_ADDR='198.51.100.7',
        ).environ
        estados = []
        with self.assertLogs('django.request', 'ERROR'):
            b''.join(WSGIHandler()(environ, lambda estado, cabeceras, *_: estados.append(estado)))
        self.assertEqual(estados, ['500 Internal Server Error'])
        sentry_sdk.flush()
        self.assertEqual(len(self.transporte.eventos), 1)
        return self.transporte.eventos[0]

    def test_el_error_llega_sin_datos_personales(self):
        evento = self.evento_de_peticion_que_falla()
        texto = json.dumps(evento)
        for dato in (CORREO, TOKEN, 'secreta', '203.0.113.9', '198.51.100.7'):
            self.assertNotIn(dato, texto)
        # Sigue sirviendo para depurar: tipo de error, ruta y línea del código.
        self.assertEqual(evento['exception']['values'][0]['type'], 'ValueError')
        self.assertIn('[oculto]', evento['exception']['values'][0]['value'])
        self.assertTrue(evento['request']['url'].endswith('/falla/'))
        marcos = evento['exception']['values'][0]['stacktrace']['frames']
        self.assertTrue(any(marco['function'] == 'vista_que_falla' for marco in marcos))
        self.assertTrue(all('vars' not in marco for marco in marcos))
        self.assertNotIn('user', evento)

    def test_sin_dsn_no_se_inicia(self):
        with mock.patch('sentry_sdk.init') as init:
            iniciar('')
        init.assert_not_called()

    def test_limpiar_evento_tapa_correos_en_todo_el_evento(self):
        evento = limpiar_evento({
            'message': f'Fallo al enviar a {CORREO}',
            'breadcrumbs': {'values': [{'message': f'correo a {CORREO}'}]},
            'request': {'url': f'https://infotrip.online/baja/?t={TOKEN}', 'query_string': f't={TOKEN}',
                        'data': {'correo': CORREO}},
            'user': {'email': CORREO},
        })
        self.assertNotIn(CORREO, json.dumps(evento))
        self.assertNotIn(TOKEN, json.dumps(evento))
        self.assertEqual(evento['request'], {'url': 'https://infotrip.online/baja/'})
