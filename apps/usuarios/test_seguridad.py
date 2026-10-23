"""Pruebas de los hallazgos de seguridad S1 (límites), S2 (correo), S3 (registro) y S7 (SMTP)."""
from smtplib import SMTPException
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase, APITransactionTestCase

from .models import CodigoAcceso, Usuario


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class LimitesLoginTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.usuario = Usuario.objects.create_user('limite@example.com', 'Ana', 'Viaje', 'Prueba-segura-493!')
        self.credenciales = {'email': self.usuario.email, 'password': 'Prueba-segura-493!'}

    def login(self, password='incorrecta', **extra):
        return self.client.post('/api/v1/auth/login/', dict(self.credenciales, password=password), **extra)

    def test_x_forwarded_for_falso_no_evade_limite_por_ip(self):
        for intento in range(10):
            self.login(email=f'otro{intento}@example.com', HTTP_X_FORWARDED_FOR=f'203.0.113.{intento}')
        respuesta = self.login(HTTP_X_FORWARDED_FOR='198.51.100.77')
        self.assertEqual(respuesta.status_code, 429)

    def test_bloqueo_por_cuenta_aunque_cambie_la_ip(self):
        for intento in range(5):
            self.assertEqual(self.login(REMOTE_ADDR=f'203.0.113.{intento}').status_code, 403)
        # Ni siquiera la contraseña correcta pasa mientras dura el bloqueo.
        respuesta = self.login(password=self.credenciales['password'], REMOTE_ADDR='198.51.100.9')
        self.assertEqual(respuesta.status_code, 429)

    def test_bloqueo_por_cuenta_no_distingue_mayusculas(self):
        for intento in range(5):
            self.login(email='LIMITE@Example.com', REMOTE_ADDR=f'203.0.113.{intento}')
        respuesta = self.login(password=self.credenciales['password'], REMOTE_ADDR='198.51.100.9')
        self.assertEqual(respuesta.status_code, 429)

    def test_login_correcto_reinicia_fallos(self):
        for intento in range(4):
            self.login(REMOTE_ADDR=f'203.0.113.{intento}')
        self.assertEqual(self.login(password=self.credenciales['password']).status_code, 200)
        for intento in range(4):
            self.assertEqual(self.login(REMOTE_ADDR=f'192.0.2.{intento}').status_code, 403)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CorreoSinMayusculasTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.datos = {'nombre': 'Ana', 'apellido': 'Viaje', 'password': 'Prueba-segura-493!',
                      'password2': 'Prueba-segura-493!'}

    def registrar(self, email, **extra):
        return self.client.post('/api/v1/auth/registro/', dict(self.datos, email=email), **extra)

    def test_registro_guarda_correo_en_minusculas(self):
        self.assertEqual(self.registrar('  Ana@Ejemplo.COM ').status_code, 201)
        self.assertEqual(Usuario.objects.get().email, 'ana@ejemplo.com')

    def test_mayusculas_no_crean_cuenta_duplicada(self):
        self.registrar('ana@ejemplo.com')
        self.registrar('ANA@ejemplo.com')
        self.assertEqual(Usuario.objects.count(), 1)

    def test_manager_y_restriccion_de_base_ignoran_mayusculas(self):
        from django.db import IntegrityError, transaction
        Usuario.objects.create_user('Mixto@Ejemplo.com', 'A', 'B', 'Prueba-segura-493!')
        self.assertTrue(Usuario.objects.filter(email='mixto@ejemplo.com').exists())
        # bulk_create no pasa por save(): la restricción de la base es la última barrera.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.bulk_create([Usuario(email='MIXTO@ejemplo.com', nombre='C', apellido='D')])

    def test_login_y_recuperacion_aceptan_mayusculas(self):
        Usuario.objects.create_user('ana@ejemplo.com', 'Ana', 'Viaje', 'Prueba-segura-493!')
        login = self.client.post('/api/v1/auth/login/', {'email': 'ANA@Ejemplo.com', 'password': 'Prueba-segura-493!'})
        self.assertEqual(login.status_code, 200, login.data)
        from django.core import mail
        self.client.post('/api/v1/auth/recuperar/', {'email': 'Ana@EJEMPLO.com'})
        self.assertEqual(mail.outbox[-1].to, ['ana@ejemplo.com'])


class RegistroGenericoTests(APITestCase):
    def setUp(self):
        cache.clear()
        Usuario.objects.create_user('existe@example.com', 'Ana', 'Viaje', 'Prueba-segura-493!')

    def registrar(self, email):
        return self.client.post('/api/v1/auth/registro/', {
            'email': email, 'nombre': 'Otro', 'apellido': 'Viajero',
            'password': 'Prueba-segura-493!', 'password2': 'Prueba-segura-493!'})

    def test_respuesta_no_revela_si_el_correo_existe(self):
        existente = self.registrar('existe@example.com')
        nuevo = self.registrar('nuevo@example.com')
        self.assertEqual(existente.status_code, nuevo.status_code)
        self.assertEqual(existente.data, nuevo.data)
        self.assertEqual(Usuario.objects.count(), 2)
        self.assertEqual(Usuario.objects.get(email='existe@example.com').nombre, 'Ana')

    def test_errores_de_validacion_siguen_informandose(self):
        respuesta = self.client.post('/api/v1/auth/registro/', {
            'email': 'otro@example.com', 'nombre': 'A', 'apellido': 'B', 'password': 'Prueba-segura-493!',
            'password2': 'distinta'})
        self.assertEqual(respuesta.status_code, 400)

    def test_limite_de_registros_por_ip(self):
        for intento in range(10):
            self.registrar(f'masivo{intento}@example.com')
        self.assertEqual(self.registrar('uno-mas@example.com').status_code, 429)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EnvioFueraDeTransaccionTests(APITransactionTestCase):
    """S7: el SMTP puede tardar hasta EMAIL_TIMEOUT; no debe retener el bloqueo del usuario."""

    def setUp(self):
        cache.clear()
        Usuario.objects.create_user('smtp@example.com', 'Ana', 'Viaje', 'Prueba-segura-493!')
        self.credenciales = {'email': 'smtp@example.com', 'password': 'Prueba-segura-493!'}

    def test_codigo_se_envia_sin_transaccion_abierta(self):
        en_transaccion = []
        def enviar(*args, **kwargs):
            en_transaccion.append(connection.in_atomic_block)
            return 1
        with patch('apps.usuarios.verificacion.send_mail', side_effect=enviar):
            self.assertEqual(self.client.post('/api/v1/auth/login/', self.credenciales).status_code, 200)
        self.assertEqual(en_transaccion, [False])
        self.assertTrue(CodigoAcceso.objects.exists())

    def test_fallo_de_envio_no_deja_desafio(self):
        with patch('apps.usuarios.verificacion.send_mail', side_effect=SMTPException('fallo')):
            self.assertEqual(self.client.post('/api/v1/auth/login/', self.credenciales).status_code, 503)
        self.assertFalse(CodigoAcceso.objects.exists())
