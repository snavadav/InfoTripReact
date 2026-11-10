"""Nombre de usuario: formato, reservados, unicidad sin mayúsculas, sugerencia y límite de 30 días."""
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from . import nombres
from .models import Usuario

CLAVE = 'Prueba-segura-493!'


def crear(email='ana@example.com', nombre='Ana', apellido='Pérez', **extra):
    return Usuario.objects.create_user(email, nombre, apellido, CLAVE, es_verificado=True, **extra)


class FormatoTests(SimpleTestCase):
    def test_validos(self):
        for nombre in ['ana', 'ana.perez', 'ana_p', 'a1b', 'x' * 30, 'leo.2026']:
            self.assertEqual(nombres.problema(nombre), '', nombre)

    def test_invalidos(self):
        for nombre in ['ab', 'x' * 31, 'Ana', 'ana perez', 'ana-perez', 'ñandú', '.ana', 'ana.', 'an..a', '123',
                       'ana@x', '']:
            self.assertTrue(nombres.problema(nombre), nombre)

    def test_reservados_y_suplantacion(self):
        for nombre in ['admin', 'infotrip', 'moderacion', 'soporte', 'api', 'infotrip.oficial', 'el_admin',
                       'soporte_tecnico', 'i.n.f.o.t.r.i.p']:
            self.assertEqual(nombres.problema(nombre), 'Ese nombre está reservado.', nombre)

    def test_ofensivas_basicas_sin_falsos_positivos_comunes(self):
        for nombre in ['pendejo', 'el.puto', 'p3ndej0', 'la_chingada99']:
            self.assertEqual(nombres.problema(nombre), 'Elige un nombre respetuoso.', nombre)
        for nombre in ['computadora', 'maricela', 'disputa', 'ignacio.nacional']:
            self.assertEqual(nombres.problema(nombre), '', nombre)

    def test_la_lista_esta_versionada(self):
        self.assertIsInstance(nombres.VERSION_LISTAS, int)


class ModeloTests(TestCase):
    def test_unico_sin_distinguir_mayusculas_y_admite_varios_nulos(self):
        crear(username='ana')
        crear('leo@example.com', 'Leo')
        crear('eva@example.com', 'Eva')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.filter(email='leo@example.com').update(username='ANA')
        self.assertEqual(Usuario.objects.filter(username=None).count(), 2)

    def test_vacio_se_guarda_como_nulo_y_en_minusculas(self):
        ana = crear(username='')
        self.assertIsNone(ana.username)
        ana.username = 'Ana.P'
        ana.save()
        ana.refresh_from_db()
        self.assertEqual(ana.username, 'ana.p')

    def test_sugerencia_desde_el_nombre_y_libre(self):
        crear('otra@example.com', 'Otra', username='ana.perez')
        ana = crear()
        self.assertEqual(nombres.sugerir(ana), 'ana.perez2')
        self.assertIsNone(Usuario.objects.get(pk=ana.pk).username)
        self.assertEqual(nombres.sugerir(crear('x@example.com', 'Él', '')), 'viaje.el')


class ApiTests(APITestCase):
    url = '/api/v1/auth/username/'

    def setUp(self):
        cache.clear()
        self.ana = crear()
        self.client.force_authenticate(self.ana)

    def post(self, username):
        # Con el usuario recién leído, como en una petición real.
        self.client.force_authenticate(Usuario.objects.get(pk=self.ana.pk))
        return self.client.post(self.url, {'username': username}, format='json')

    def get(self, url):
        self.client.force_authenticate(Usuario.objects.get(pk=self.ana.pk))
        return self.client.get(url)

    def test_sin_nombre_propone_sin_guardar(self):
        datos = self.client.get(self.url).data
        self.assertEqual((datos['username'], datos['sugerencia'], datos['puede_cambiar']), (None, 'ana.perez', True))
        self.ana.refresh_from_db()
        self.assertIsNone(self.ana.username)

    def test_elegir_normaliza_y_aparece_en_el_perfil(self):
        respuesta = self.post('@Ana.Viaja')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['username'], 'ana.viaja')
        self.assertEqual(self.get('/api/v1/auth/perfil/').data['username'], 'ana.viaja')

    def test_ocupado_sin_distinguir_mayusculas(self):
        crear('leo@example.com', 'Leo', username='viajero.leo')
        respuesta = self.post('Viajero.Leo')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('otra persona', str(respuesta.data))

    def test_disponibilidad_en_vivo(self):
        crear('leo@example.com', 'Leo', username='leo')
        consulta = '/api/v1/auth/username/disponible/?username='
        self.assertEqual(self.client.get(consulta + 'LEO').data['disponible'], False)
        self.assertEqual(self.client.get(consulta + 'admin').data['motivo'], 'Ese nombre está reservado.')
        self.assertEqual(self.client.get(consulta + 'ana.libre').data['disponible'], True)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(consulta + 'leo').status_code, 401)

    def test_disponibilidad_tiene_limite(self):
        consulta = '/api/v1/auth/username/disponible/?username=ana'
        with mock.patch('apps.usuarios.views.DisponibleThrottle.rate', '2/min'):
            codigos = [self.client.get(consulta).status_code for _ in range(3)]
        self.assertEqual(codigos, [200, 200, 429])

    def test_un_cambio_cada_30_dias(self):
        self.assertEqual(self.post('ana.uno').status_code, 200)
        respuesta = self.post('ana.dos')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('30 días', str(respuesta.data))
        # Repetir el mismo nombre no cuenta como cambio.
        self.assertEqual(self.post('ana.uno').status_code, 200)
        Usuario.objects.filter(pk=self.ana.pk).update(username_cambiado=timezone.now() - timedelta(days=31))
        self.assertEqual(self.post('ana.dos').data['username'],
                         'ana.dos')
        self.assertFalse(self.get(self.url).data['puede_cambiar'])

    def test_al_eliminar_la_cuenta_se_libera(self):
        from apps.comunidad.cuenta import anonimizar_cuenta
        self.post('ana.uno')
        anonimizar_cuenta(self.ana)
        self.assertFalse(Usuario.objects.filter(username='ana.uno').exists())

    def test_paginas(self):
        self.assertContains(self.client.get('/elegir-usuario/'), 'js/elegir-usuario.js')
        self.assertContains(self.client.get('/robots.txt'), 'Disallow: /u/')
