"""Amigos: ciclo de solicitudes, sin duplicados, bloqueo, búsqueda solo por @usuario y matriz de visibilidad."""
import json
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.comunidad.cuenta import anonimizar_cuenta
from apps.comunidad.models import Notificacion, VisitaComprobada
from apps.destinos.models import Destino, Municipio, Region
from apps.usuarios.models import Usuario
from .models import Amistad, Bloqueo

CLAVE = 'Prueba-segura-493!'
API = '/api/v1/amigos/'


class Base(APITestCase):
    def setUp(self):
        cache.clear()
        self.ana = self.crear('ana@example.com', 'Ana', 'ana')
        self.leo = self.crear('leo@example.com', 'Leo', 'leo')
        self.eva = self.crear('eva@example.com', 'Eva', 'eva')

    def crear(self, email, nombre, username=None, **extra):
        return Usuario.objects.create_user(email, nombre, 'Prueba', CLAVE, es_verificado=True, username=username,
                                           **extra)

    def como(self, usuario):
        self.client.force_authenticate(Usuario.objects.get(pk=usuario.pk) if usuario else None)

    def solicitar(self, de, para):
        self.como(de)
        return self.client.post(API + 'solicitudes/', {'username': para}, format='json')

    def amigos(self, uno, otro):
        pk = self.solicitar(uno, otro.username).data['solicitud']
        self.como(otro)
        self.client.post(f'{API}solicitudes/{pk}/aceptar/')

    def pareja(self, uno, otro):
        return Amistad.objects.filter(de__in=[uno, otro], para__in=[uno, otro])


class SolicitudesTests(Base):
    def test_ciclo_completo_con_avisos(self):
        respuesta = self.solicitar(self.ana, '@Leo')
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data['relacion'], 'enviada')
        self.assertEqual(Notificacion.objects.get(usuario=self.leo).texto, '@ana te envió una solicitud de amistad.')
        self.como(self.leo)
        recibidas = self.client.get(API).data['recibidas']
        self.assertEqual([(p['username'], p['relacion']) for p in recibidas], [('ana', 'recibida')])
        aceptada = self.client.post(f"{API}solicitudes/{recibidas[0]['solicitud']}/aceptar/")
        self.assertEqual(aceptada.data['relacion'], 'amigos')
        self.assertEqual(Notificacion.objects.get(usuario=self.ana).texto, '@leo aceptó tu solicitud de amistad.')
        self.assertIsNotNone(self.pareja(self.ana, self.leo).get().respondido)
        self.como(self.ana)
        self.assertEqual([p['username'] for p in self.client.get(API).data['amigos']], ['leo'])
        self.assertEqual(self.client.delete(API + 'leo/').status_code, 204)
        self.assertFalse(self.pareja(self.ana, self.leo).exists())
        self.assertEqual(self.client.delete(API + 'leo/').status_code, 404)

    def test_un_solo_registro_por_pareja_y_la_solicitud_cruzada_acepta(self):
        self.solicitar(self.ana, 'leo')
        self.assertEqual(self.solicitar(self.ana, 'leo').status_code, 200)
        respuesta = self.solicitar(self.leo, 'ana')
        self.assertEqual(respuesta.data['relacion'], 'amigos')
        self.assertEqual(self.pareja(self.ana, self.leo).count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Amistad.objects.create(de=self.leo, para=self.ana)

    def test_sin_autoamistad(self):
        self.assertEqual(self.solicitar(self.ana, 'ana').status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Amistad.objects.create(de=self.ana, para=self.ana)

    def test_sin_nombre_de_usuario_no_se_envia_ni_se_recibe(self):
        sin_nombre = self.crear('x@example.com', 'Xochitl')
        self.assertEqual(self.solicitar(sin_nombre, 'leo').status_code, 400)
        self.assertEqual(self.solicitar(self.ana, 'xochitl').status_code, 404)

    def test_rechazar_no_avisa_y_espera_30_dias_para_reintentar(self):
        pk = self.solicitar(self.ana, 'leo').data['solicitud']
        self.como(self.leo)
        self.assertEqual(self.client.post(f'{API}solicitudes/{pk}/rechazar/').data['relacion'], 'ninguna')
        self.assertFalse(Notificacion.objects.filter(usuario=self.ana).exists())
        self.assertEqual(self.solicitar(self.ana, 'leo').status_code, 400)
        Amistad.objects.filter(pk=pk).update(respondido=timezone.now() - timedelta(days=31))
        self.assertEqual(self.solicitar(self.ana, 'leo').status_code, 201)
        self.assertEqual(self.pareja(self.ana, self.leo).get().estado, 'pendiente')

    def test_quien_rechazo_puede_enviar_despues(self):
        pk = self.solicitar(self.ana, 'leo').data['solicitud']
        self.como(self.leo)
        self.client.post(f'{API}solicitudes/{pk}/rechazar/')
        self.assertEqual(self.solicitar(self.leo, 'ana').status_code, 201)
        self.assertEqual(self.pareja(self.ana, self.leo).get().de, self.leo)

    def test_cancelar_solo_la_propia_y_pendiente(self):
        pk = self.solicitar(self.ana, 'leo').data['solicitud']
        self.como(self.leo)
        self.assertEqual(self.client.delete(f'{API}solicitudes/{pk}/').status_code, 404)
        self.como(self.eva)
        self.assertEqual(self.client.post(f'{API}solicitudes/{pk}/aceptar/').status_code, 404)
        self.como(self.ana)
        self.assertEqual(self.client.post(f'{API}solicitudes/{pk}/aceptar/').status_code, 404)
        self.assertEqual(self.client.delete(f'{API}solicitudes/{pk}/').status_code, 204)
        self.assertFalse(Amistad.objects.exists())

    def test_limite_de_solicitudes(self):
        with mock.patch('apps.amigos.views.SolicitudThrottle.rate', '1/hour'):
            self.assertEqual(self.solicitar(self.ana, 'leo').status_code, 201)
            self.assertEqual(self.solicitar(self.ana, 'eva').status_code, 429)

    def test_sin_sesion(self):
        self.como(None)
        self.assertEqual(self.client.get(API).status_code, 401)
        self.assertEqual(self.client.post(API + 'solicitudes/', {'username': 'leo'}).status_code, 401)

    def test_al_eliminar_la_cuenta_desaparecen_sus_amistades_y_bloqueos(self):
        self.amigos(self.ana, self.leo)
        Bloqueo.objects.create(de=self.ana, para=self.eva)
        anonimizar_cuenta(Usuario.objects.get(pk=self.ana.pk))
        self.assertFalse(Amistad.objects.exists())
        self.assertFalse(Bloqueo.objects.exists())


class BloqueoTests(Base):
    def test_bloquear_elimina_la_amistad_y_aisla(self):
        self.amigos(self.ana, self.leo)
        self.como(self.ana)
        self.assertEqual(self.client.post(API + 'bloqueos/', {'username': 'leo'}, format='json').status_code, 201)
        self.assertFalse(self.pareja(self.ana, self.leo).exists())
        self.assertEqual([p['username'] for p in self.client.get(API).data['bloqueados']], ['leo'])
        # Quien fue bloqueado no puede enviar, no la encuentra y no ve su perfil.
        self.assertEqual(self.solicitar(self.leo, 'ana').status_code, 404)
        self.como(self.leo)
        self.assertEqual(self.client.get(API + 'buscar/?q=an').data, [])
        self.assertEqual(self.client.get('/api/v1/personas/ana/').status_code, 404)
        # Quien bloquea tampoco envía sin desbloquear, pero sí ve el perfil para poder desbloquear.
        self.assertEqual(self.solicitar(self.ana, 'leo').status_code, 400)
        self.como(self.ana)
        self.assertEqual(self.client.get('/api/v1/personas/leo/').data['relacion'], 'bloqueado')
        self.assertEqual(self.client.delete(API + 'bloqueos/leo/').status_code, 204)
        self.assertEqual(self.solicitar(self.leo, 'ana').status_code, 201)

    def test_no_se_bloquea_a_si_misma_ni_duplica(self):
        self.como(self.ana)
        self.assertEqual(self.client.post(API + 'bloqueos/', {'username': 'ana'}, format='json').status_code, 400)
        for _ in range(2):
            self.client.post(API + 'bloqueos/', {'username': 'leo'}, format='json')
        self.assertEqual(Bloqueo.objects.count(), 1)


class BusquedaTests(Base):
    def buscar(self, texto, como=None):
        self.como(como or self.ana)
        return self.client.get(API + 'buscar/', {'q': texto})

    def test_solo_por_username_nunca_por_correo_ni_nombre(self):
        self.crear('zoe@example.com', 'Leonor', 'zoe')
        self.assertEqual([p['username'] for p in self.buscar('@le').data], ['leo'])
        self.assertEqual(self.buscar('leo@example.com').data, [])
        self.assertEqual(self.buscar('example').data, [])
        self.assertEqual(self.buscar('leonor').data, [])
        texto = json.dumps(self.buscar('le').data)
        self.assertNotIn('@example.com', texto)
        self.assertEqual(set(self.buscar('le').data[0]), {'username', 'nombre', 'relacion'})

    def test_exacta_primero_maximo_diez_y_sin_mi_cuenta(self):
        for numero in range(12):
            self.crear(f'l{numero}@example.com', 'L', f'leo{numero:02d}')
        resultados = [p['username'] for p in self.buscar('leo').data]
        self.assertEqual(len(resultados), 10)
        self.assertEqual(resultados[0], 'leo')
        self.assertEqual(self.buscar('ana').data, [])
        self.assertEqual(self.buscar('l').data, [])

    def test_privada_solo_la_encuentran_sus_amigos_e_inactivas_nadie(self):
        Usuario.objects.filter(pk=self.leo.pk).update(visibilidad='privado')
        self.crear('ida@example.com', 'Ida', 'leo.ida', es_activo=False)
        self.assertEqual(self.buscar('leo').data, [])
        self.amigos(self.leo, self.ana)
        self.assertEqual([(p['username'], p['relacion']) for p in self.buscar('leo').data], [('leo', 'amigos')])

    def test_indica_la_solicitud_pendiente(self):
        pk = self.solicitar(self.ana, 'leo').data['solicitud']
        self.assertEqual(self.buscar('leo').data[0]['solicitud'], pk)
        self.assertEqual(self.buscar('ana', self.leo).data[0]['relacion'], 'recibida')


class VisibilidadTests(Base):
    def setUp(self):
        super().setUp()
        region = Region.objects.create(nombre='Sierra', slug='sierra-de-jalisco')
        municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa', region=region)
        tapalpa = Destino.objects.create(nombre='Tapalpa', slug='tapalpa', municipio=municipio, descripcion='-',
                                         latitud='19.9', longitud='-103.7')
        VisitaComprobada.objects.create(autor=self.leo, destino=tapalpa, fecha='2026-03-14')

    def perfil(self, visitante, username='leo'):
        self.como(visitante)
        return self.client.get(f'/api/v1/personas/{username}/')

    def test_matriz_de_relacion_por_configuracion(self):
        sola = self.crear('sola@example.com', 'Sola', 'sola')
        self.amigos(self.ana, self.leo)
        self.solicitar(self.eva, 'leo')
        # Visitante → relación esperada.
        visitantes = {None: 'anonimo', sola: 'ninguna', self.eva: 'enviada', self.ana: 'amigos', self.leo: 'yo'}
        esperado = {
            'publico': {'anonimo': True, 'ninguna': True, 'enviada': True, 'amigos': True, 'yo': True},
            'amigos': {'anonimo': False, 'ninguna': False, 'enviada': False, 'amigos': True, 'yo': True},
            'privado': {'anonimo': False, 'ninguna': False, 'enviada': False, 'amigos': False, 'yo': True},
        }
        for visibilidad, por_relacion in esperado.items():
            Usuario.objects.filter(pk=self.leo.pk).update(visibilidad=visibilidad)
            for visitante, rel in visitantes.items():
                with self.subTest(visibilidad=visibilidad, relacion=rel):
                    datos = self.perfil(visitante).data
                    self.assertEqual(datos['relacion'], rel)
                    self.assertEqual(datos['detalle'], por_relacion[rel])
                    self.assertEqual(datos['nombre'], 'Leo Prueba')
                    self.assertEqual('lugares' in datos, por_relacion[rel])

    def test_sin_fechas_ni_correo(self):
        Usuario.objects.filter(pk=self.leo.pk).update(visibilidad='publico')
        datos = self.perfil(self.ana).data
        self.assertEqual(datos['lugares'], [{'slug': 'tapalpa', 'nombre': 'Tapalpa'}])
        self.assertEqual([s for s in datos['sellos'] if s['sello']], [{'slug': 'tapalpa', 'nombre': 'Tapalpa',
                                                                         'sello': True}])
        texto = json.dumps(datos, default=str)
        for prohibido in ('2026-03-14', '14/03', 'fecha', '@example.com'):
            self.assertNotIn(prohibido, texto)

    def test_lista_de_amigos_segun_preferencia_y_sin_privados(self):
        self.amigos(self.ana, self.leo)
        self.amigos(self.eva, self.leo)
        Usuario.objects.filter(pk=self.eva.pk).update(visibilidad='privado')
        self.assertEqual([p['username'] for p in self.perfil(self.ana).data['amigos']], ['ana'])
        Usuario.objects.filter(pk=self.leo.pk).update(mostrar_amigos=False)
        self.assertNotIn('amigos', self.perfil(self.ana).data)
        self.assertIn('amigos', self.perfil(self.leo).data)

    def test_cambiar_la_visibilidad_desde_el_perfil(self):
        self.como(self.leo)
        respuesta = self.client.patch('/api/v1/auth/perfil/', {'visibilidad': 'publico', 'mostrar_amigos': False},
                                      format='json')
        self.assertEqual((respuesta.data['visibilidad'], respuesta.data['mostrar_amigos']), ('publico', False))
        self.assertEqual(self.client.patch('/api/v1/auth/perfil/', {'visibilidad': 'todos'},
                                           format='json').status_code, 400)

    def test_inexistente_o_dada_de_baja(self):
        self.assertEqual(self.perfil(self.ana, 'nadie').status_code, 404)
        anonimizar_cuenta(Usuario.objects.get(pk=self.leo.pk))
        self.assertEqual(self.perfil(self.ana).status_code, 404)

    def test_paginas_sin_scripts_inline(self):
        for ruta, script in [('/amigos/', 'js/amigos.js'), ('/u/leo/', 'js/perfil-publico.js')]:
            pagina = self.client.get(ruta)
            self.assertContains(pagina, script)
            self.assertContains(pagina, 'noindex')
            self.assertNotRegex(pagina.content.decode(), r'<script(?![^>]*\bsrc=)[^>]*>')
        self.assertContains(self.client.get('/u/%3Cb%3E/'), 'data-username="&lt;b&gt;"')
