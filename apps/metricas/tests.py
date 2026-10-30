from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.comunidad.models import Aporte, Colaboracion
from apps.comunidad.moderacion import moderar
from apps.destinos.models import Destino, Municipio, Region
from apps.usuarios.models import Usuario
from .models import Evento
from .views import EMBUDOS, embudos

URL = '/api/v1/eventos/'
CLAVE = 'Prueba-segura-493!'


class EventosDelNavegadorTests(TestCase):
    def enviar(self, **datos):
        return self.client.post(URL, datos, content_type='application/json')

    def test_guarda_solo_los_permitidos_y_sin_usuario(self):
        self.assertEqual(self.enviar(nombre='ficha_vista', destino='tequila').status_code, 204)
        evento = Evento.objects.get()
        self.assertEqual((evento.nombre, evento.destino, evento.usuario), ('ficha_vista', 'tequila', None))
        self.assertEqual(self.enviar(nombre='login_completado').status_code, 400)
        self.assertEqual(self.enviar(nombre='inventado').status_code, 400)
        self.assertEqual(self.enviar(nombre='ficha_vista', destino='no es un slug').status_code, 400)
        self.assertEqual(Evento.objects.count(), 1)


class EventosDelServidorTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user('a@example.com', 'Ana', 'P', CLAVE, es_verificado=True)
        self.otro = Usuario.objects.create_user('b@example.com', 'Leo', 'P', CLAVE, es_verificado=True)
        self.moderador = Usuario.objects.create_superuser('m@example.com', 'Mod', 'P', CLAVE)
        municipio = Municipio.objects.create(nombre='M', slug='m', region=Region.objects.create(nombre='R', slug='r'))
        self.destino = Destino.objects.create(nombre='D', slug='d', municipio=municipio, descripcion='-',
                                              latitud=20, longitud=-103)
        token = RefreshToken.for_user(self.usuario)
        token['correo_confirmado'] = True
        self.cliente = APIClient()
        self.cliente.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))

    def nombres(self):
        return list(Evento.objects.order_by('pk').values_list('nombre', flat=True))

    def test_acciones_registran_su_evento_con_la_cuenta(self):
        hoy = str(timezone.localdate())
        self.cliente.post('/api/v1/destinos/d/aportes/', {'tipo': 'resena', 'texto': 'Bien', 'fecha_visita': hoy,
                                                          'calificacion': 4})
        self.cliente.post('/api/v1/destinos/d/colaboraciones/', {'tipo': 'pregunta', 'texto': '¿Abre?'})
        self.cliente.put('/api/v1/favoritos/d/')
        self.cliente.put('/api/v1/favoritos/d/')
        self.cliente.post('/api/v1/mis-viajes/', {
            'nombre': 'V', 'destino': 'D', 'fecha_inicio': hoy, 'fecha_fin': hoy, 'personas': 1, 'presupuesto': '1',
            'gastos': []}, format='json')
        self.assertEqual(self.nombres(), ['aporte_enviado', 'dato_enviado', 'favorito_guardado', 'viaje_guardado'])
        self.assertTrue(all(e.usuario == self.usuario for e in Evento.objects.all()))
        self.assertEqual(Evento.objects.get(nombre='aporte_enviado').destino, 'd')

    def test_moderacion_confirmacion_y_reporte(self):
        aporte = Aporte.objects.create(autor=self.otro, destino=self.destino, tipo='resena', texto='Bien',
                                       fecha_visita=timezone.localdate(), calificacion=4)
        moderar(aporte, self.moderador, 'publicado', 'Revisado')
        moderar(aporte, self.moderador, 'oculto', 'Revisado')
        moderar(aporte, self.moderador, 'publicado', 'Revisado')
        self.assertEqual(Evento.objects.filter(nombre='aporte_publicado', usuario=self.otro).count(), 2)
        self.cliente.post(f'/api/v1/aportes/{aporte.pk}/reportar/', {'motivo': 'Falso'})
        dato = Colaboracion.objects.create(destino=self.destino, autor=self.otro, tipo='correccion', campo='acceso',
                                           texto='T', fuente='F', fecha_dato=timezone.localdate(), estado='publicado')
        self.cliente.post(f'/api/v1/colaboraciones/{dato.pk}/confirmar/')
        self.assertEqual(self.nombres()[-2:], ['reporte_enviado', 'dato_confirmado'])

    def test_eliminar_la_cuenta_desvincula_sus_eventos(self):
        Evento.objects.create(nombre='viaje_guardado', usuario=self.usuario)
        self.assertEqual(self.cliente.post('/api/v1/mi-cuenta/eliminar/', {'password': CLAVE}).status_code, 200)
        self.assertIsNone(Evento.objects.get().usuario)


class PanelTests(TestCase):
    def test_embudos_calculan_la_conversion(self):
        filas = embudos({'ficha_vista': 200, 'dato_practico_visto': 50})[0]['filas']
        self.assertEqual([f['conversion'] for f in filas[:3]], [None, 25, 0])
        self.assertEqual(len(EMBUDOS), 3)

    def test_panel_solo_para_personal_con_indicadores(self):
        self.assertEqual(self.client.get('/admin/metricas/').status_code, 302)
        Evento.objects.create(nombre='ficha_vista')
        self.client.force_login(Usuario.objects.create_superuser('m@example.com', 'Mod', 'P', CLAVE))
        respuesta = self.client.get('/admin/metricas/')
        self.assertContains(respuesta, 'Fichas con al menos 3 datos prácticos')
        self.assertEqual(next(e for e in respuesta.context['eventos'] if e['nombre'] == 'ficha_vista')['dias_7'], 1)
        self.assertContains(self.client.get('/admin/'), 'href="/admin/metricas/"')

    def test_retencion_y_fichas_utiles(self):
        ahora = timezone.now()
        usuarios = [Usuario.objects.create_user(f'u{i}@example.com', 'A', 'B', CLAVE) for i in range(2)]
        Usuario.objects.update(fecha_registro=ahora - timedelta(days=45))
        Evento.objects.create(nombre='login_completado', usuario=usuarios[0])
        municipio = Municipio.objects.create(nombre='M', slug='m', region=Region.objects.create(nombre='R', slug='r'))
        destino = Destino.objects.create(nombre='D', slug='d', municipio=municipio, descripcion='-',
                                         latitud=20, longitud=-103)
        Destino.objects.create(nombre='E', slug='e', municipio=municipio, descripcion='-', latitud=20, longitud=-103)
        for campo in ['acceso', 'pago', 'contacto']:
            Colaboracion.objects.create(destino=destino, autor=usuarios[0], tipo='correccion', campo=campo, texto='T',
                                        fuente='F', fecha_dato=timezone.localdate(), estado='publicado')
        moderador = Usuario.objects.create_superuser('m@example.com', 'Mod', 'P', CLAVE)
        self.client.force_login(moderador)
        contexto = self.client.get('/admin/metricas/').context
        self.assertEqual((contexto['retencion']['activos'], contexto['retencion']['cohorte']), (1, 2))
        self.assertEqual((contexto['fichas']['utiles'], contexto['fichas']['total']), (1, 2))

    def test_purga_solo_lo_antiguo(self):
        viejo = Evento.objects.create(nombre='ficha_vista')
        Evento.objects.filter(pk=viejo.pk).update(creado=timezone.now() - timedelta(days=400))
        nuevo = Evento.objects.create(nombre='ficha_vista')
        call_command('purgar_eventos', stdout=StringIO())
        self.assertEqual(list(Evento.objects.values_list('pk', flat=True)), [nuevo.pk])
