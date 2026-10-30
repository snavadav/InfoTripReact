import re
from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CodigoAcceso, Usuario
from .sesion import COOKIE_REFRESH


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class VerificacionCorreoTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.usuario = Usuario.objects.create_user('viajero@example.com', 'Ana', 'Viaje', 'Prueba-segura-493!')
        self.credenciales = {'email': self.usuario.email, 'password': 'Prueba-segura-493!'}

    def solicitar(self):
        response = self.client.post('/api/v1/auth/login/', self.credenciales)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        codigo = re.search(r'\b[0-9]{6}\b', mail.outbox[-1].body).group()
        self.assertEqual(mail.outbox[-1].to, [self.usuario.email])
        self.assertNotEqual(CodigoAcceso.objects.get().codigo_hash, codigo)
        return {'desafio': response.data['desafio'], 'codigo': codigo}

    def verificar(self, datos):
        return self.client.post('/api/v1/auth/verificar-codigo/', datos)

    def test_login_completo_y_refresh(self):
        datos = self.solicitar()
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.es_verificado)
        self.assertIsNone(self.usuario.ultimo_acceso)
        response = self.verificar(datos)
        self.assertEqual(response.status_code, 200, response.data)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.es_verificado)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])
        self.assertEqual(self.client.get('/api/v1/auth/perfil/').status_code, 200)
        self.client.credentials()
        renovacion = self.client.post('/api/v1/auth/token/refresh/')
        self.assertEqual(renovacion.status_code, 200, renovacion.data)
        self.assertIn('access', renovacion.data)

    def test_no_se_puede_reutilizar(self):
        datos = self.solicitar()
        self.assertEqual(self.verificar(datos).status_code, 200)
        self.assertEqual(self.verificar(datos).status_code, 400)

    def test_codigo_vencido(self):
        datos = self.solicitar()
        CodigoAcceso.objects.update(expira=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.verificar(datos).status_code, 400)

    def test_cinco_intentos_bloquean_incluso_codigo_correcto(self):
        datos = self.solicitar()
        incorrecto = dict(datos, codigo='111111' if datos['codigo'] != '111111' else '222222')
        for _ in range(5):
            self.assertEqual(self.verificar(incorrecto).status_code, 400)
        self.assertEqual(CodigoAcceso.objects.get().intentos, 5)
        self.assertEqual(self.verificar(datos).status_code, 400)

    def test_reenvio_espera_e_invalida_anterior(self):
        anterior = self.solicitar()
        self.assertEqual(self.client.post('/api/v1/auth/login/', self.credenciales).status_code, 429)
        self.assertEqual(len(mail.outbox), 1)
        CodigoAcceso.objects.update(enviado=timezone.now() - timedelta(seconds=61))
        nuevo = self.solicitar()
        self.assertNotEqual(anterior['desafio'], nuevo['desafio'])
        self.assertEqual(self.verificar(anterior).status_code, 400)
        self.assertEqual(self.verificar(nuevo).status_code, 200)

    def test_credenciales_incorrectas_y_usuario_inactivo(self):
        response = self.client.post('/api/v1/auth/login/', dict(self.credenciales, password='incorrecta'))
        self.assertIn(response.status_code, [400, 401, 403])
        self.usuario.es_activo = False
        self.usuario.save()
        self.assertIn(self.client.post('/api/v1/auth/login/', self.credenciales).status_code, [401, 403])
        self.assertFalse(CodigoAcceso.objects.exists())

    def test_error_envio_no_crea_desafio_ni_tokens(self):
        with patch('apps.usuarios.verificacion.send_mail', side_effect=SMTPException('fallo')):
            response = self.client.post('/api/v1/auth/login/', self.credenciales)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(CodigoAcceso.objects.exists())
        self.assertNotIn('access', response.data)

    def test_cambio_password_email_o_desactivacion_invalida_codigo(self):
        for campo, valor in [('password', 'nuevo-hash'), ('email', 'otro@example.com'), ('es_activo', False)]:
            with self.subTest(campo=campo):
                CodigoAcceso.objects.all().delete()
                self.usuario.password = Usuario.objects.get(pk=self.usuario.pk).password
                self.usuario.set_password(self.credenciales['password'])
                self.usuario.email = self.credenciales['email']
                self.usuario.es_activo = True
                self.usuario.save()
                datos = self.solicitar()
                Usuario.objects.filter(pk=self.usuario.pk).update(**{campo: valor})
                self.assertEqual(self.verificar(datos).status_code, 400)

    def test_registro_no_emite_tokens(self):
        response = self.client.post('/api/v1/auth/registro/', {
            'email': 'nuevo@example.com', 'nombre': 'Nuevo', 'apellido': 'Viajero',
            'password': 'Prueba-segura-493!', 'password2': 'Prueba-segura-493!',
        })
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn('tokens', response.data)
        self.assertFalse(Usuario.objects.get(email='nuevo@example.com').es_verificado)

    def test_tokens_anteriores_no_evaden_verificacion(self):
        self.usuario.es_verificado = True
        self.usuario.save()
        anterior = RefreshToken.for_user(self.usuario)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(anterior.access_token))
        self.assertEqual(self.client.get('/api/v1/auth/perfil/').status_code, 401)
        self.client.credentials()
        self.client.cookies[COOKIE_REFRESH] = str(anterior)
        response = self.client.post('/api/v1/auth/token/refresh/')
        self.assertEqual(response.status_code, 401)
        self.assertIn('terminó', response.data['detail'])

    def test_tambien_se_pide_codigo_a_usuario_ya_verificado(self):
        self.usuario.es_verificado = True
        self.usuario.save()
        self.solicitar()

    def test_formato_invalido(self):
        self.assertEqual(self.verificar({'desafio': 'no-valido', 'codigo': '123456'}).status_code, 400)
        datos = self.solicitar()
        self.assertEqual(self.verificar(dict(datos, codigo='abcdef')).status_code, 400)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='')
    def test_smtp_sin_configurar_informa_error(self):
        self.assertEqual(self.client.post('/api/v1/auth/login/', self.credenciales).status_code, 503)

    def test_limite_solicitudes_login(self):
        for _ in range(10):
            self.client.post('/api/v1/auth/login/', dict(self.credenciales, password='incorrecta'))
        self.assertEqual(self.client.post('/api/v1/auth/login/', self.credenciales).status_code, 429)
