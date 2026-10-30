"""Página para negocios: mide interés sin cobrar y sin crear una cuenta."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.metricas.models import Evento
from .models import InteresNegocio

URL = '/api/v1/negocios/interes/'
DATOS = {'negocio': 'Hostal Sierra', 'contacto': 'Eva', 'correo': 'eva@example.com', 'municipio': 'Tapalpa',
         'acepto': True}


class InteresTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_registra_sin_sesion_y_mide_sin_datos_personales(self):
        self.assertEqual(self.client.post(URL, DATOS, format='json').status_code, 201)
        interes = InteresNegocio.objects.get()
        self.assertEqual((interes.negocio, interes.correo, interes.atendido), ('Hostal Sierra', 'eva@example.com', False))
        evento = Evento.objects.get(nombre='interes_negocio')
        self.assertIsNone(evento.usuario)
        self.assertEqual(evento.destino, '')

    def test_campos_opcionales(self):
        datos = {**DATOS, 'telefono': '3312345678', 'mensaje': 'Quiero corregir mis horarios'}
        self.assertEqual(self.client.post(URL, datos, format='json').status_code, 201)
        self.assertEqual(InteresNegocio.objects.get().telefono, '3312345678')

    def test_exige_autorizacion_y_datos_validos(self):
        for cambio in [{'acepto': False}, {'correo': 'no-es-correo'}, {'negocio': ''}, {'contacto': ''},
                       {'municipio': ''}, {'negocio': 'x' * 151}, {'mensaje': 'x' * 1001}]:
            cache.clear()
            self.assertEqual(self.client.post(URL, {**DATOS, **cambio}, format='json').status_code, 400, cambio)
        sin_autorizar = {clave: valor for clave, valor in DATOS.items() if clave != 'acepto'}
        self.assertEqual(self.client.post(URL, sin_autorizar, format='json').status_code, 400)
        self.assertFalse(InteresNegocio.objects.exists())

    def test_el_campo_trampa_finge_exito_y_no_guarda(self):
        respuesta = self.client.post(URL, {**DATOS, 'sitio_web': 'http://spam.example'}, format='json')
        self.assertEqual(respuesta.status_code, 201)
        self.assertFalse(InteresNegocio.objects.exists())
        self.assertFalse(Evento.objects.filter(nombre='interes_negocio').exists())

    def test_limite_por_hora(self):
        for _ in range(10):
            self.assertEqual(self.client.post(URL, DATOS, format='json').status_code, 201)
        self.assertEqual(self.client.post(URL, DATOS, format='json').status_code, 429)

    def test_no_se_lee_por_la_api(self):
        self.assertEqual(self.client.get(URL).status_code, 405)


class PaginaTests(APITestCase):
    def test_dice_que_no_cobra_y_la_regla_de_confianza(self):
        pagina = self.client.get('/negocios/')
        self.assertContains(pagina, 'Hoy no vendemos nada ni cobramos')
        self.assertContains(pagina, 'jamás movería reseñas')
        self.assertContains(pagina, 'todavía no existen')
        self.assertContains(self.client.get('/sitemap.xml'), '/negocios/')
        self.assertContains(self.client.get('/terminos/'), 'Un pago nunca cambia')
        self.assertContains(self.client.get('/privacidad/'), 'Si nos escribes como negocio')

    @override_settings(ALLOWED_HOSTS=['testserver'])
    def test_el_personal_lo_ve_en_el_admin(self):
        InteresNegocio.objects.create(negocio='Hostal Sierra', contacto='Eva', correo='eva@example.com', municipio='Tapalpa')
        personal = get_user_model().objects.create_superuser('m@example.com', 'Mod', 'P', 'Prueba-segura-493!')
        self.client.force_login(personal)
        self.assertContains(self.client.get('/admin/comunidad/interesnegocio/'), 'Hostal Sierra')
