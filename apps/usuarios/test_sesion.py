"""S6: el refresh token vive en una cookie HttpOnly y las rutas que la usan exigen CSRF."""
import re
from datetime import timedelta

from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Usuario
from .sesion import COOKIE_REFRESH, RUTA_COOKIE
from .verificacion import ROTAR_REFRESH_CADA

REFRESCO = '/api/v1/auth/token/refresh/'
LOGOUT = '/api/v1/auth/logout/'


class SesionBase(APITestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user('sesion@example.com', 'Ana', 'Prueba', 'Prueba-segura-493!',
                                                   es_verificado=True)

    def token(self, antiguedad=timedelta(0)):
        refresh = RefreshToken.for_user(self.usuario)
        refresh['correo_confirmado'] = True
        refresh['iat'] = int((timezone.now() - antiguedad).timestamp())
        return refresh

    def con_cookie(self, refresh):
        self.client.cookies[COOKIE_REFRESH] = str(refresh)

    def assertCookieBorrada(self, respuesta):
        self.assertEqual(respuesta.cookies[COOKIE_REFRESH].value, '')
        self.assertEqual(respuesta.cookies[COOKIE_REFRESH]['path'], RUTA_COOKIE)


class CookieDeSesionTests(SesionBase):
    def iniciar_sesion(self):
        credenciales = {'email': self.usuario.email, 'password': 'Prueba-segura-493!'}
        desafio = self.client.post('/api/v1/auth/login/', credenciales).data['desafio']
        codigo = re.search(r'[0-9]{6}', mail.outbox[-1].body).group()
        return self.client.post('/api/v1/auth/verificar-codigo/', {'desafio': desafio, 'codigo': codigo})

    def test_el_login_entrega_el_refresh_solo_en_cookie_httponly(self):
        respuesta = self.iniciar_sesion()
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertNotIn('refresh', respuesta.data)
        self.assertNotIn('refresh', respuesta.content.decode())
        self.assertIn('access', respuesta.data)
        cookie = respuesta.cookies[COOKIE_REFRESH]
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Strict')
        self.assertEqual(cookie['path'], RUTA_COOKIE)
        self.assertEqual(cookie['max-age'], 7 * 24 * 3600)
        self.assertFalse(cookie['secure'])
        self.assertIn('csrftoken', respuesta.cookies)
        self.assertFalse(respuesta.cookies['csrftoken']['httponly'])

    @override_settings(REFRESH_COOKIE_SECURE=True)
    def test_cookie_segura_en_produccion(self):
        self.assertTrue(self.iniciar_sesion().cookies[COOKIE_REFRESH]['secure'])

    def test_el_token_en_el_cuerpo_no_sirve(self):
        respuesta = self.client.post(REFRESCO, {'refresh': str(self.token())})
        self.assertEqual(respuesta.status_code, 401)
        self.assertIn('sesión activa', respuesta.data['detail'])


class RefrescoTests(SesionBase):
    def test_entrega_un_access_valido_sin_rotar_el_mismo_dia(self):
        refresh = self.token()
        self.con_cookie(refresh)
        for _ in range(3):
            respuesta = self.client.post(REFRESCO)
            self.assertEqual(respuesta.status_code, 200)
            self.assertNotIn('refresh', respuesta.data)
            self.assertNotIn(COOKIE_REFRESH, respuesta.cookies)
        self.assertFalse(BlacklistedToken.objects.exists())
        self.assertEqual(OutstandingToken.objects.count(), 1)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + respuesta.data['access'])
        self.assertEqual(self.client.get('/api/v1/auth/perfil/').status_code, 200)

    def test_rota_una_vez_al_dia_y_revoca_el_anterior(self):
        anterior = self.token(antiguedad=ROTAR_REFRESH_CADA + timedelta(minutes=1))
        self.con_cookie(anterior)
        respuesta = self.client.post(REFRESCO)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('refresh', respuesta.data)
        nuevo = respuesta.cookies[COOKIE_REFRESH]
        self.assertTrue(nuevo['httponly'])
        self.assertNotEqual(nuevo.value, str(anterior))
        self.assertEqual(BlacklistedToken.objects.count(), 1)
        # El nuevo mantiene el correo confirmado y funciona; el anterior ya no.
        self.assertEqual(self.client.post(REFRESCO).status_code, 200)
        self.con_cookie(anterior)
        self.assertEqual(self.client.post(REFRESCO).status_code, 401)

    def test_token_invalido_borra_la_cookie(self):
        self.con_cookie('no-es-un-token')
        respuesta = self.client.post(REFRESCO)
        self.assertEqual(respuesta.status_code, 401)
        self.assertCookieBorrada(respuesta)

    def test_cuenta_sin_correo_confirmado(self):
        self.con_cookie(RefreshToken.for_user(self.usuario))
        respuesta = self.client.post(REFRESCO)
        self.assertEqual(respuesta.status_code, 401)
        self.assertCookieBorrada(respuesta)


class CsrfTests(SesionBase):
    def cliente(self):
        cliente = APIClient(enforce_csrf_checks=True)
        cliente.cookies[COOKIE_REFRESH] = str(self.token())
        return cliente

    def test_refresco_y_logout_rechazan_peticiones_sin_token_csrf(self):
        for ruta in (REFRESCO, LOGOUT):
            with self.subTest(ruta=ruta):
                respuesta = self.cliente().post(ruta)
                self.assertEqual(respuesta.status_code, 403)
                self.assertIn('CSRF', respuesta.data['detail'])
        self.assertFalse(BlacklistedToken.objects.exists())

    def test_con_token_csrf_funcionan(self):
        for ruta in (REFRESCO, LOGOUT):
            with self.subTest(ruta=ruta):
                cliente = self.cliente()
                cliente.cookies['csrftoken'] = 'a' * 32
                respuesta = cliente.post(ruta, HTTP_X_CSRFTOKEN='a' * 32)
                self.assertEqual(respuesta.status_code, 200, respuesta.data)


class LogoutTests(SesionBase):
    def test_revoca_el_token_y_borra_la_cookie_sin_pedir_access(self):
        refresh = self.token()
        self.con_cookie(refresh)
        respuesta = self.client.post(LOGOUT)
        self.assertEqual(respuesta.status_code, 200)
        self.assertCookieBorrada(respuesta)
        self.con_cookie(refresh)
        self.assertEqual(self.client.post(REFRESCO).status_code, 401)

    def test_sin_sesion_o_con_token_invalido(self):
        self.assertEqual(self.client.post(LOGOUT).status_code, 400)
        self.con_cookie('no-es-un-token')
        respuesta = self.client.post(LOGOUT)
        self.assertEqual(respuesta.status_code, 400)
        self.assertCookieBorrada(respuesta)


class CambioDeContrasenaTests(SesionBase):
    def test_borra_la_cookie_y_revoca_la_sesion(self):
        refresh = self.token()
        self.con_cookie(refresh)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(refresh.access_token))
        respuesta = self.client.post('/api/v1/auth/cambiar-password/', {
            'password_actual': 'Prueba-segura-493!', 'password_nuevo': 'Nueva-clave-segura-817!',
            'password_nuevo2': 'Nueva-clave-segura-817!',
        })
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertCookieBorrada(respuesta)
        self.con_cookie(refresh)
        self.client.credentials()
        self.assertEqual(self.client.post(REFRESCO).status_code, 401)
