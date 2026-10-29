"""Recomendación 8: "¿Sigue vigente?" renueva la vigencia de un dato práctico y ordena por frescura."""
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.destinos.models import Destino, Municipio, Region
from apps.usuarios.models import Usuario
from .models import Colaboracion, Confirmacion
from .selectors import ficha_practica


class VigenciaTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.autor = self.usuario('autor@example.com')
        self.viajero = self.usuario('viajero@example.com')
        region = Region.objects.create(nombre='Región', slug='region')
        self.municipio = Municipio.objects.create(nombre='Municipio', slug='municipio', region=region)
        self.destino = self.crear_destino('destino')
        self.dato = self.correccion(self.destino, dias=120)

    def usuario(self, email):
        return Usuario.objects.create_user(email, 'Ana', 'Prueba', 'Clave-segura-483!', es_verificado=True)

    def crear_destino(self, slug):
        return Destino.objects.create(nombre=slug.title(), slug=slug, municipio=self.municipio,
                                      descripcion='Lugar', latitud=20, longitud=-103)

    def correccion(self, destino, dias, **cambios):
        datos = dict(destino=destino, autor=self.autor, tipo='correccion', campo='horarios', texto='9 a 18 h',
                     fuente='Sitio oficial', fecha_dato=self.hoy - timedelta(days=dias), estado='publicado')
        return Colaboracion.objects.create(**{**datos, **cambios})

    def cliente(self, usuario):
        token = RefreshToken.for_user(usuario)
        token['correo_confirmado'] = True
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
        return cliente

    def confirmar(self, usuario, dato=None):
        return self.cliente(usuario).post(f'/api/v1/colaboraciones/{(dato or self.dato).pk}/confirmar/')

    def horarios(self):
        return ficha_practica(self.destino)[0]

    def test_confirmar_renueva_la_vigencia(self):
        self.assertEqual(self.horarios()['vigencia'], 'antigua')
        respuesta = self.confirmar(self.viajero)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['confirmaciones'], 1)
        campo = self.horarios()
        self.assertEqual((campo['vigencia'], campo['edad_dias'], campo['vigente_desde']), ('reciente', 0, self.hoy))
        self.assertEqual(campo['dato'].num_confirmaciones, 1)
        self.assertContains(self.client.get('/destinos/destino/'), 'Confirmado como vigente por 1 persona')

    def test_una_confirmacion_por_persona_que_actualiza_la_fecha(self):
        Confirmacion.objects.create(dato=self.dato, autor=self.viajero, fecha=self.hoy - timedelta(days=40))
        self.assertEqual(self.confirmar(self.viajero).data['confirmaciones'], 1)
        self.assertEqual(Confirmacion.objects.get().fecha, self.hoy)

    def test_restricciones(self):
        self.assertEqual(self.confirmar(self.autor).status_code, 400)
        nuevo = self.correccion(self.destino, dias=10, texto='10 a 17 h')
        self.assertEqual(self.confirmar(self.viajero).status_code, 400)
        self.assertEqual(self.confirmar(self.viajero, nuevo).status_code, 200)
        pendiente = self.correccion(self.destino, dias=1, campo='acceso', estado='pendiente')
        self.assertEqual(self.confirmar(self.viajero, pendiente).status_code, 404)
        pregunta = Colaboracion.objects.create(destino=self.destino, autor=self.autor, tipo='pregunta',
                                               texto='¿?', estado='publicado')
        self.assertEqual(self.confirmar(self.viajero, pregunta).status_code, 404)
        self.assertEqual(APIClient().post(f'/api/v1/colaboraciones/{nuevo.pk}/confirmar/').status_code, 401)

    def test_confirmacion_de_cuenta_inactiva_no_cuenta(self):
        Confirmacion.objects.create(dato=self.dato, autor=self.viajero, fecha=self.hoy)
        Usuario.objects.filter(pk=self.viajero.pk).update(es_activo=False)
        self.assertEqual(self.horarios()['vigencia'], 'antigua')
        self.assertEqual(self.horarios()['dato'].num_confirmaciones, None)

    def test_filtro_de_informacion_reciente_cuenta_las_confirmaciones(self):
        filtro = {'datos_recientes': 'on'}
        self.assertEqual(self.client.get('/destinos/', filtro).context['pagina'].paginator.count, 0)
        self.confirmar(self.viajero)
        self.assertEqual(self.client.get('/destinos/', filtro).context['pagina'].paginator.count, 1)
