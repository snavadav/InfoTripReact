"""Registro de un paso y dispositivo recordado."""
import re

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import CodigoAcceso, Usuario
from .sesion import COOKIE_DISPOSITIVO, COOKIE_REFRESH

CLAVE = 'Prueba-segura-493!'
LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def codigo_del_correo():
    return re.search(r'[0-9]{6}', mail.outbox[-1].body).group()


@override_settings(EMAIL_BACKEND=LOCMEM)
class RegistroCortoTests(APITestCase):
    def setUp(self):
        cache.clear()

    def registrar(self, email='nueva@example.com', **extra):
        return self.client.post('/api/v1/auth/registro/', {'nombre': 'Ana', 'email': email, 'password': CLAVE, **extra})

    def test_con_nombre_correo_y_contrasena_llega_el_codigo_y_entra(self):
        respuesta = self.registrar()
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertTrue(respuesta.data['requiere_codigo'])
        self.assertEqual(mail.outbox[-1].to, ['nueva@example.com'])
        verificacion = self.client.post('/api/v1/auth/verificar-codigo/', {
            'desafio': respuesta.data['desafio'], 'codigo': codigo_del_correo()})
        self.assertEqual(verificacion.status_code, 200, verificacion.data)
        self.assertEqual(verificacion.data['usuario']['nombre_completo'], 'Ana')
        self.assertIn(COOKIE_REFRESH, verificacion.cookies)
        self.assertTrue(Usuario.objects.get(email='nueva@example.com').es_verificado)

    def test_contrasena_debil_y_confirmacion_distinta_se_rechazan(self):
        self.assertEqual(self.client.post('/api/v1/auth/registro/', {
            'nombre': 'Ana', 'email': 'a@example.com', 'password': '123'}).status_code, 400)
        self.assertEqual(self.registrar(email='b@example.com', password2='otra').status_code, 400)
        self.assertFalse(Usuario.objects.exists())

    def test_correo_existente_responde_igual_sin_tocar_la_cuenta_y_avisa_a_su_dueno(self):
        Usuario.objects.create_user('existe@example.com', 'Ana', 'P', CLAVE, es_verificado=True)
        existente = self.registrar(email='existe@example.com')
        nueva = self.registrar()
        self.assertEqual(existente.status_code, nueva.status_code)
        self.assertEqual(set(existente.data), set(nueva.data))
        self.assertEqual({k: v for k, v in existente.data.items() if k != 'desafio'},
                         {k: v for k, v in nueva.data.items() if k != 'desafio'})
        aviso = mail.outbox[0]
        self.assertEqual(aviso.to, ['existe@example.com'])
        self.assertIn('Ya tienes una cuenta', aviso.subject)
        self.assertFalse(re.search(r'\b[0-9]{6}\b', aviso.body))
        # El desafío falso no sirve con ningún código.
        falso = self.client.post('/api/v1/auth/verificar-codigo/', {'desafio': existente.data['desafio'],
                                                                    'codigo': '123456'})
        self.assertEqual(falso.status_code, 400)

    def test_el_aviso_de_correo_existente_no_se_repite_en_una_hora(self):
        Usuario.objects.create_user('existe@example.com', 'Ana', 'P', CLAVE)
        self.registrar(email='existe@example.com')
        self.registrar(email='existe@example.com')
        self.assertEqual(len(mail.outbox), 1)


@override_settings(EMAIL_BACKEND=LOCMEM)
class DispositivoRecordadoTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.usuario = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', CLAVE, es_verificado=True)
        self.credenciales = {'email': self.usuario.email, 'password': CLAVE}

    def entrar_con_codigo(self, cliente, recordar):
        desafio = cliente.post('/api/v1/auth/login/', self.credenciales).data['desafio']
        return cliente.post('/api/v1/auth/verificar-codigo/', {'desafio': desafio, 'codigo': codigo_del_correo(),
                                                               'recordar': recordar})

    def olvidar_ultimo_envio(self):
        # Hay 60 s de espera entre códigos; aquí solo interesa si se pide uno nuevo.
        cache.clear()
        CodigoAcceso.objects.all().delete()

    def test_por_defecto_no_se_recuerda(self):
        self.assertNotIn(COOKIE_DISPOSITIVO, self.entrar_con_codigo(self.client, False).cookies)

    def test_recordado_no_pide_codigo_pero_si_contrasena(self):
        respuesta = self.entrar_con_codigo(self.client, True)
        cookie = respuesta.cookies[COOKIE_DISPOSITIVO]
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Strict')
        self.assertEqual(cookie['max-age'], 30 * 24 * 3600)
        enviados = len(mail.outbox)
        cache.clear()
        directa = self.client.post('/api/v1/auth/login/', self.credenciales)
        self.assertEqual(directa.status_code, 200, directa.data)
        self.assertFalse(directa.data['requiere_codigo'])
        self.assertIn('access', directa.data)
        self.assertIn(COOKIE_REFRESH, directa.cookies)
        self.assertEqual(len(mail.outbox), enviados)
        self.assertEqual(self.client.post('/api/v1/auth/login/', {**self.credenciales, 'password': 'mal'}).status_code, 403)

    def test_otro_navegador_o_cookie_alterada_si_piden_codigo(self):
        valor = self.entrar_con_codigo(self.client, True).cookies[COOKIE_DISPOSITIVO].value
        self.olvidar_ultimo_envio()
        self.assertTrue(APIClient().post('/api/v1/auth/login/', self.credenciales).data['requiere_codigo'])
        self.olvidar_ultimo_envio()
        ajeno = APIClient()
        ajeno.cookies[COOKIE_DISPOSITIVO] = valor[:-1] + ('a' if valor[-1] != 'a' else 'b')
        self.assertTrue(ajeno.post('/api/v1/auth/login/', self.credenciales).data['requiere_codigo'])

    def test_cambiar_la_contrasena_o_el_correo_anula_el_recuerdo(self):
        self.entrar_con_codigo(self.client, True)
        self.olvidar_ultimo_envio()
        self.usuario.set_password('Nueva-clave-segura-817!')
        self.usuario.save()
        self.credenciales['password'] = 'Nueva-clave-segura-817!'
        self.assertTrue(self.client.post('/api/v1/auth/login/', self.credenciales).data['requiere_codigo'])

    def test_no_sirve_para_otra_cuenta(self):
        self.entrar_con_codigo(self.client, True)
        cache.clear()
        otra = Usuario.objects.create_user('otra@example.com', 'Eva', 'P', CLAVE, es_verificado=True)
        respuesta = self.client.post('/api/v1/auth/login/', {'email': otra.email, 'password': CLAVE})
        self.assertTrue(respuesta.data['requiere_codigo'])
