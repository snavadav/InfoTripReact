"""Baja de cuenta y páginas legales."""
from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.destinos.models import Destino, Municipio, Region
from apps.usuarios.models import CodigoAcceso, Usuario
from apps.usuarios.sesion import COOKIE_REFRESH
from .models import Aporte, Colaboracion, Confirmacion, Decision, Favorito, Notificacion, Viaje

CLAVE = 'Prueba-segura-493!'
URL = '/api/v1/mi-cuenta/eliminar/'


def jpeg():
    salida = BytesIO()
    Image.new('RGB', (10, 10), 'blue').save(salida, 'JPEG')
    return ContentFile(salida.getvalue(), name='foto.jpg')


class BajaDeCuentaTests(TestCase):
    def setUp(self):
        carpeta = TemporaryDirectory()
        ajuste = override_settings(MEDIA_ROOT=carpeta.name)
        ajuste.enable()
        self.addCleanup(carpeta.cleanup)
        self.addCleanup(ajuste.disable)
        self.usuario = Usuario.objects.create_user('baja@example.com', 'Ana', 'Prueba', CLAVE, es_verificado=True,
                                                   ciudad_origen='Guadalajara', bio='Viajera')
        self.moderador = Usuario.objects.create_superuser('mod@example.com', 'Leo', 'Prueba', CLAVE)
        municipio = Municipio.objects.create(nombre='M', slug='m', region=Region.objects.create(nombre='R', slug='r'))
        self.destino = Destino.objects.create(nombre='D', slug='d', municipio=municipio, descripcion='-',
                                              latitud=20, longitud=-103)
        self.refresh = RefreshToken.for_user(self.usuario)
        self.refresh['correo_confirmado'] = True
        self.cliente = APIClient()
        self.cliente.credentials(HTTP_AUTHORIZATION='Bearer ' + str(self.refresh.access_token))

    def eliminar(self, password=CLAVE):
        return self.cliente.post(URL, {'password': password})

    def test_borra_lo_personal_y_conserva_el_historial_anonimo(self):
        self.usuario.foto_perfil.save('perfil.jpg', jpeg())
        foto = Aporte.objects.create(autor=self.usuario, destino=self.destino, tipo='foto', texto='Mi foto',
                                     fecha_visita=timezone.localdate(), estado='publicado', imagen=jpeg())
        Decision.objects.create(aporte=foto, moderador=self.moderador, estado_anterior='pendiente',
                                estado_nuevo='publicado', motivo='Revisado')
        dato = Colaboracion.objects.create(autor=self.usuario, destino=self.destino, tipo='correccion', campo='acceso',
                                           texto='Mi dato', fuente='Mi fuente', fecha_dato=timezone.localdate(),
                                           estado='publicado')
        Confirmacion.objects.create(dato=dato, autor=self.usuario, fecha=timezone.localdate())
        Favorito.objects.create(autor=self.usuario, destino=self.destino)
        Notificacion.objects.create(usuario=self.usuario, texto='Aviso')
        Viaje.objects.create(autor=self.usuario, nombre='V', destino='D', fecha_inicio='2026-01-01',
                             fecha_fin='2026-01-02', personas=1, presupuesto=1)
        rutas = [foto.imagen.path, self.usuario.foto_perfil.path]

        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.eliminar()

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.cookies[COOKIE_REFRESH].value, '')
        self.usuario.refresh_from_db()
        foto.refresh_from_db()
        dato.refresh_from_db()
        self.assertEqual((self.usuario.nombre, self.usuario.apellido), ('Cuenta', 'eliminada'))
        self.assertTrue(self.usuario.email.endswith('@infotrip.invalid'))
        self.assertEqual((self.usuario.ciudad_origen, self.usuario.bio), ('', ''))
        self.assertFalse(self.usuario.es_activo)
        self.assertFalse(self.usuario.has_usable_password())
        self.assertEqual((foto.estado, foto.imagen.name), ('retirado', ''))
        self.assertNotIn('Mi foto', foto.texto)
        self.assertEqual((dato.estado, dato.fuente), ('oculto', ''))
        self.assertNotIn('Mi dato', dato.texto)
        for modelo in (Favorito, Confirmacion, Viaje):
            self.assertFalse(modelo.objects.filter(autor=self.usuario).exists())
        self.assertFalse(Notificacion.objects.filter(usuario=self.usuario).exists())
        self.assertFalse(CodigoAcceso.objects.filter(usuario=self.usuario).exists())
        self.assertEqual(Decision.objects.count(), 1)
        for ruta in rutas:
            with self.assertRaises(FileNotFoundError):
                open(ruta)

    def test_la_sesion_deja_de_servir_y_el_correo_queda_libre(self):
        self.eliminar()
        self.assertEqual(self.cliente.get('/api/v1/auth/perfil/').status_code, 401)
        self.client.cookies[COOKIE_REFRESH] = str(self.refresh)
        self.assertEqual(self.client.post('/api/v1/auth/token/refresh/').status_code, 401)
        Usuario.objects.create_user('baja@example.com', 'Ana', 'Nueva', CLAVE)

    def test_exige_contrasena_correcta_y_sesion(self):
        self.assertEqual(self.eliminar('otra').status_code, 400)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.es_activo)
        self.assertEqual(APIClient().post(URL, {'password': CLAVE}).status_code, 401)

    def test_no_aplica_a_cuentas_de_administracion(self):
        token = RefreshToken.for_user(self.moderador)
        token['correo_confirmado'] = True
        Usuario.objects.filter(pk=self.moderador.pk).update(es_verificado=True)
        self.cliente.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
        self.assertEqual(self.eliminar().status_code, 400)


class PaginasLegalesTests(TestCase):
    @override_settings(CONTACTO_PRIVACIDAD='contacto@example.com')
    def test_privacidad_y_terminos_publicos_y_enlazados(self):
        self.assertContains(self.client.get('/privacidad/'), 'contacto@example.com')
        self.assertContains(self.client.get('/terminos/'), 'Términos de uso')
        pie = self.client.get('/destinos/')
        self.assertContains(pie, 'href="/privacidad/"')
        self.assertContains(pie, 'href="/terminos/"')
        self.assertContains(self.client.get('/registro/'), 'href="/privacidad/"')
