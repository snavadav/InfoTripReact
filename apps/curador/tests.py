from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.destinos.models import Lugar
from apps.usuarios.models import Usuario

from .models import EtiquetaLugar
from .muestreo import progreso, siguiente

CLAVE = 'Prueba-segura-493!'
URL = '/admin/etiquetar-lugares/'


def lugar(nombre, tipo='comer', subtipo='restaurant', **campos):
    return Lugar.objects.create(nombre=nombre, tipo=tipo, subtipo=subtipo, latitud='20.6', longitud='-103.3', **campos)


class MuestreoTests(TestCase):
    def setUp(self):
        self.ana = Usuario.objects.create_superuser('ana@example.com', 'Ana', 'P', CLAVE)
        self.leo = Usuario.objects.create_superuser('leo@example.com', 'Leo', 'P', CLAVE)
        self.comer = [lugar(f'Fonda {i}') for i in range(5)]
        self.hotel = lugar('Hotel Sierra', 'dormir', 'hotel')

    def test_alterna_tipos_para_que_no_dominen_los_restaurantes(self):
        primero = siguiente(self.ana)
        EtiquetaLugar.objects.create(lugar=primero, autor=self.ana, util=True)
        segundo = siguiente(self.ana)
        self.assertNotEqual(primero.tipo, segundo.tipo)

    def test_orden_fijo_igual_para_todos_y_sin_repetir_a_la_misma_persona(self):
        self.assertEqual(siguiente(self.ana), siguiente(self.leo))
        vistos = set()
        while (actual := siguiente(self.ana)) is not None:
            self.assertNotIn(actual.pk, vistos)
            vistos.add(actual.pk)
            EtiquetaLugar.objects.create(lugar=actual, autor=self.ana, util=None)
        self.assertEqual(len(vistos), 6)
        self.assertIsNotNone(siguiente(self.leo))

    def test_progreso_no_cuenta_los_no_se(self):
        EtiquetaLugar.objects.create(lugar=self.hotel, autor=self.ana, util=True)
        EtiquetaLugar.objects.create(lugar=self.comer[0], autor=self.ana, util=None)
        filas, total = progreso()
        self.assertEqual(total, 1)
        self.assertEqual({f['tipo']: f['total'] for f in filas}['Dormir'], 1)


class PantallaTests(TestCase):
    def setUp(self):
        self.lugar = lugar('Birria Don Chuy', direccion='Calle Juárez 10', denue_id='123')
        self.ana = Usuario.objects.create_superuser('ana@example.com', 'Ana', 'P', CLAVE)

    def test_muestra_el_lugar_y_guarda_la_respuesta_con_su_autor(self):
        self.client.force_login(self.ana)
        respuesta = self.client.get(URL)
        self.assertContains(respuesta, 'Birria Don Chuy')
        self.assertContains(respuesta, 'DENUE (INEGI)')
        self.assertRedirects(self.client.post(URL, {'lugar': self.lugar.pk, 'respuesta': 'no'}), f'{URL}?modo=muestra')
        etiqueta = EtiquetaLugar.objects.get()
        self.assertEqual((etiqueta.autor, etiqueta.util), (self.ana, False))
        self.assertContains(self.client.get(URL), 'Ya etiquetaste todos los lugares')

    def test_cambiar_de_opinion_no_duplica(self):
        self.client.force_login(self.ana)
        self.client.post(URL, {'lugar': self.lugar.pk, 'respuesta': 'no'})
        self.client.post(URL, {'lugar': self.lugar.pk, 'respuesta': 'si'})
        self.assertEqual(list(EtiquetaLugar.objects.values_list('util', flat=True)), [True])

    def test_respuesta_invalida_no_guarda(self):
        self.client.force_login(self.ana)
        self.client.post(URL, {'lugar': self.lugar.pk, 'respuesta': 'tal-vez'})
        self.assertFalse(EtiquetaLugar.objects.exists())

    def test_solo_personal_con_permiso(self):
        self.assertEqual(self.client.get(URL).status_code, 302)  # Sin sesión: al inicio de sesión del admin.
        sin_permiso = Usuario.objects.create_user('leo@example.com', 'Leo', 'P', CLAVE, es_staff=True)
        self.client.force_login(sin_permiso)
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.client.post(URL, {'lugar': self.lugar.pk, 'respuesta': 'si'}).status_code, 403)
        self.assertFalse(EtiquetaLugar.objects.exists())

    def test_el_grupo_de_moderacion_puede_etiquetar(self):
        leo = Usuario.objects.create_user('leo@example.com', 'Leo', 'P', CLAVE, es_verificado=True)
        call_command('crear_moderacion', agregar='leo@example.com', stdout=StringIO())
        self.client.force_login(leo)
        self.assertContains(self.client.get(URL), 'Birria Don Chuy')
