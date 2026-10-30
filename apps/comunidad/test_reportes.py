"""Reportes de datos prácticos, preguntas y respuestas ya publicados."""
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.destinos.models import Destino, Municipio, Region
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario
from .admin import ReporteAdmin, ReporteColaboracionAdmin
from .models import Aporte, Colaboracion, Decision, Reporte, ReporteColaboracion, RevisionColaboracion

CLAVE = 'Prueba-segura-493!'


class ReportesBase(TestCase):
    def setUp(self):
        self.autora = Usuario.objects.create_user('autora@example.com', 'Ana', 'P', CLAVE, es_verificado=True)
        self.otra = Usuario.objects.create_user('otra@example.com', 'Eva', 'P', CLAVE, es_verificado=True)
        self.moderador = Usuario.objects.create_superuser('mod@example.com', 'Mod', 'P', CLAVE)
        municipio = Municipio.objects.create(nombre='M', slug='m', region=Region.objects.create(nombre='R', slug='r'))
        self.destino = Destino.objects.create(nombre='D', slug='d', municipio=municipio, descripcion='-',
                                              latitud=20, longitud=-103)
        self.dato = self.colaboracion()

    def colaboracion(self, **cambios):
        datos = dict(destino=self.destino, autor=self.autora, tipo='correccion', campo='acceso', texto='Por el norte',
                     fuente='Visita', fecha_dato=timezone.localdate(), estado='publicado')
        return Colaboracion.objects.create(**{**datos, **cambios})

    def cliente(self, usuario):
        token = RefreshToken.for_user(usuario)
        token['correo_confirmado'] = True
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
        return cliente

    def reportar(self, usuario, item=None, motivo='Es falso'):
        return self.cliente(usuario).post(f'/api/v1/colaboraciones/{(item or self.dato).pk}/reportar/', {'motivo': motivo})

    def peticion(self):
        peticion = RequestFactory().post('/admin/')
        peticion.user = self.moderador
        return peticion


class ReportarColaboracionTests(ReportesBase):
    def test_se_reporta_una_vez_y_queda_en_las_metricas(self):
        self.assertEqual(self.reportar(self.otra).status_code, 201)
        self.assertEqual(self.reportar(self.otra).status_code, 400)
        reporte = ReporteColaboracion.objects.get()
        self.assertEqual((reporte.colaboracion, reporte.autor, reporte.motivo), (self.dato, self.otra, 'Es falso'))
        self.assertTrue(Evento.objects.filter(nombre='reporte_enviado', usuario=self.otra, destino='d').exists())

    def test_preguntas_y_respuestas_tambien(self):
        pregunta = self.colaboracion(tipo='pregunta', campo='', fuente='', fecha_dato=None, texto='¿Abre?')
        respuesta = self.colaboracion(tipo='respuesta', campo='', fuente='', fecha_dato=None, texto='Sí', pregunta=pregunta)
        self.assertEqual(self.reportar(self.otra, pregunta).status_code, 201)
        self.assertEqual(self.reportar(self.otra, respuesta).status_code, 201)

    def test_restricciones(self):
        self.assertEqual(self.reportar(self.autora).status_code, 400)
        self.assertEqual(self.reportar(self.otra, self.colaboracion(campo='pago', estado='pendiente')).status_code, 404)
        self.assertEqual(self.reportar(self.otra, motivo='').status_code, 400)
        self.assertEqual(APIClient().post(f'/api/v1/colaboraciones/{self.dato.pk}/reportar/', {'motivo': 'x'}).status_code, 401)

    def test_la_ficha_ofrece_reportar_cada_colaboracion_publicada(self):
        pregunta = self.colaboracion(tipo='pregunta', campo='', fuente='', fecha_dato=None, texto='¿Abre?')
        ficha = self.client.get('/destinos/d/')
        self.assertContains(ficha, f'data-url="/api/v1/colaboraciones/{self.dato.pk}/reportar/"')
        self.assertContains(ficha, f'data-url="/api/v1/colaboraciones/{pregunta.pk}/reportar/"')


class ResolverReportesTests(ReportesBase):
    def admin(self):
        return ReporteColaboracionAdmin(ReporteColaboracion, AdminSite())

    def test_resolver_oculta_el_contenido_y_guarda_historial_y_fecha(self):
        self.reportar(self.otra)
        self.admin().resolver_ocultando(self.peticion(), ReporteColaboracion.objects.all())
        self.dato.refresh_from_db()
        reporte = ReporteColaboracion.objects.get()
        self.assertEqual(self.dato.estado, 'oculto')
        self.assertTrue(reporte.resuelto)
        self.assertIsNotNone(reporte.resuelto_en)
        self.assertIn('Es falso', RevisionColaboracion.objects.get().motivo)

    def test_desestimar_conserva_el_contenido_y_deja_constancia(self):
        self.reportar(self.otra)
        self.admin().desestimar(self.peticion(), ReporteColaboracion.objects.all())
        self.dato.refresh_from_db()
        self.assertEqual(self.dato.estado, 'publicado')
        self.assertTrue(ReporteColaboracion.objects.get().resuelto)
        revision = RevisionColaboracion.objects.get()
        self.assertEqual((revision.estado_anterior, revision.estado_nuevo), ('publicado', 'publicado'))

    def test_los_reportes_de_aportes_siguen_funcionando_y_guardan_la_fecha(self):
        aporte = Aporte.objects.create(destino=self.destino, autor=self.autora, tipo='resena', texto='Bien', calificacion=4,
                                       fecha_visita=timezone.localdate(), estado='publicado')
        Reporte.objects.create(aporte=aporte, autor=self.otra, motivo='Falso')
        ReporteAdmin(Reporte, AdminSite()).desestimar(self.peticion(), Reporte.objects.all())
        self.assertIsNotNone(Reporte.objects.get().resuelto_en)
        self.assertEqual(Decision.objects.count(), 1)

    def test_aparecen_en_la_cola_y_el_panel_mide_el_tiempo(self):
        self.reportar(self.otra)
        self.client.force_login(self.moderador)
        secciones = {s['titulo']: s['total'] for s in self.client.get('/admin/moderacion/').context['secciones']}
        self.assertEqual(secciones['Reportes de información abiertos'], 1)
        self.assertIsNone(self.client.get('/admin/metricas/').context['horas_para_resolver'])
        self.admin().desestimar(self.peticion(), ReporteColaboracion.objects.all())
        self.assertIsNotNone(self.client.get('/admin/metricas/').context['horas_para_resolver'])
