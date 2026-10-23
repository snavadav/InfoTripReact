"""Pruebas de los hallazgos de seguridad S1 (límites), S2 (correo) y S3 (registro)."""
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import Usuario


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
