from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Usuario


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RecuperacionTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user=Usuario.objects.create_user('recuperar@example.com','Ana','Viaje','Clave-segura-483!',es_verificado=True)

    def test_solicitud_no_revela_cuenta_y_enlace_base_configurada(self):
        known=self.client.post('/api/v1/auth/recuperar/',{'email':self.user.email},HTTP_HOST='testserver')
        unknown=self.client.post('/api/v1/auth/recuperar/',{'email':'ausente@example.com'})
        self.assertEqual(known.status_code,200)
        self.assertEqual(known.data,unknown.data)
        self.assertEqual(len(mail.outbox),1)
        self.assertIn('http://127.0.0.1:8000/recuperar/',mail.outbox[0].body)
        self.assertNotIn('testserver',mail.outbox[0].body)

    def datos(self):
        return dict(uid=urlsafe_base64_encode(force_bytes(self.user.pk)),token=default_token_generator.make_token(self.user),password='Otra-clave-segura-493!',password2='Otra-clave-segura-493!')

    def test_restablecer_una_vez_revoca_access_y_refresh(self):
        refresh=RefreshToken.for_user(self.user);refresh['correo_confirmado']=True
        access=str(refresh.access_token)
        datos=self.datos()
        response=self.client.post('/api/v1/auth/restablecer/',datos)
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.client.post('/api/v1/auth/restablecer/',datos).status_code,400)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+access)
        self.assertEqual(self.client.get('/api/v1/auth/perfil/').status_code,401)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/v1/auth/token/refresh/',{'refresh':str(refresh)}).status_code,401)
        self.user.refresh_from_db();self.assertTrue(self.user.check_password(datos['password']))

    def test_enlace_vencido_y_malformado(self):
        datos=self.datos()
        with patch.object(default_token_generator,'_now',return_value=default_token_generator._now()+timedelta(hours=2)):
            self.assertEqual(self.client.post('/api/v1/auth/restablecer/',datos).status_code,400)
        datos['uid']='malformado'
        self.assertEqual(self.client.post('/api/v1/auth/restablecer/',datos).status_code,400)

    def test_clave_debil_y_confirmacion(self):
        datos=self.datos();datos.update(password='123',password2='123')
        self.assertEqual(self.client.post('/api/v1/auth/restablecer/',datos).status_code,400)
        datos=self.datos();datos['password2']='distinta'
        self.assertEqual(self.client.post('/api/v1/auth/restablecer/',datos).status_code,400)

    def test_perfil_no_permite_escalar_permisos(self):
        token=RefreshToken.for_user(self.user);token['correo_confirmado']=True
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+str(token.access_token))
        response=self.client.patch('/api/v1/auth/perfil/',{'nombre':'Nuevo','es_staff':True,'email':'otro@example.com'})
        self.assertEqual(response.status_code,200)
        self.user.refresh_from_db();self.assertFalse(self.user.es_staff);self.assertEqual(self.user.email,'recuperar@example.com')
        self.assertEqual(self.user.nombre,'Nuevo')

    def test_paginas_perfil_y_recuperacion(self):
        self.assertContains(self.client.get('/perfil/'),'Mis aportes')
        self.assertContains(self.client.get('/recuperar/'),'Recupera tu acceso')
