"""Propuestas de lugares: nada se publica sin aprobación, se avisa de duplicados y se protege a quien propone."""
from django.core.cache import cache
from django.core.management import call_command
from io import StringIO
from unittest.mock import patch
from rest_framework.test import APITestCase

from apps.destinos.models import Lugar, Municipio, Region
from apps.destinos.test_osm import TAPALPA, lugar as nodo
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario
from .cuenta import anonimizar_cuenta
from .models import Notificacion, PropuestaLugar
from .moderacion import moderar
from .propuestas_lugar import MAXIMO_PENDIENTES, se_parecen

URL = '/api/v1/lugares/propuestas/'
DATOS = {'nombre': 'Fonda Nueva', 'subtipo': 'restaurant', 'latitud': '19.945000', 'longitud': '-103.757000'}


class Base(APITestCase):
    def setUp(self):
        cache.clear()
        self.ana = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.moderador = Usuario.objects.create_superuser('m@example.com', 'Mod', 'P', 'Prueba-segura-493!')
        self.tapalpa = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa',
                                                region=Region.objects.create(nombre='Sierra', slug='sierra'))
        self.client.force_authenticate(self.ana)

    def propuesta(self, **campos):
        return PropuestaLugar.objects.create(autor=self.ana, **{**DATOS, **campos})

    def existente(self, nombre='Fonda Vieja', latitud='19.945000', longitud='-103.757000', **campos):
        return Lugar.objects.create(nombre=nombre, tipo='comer', subtipo='restaurant', latitud=latitud, longitud=longitud,
                                    municipio=self.tapalpa, **campos)


class EnviarTests(Base):
    def test_queda_pendiente_y_no_aparece_en_el_mapa(self):
        respuesta = self.client.post(URL, DATOS, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data['estado'], 'pendiente')
        self.assertFalse(Lugar.objects.exists())
        self.assertEqual(Evento.objects.filter(nombre='lugar_propuesto').count(), 1)

    def test_requiere_sesion(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(URL, DATOS, format='json').status_code, 401)
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_valores_invalidos(self):
        for cambio in [{'nombre': ''}, {'nombre': '   '}, {'subtipo': 'inventado'}, {'latitud': '40'}, {'longitud': '-90'},
                       {'latitud': 'x'}, {'sitio_web': 'javascript:alert(1)'}, {'sitio_web': 'ftp://a.mx'}]:
            self.assertEqual(self.client.post(URL, {**DATOS, **cambio}, format='json').status_code, 400, cambio)
        self.assertFalse(PropuestaLugar.objects.exists())

    def test_no_se_puede_declarar_aprobada(self):
        respuesta = self.client.post(URL, {**DATOS, 'estado': 'publicado'}, format='json')
        self.assertEqual(respuesta.data['estado'], 'pendiente')

    def test_limite_de_pendientes(self):
        for numero in range(MAXIMO_PENDIENTES):
            self.propuesta(nombre=f'Lugar {numero}')
        self.assertEqual(self.client.post(URL, DATOS, format='json').status_code, 400)

    def test_solo_veo_las_mias(self):
        self.propuesta()
        otra = Usuario.objects.create_user('leo@example.com', 'Leo', 'P', 'x', es_verificado=True)
        PropuestaLugar.objects.create(autor=otra, **{**DATOS, 'nombre': 'Ajena'})
        self.assertEqual([p['nombre'] for p in self.client.get(URL).data['results']], ['Fonda Nueva'])


class DuplicadosTests(Base):
    def test_nombres_parecidos(self):
        for uno, otro in [('Fonda Doña Ana', 'Fonda Dona Ana'), ('OXXO', 'Oxxo Centro'), ('Hotel Sierra', 'Hotel Sierra.')]:
            self.assertTrue(se_parecen(uno, otro), (uno, otro))
        self.assertFalse(se_parecen('Fonda Ana', 'Farmacia Guadalajara'))
        self.assertTrue(se_parecen('博物館', '博物館'))
        self.assertFalse(se_parecen('博物館', 'Museo'))

    def test_si_hay_algo_parecido_pregunta_antes_de_guardar(self):
        sitio = self.existente(nombre='Fonda Nueva')
        respuesta = self.client.post(URL, DATOS, format='json')
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data['parecidos'], [{'id': sitio.pk, 'nombre': 'Fonda Nueva', 'url': f'/lugares/{sitio.pk}/'}])
        self.assertFalse(PropuestaLugar.objects.exists())
        confirmada = self.client.post(URL, {**DATOS, 'confirmar_distinto': True}, format='json')
        self.assertEqual(confirmada.status_code, 201)

    def test_mismo_nombre_lejos_u_otro_nombre_cerca_no_es_duplicado(self):
        self.existente(nombre='Fonda Nueva', latitud='19.960000')
        self.existente(nombre='Farmacia Guadalajara')
        self.assertEqual(self.client.post(URL, DATOS, format='json').status_code, 201)

    def test_lo_oculto_no_cuenta_como_duplicado(self):
        self.existente(nombre='Fonda Nueva', es_activo=False)
        self.assertEqual(self.client.post(URL, DATOS, format='json').status_code, 201)


class ModerarTests(Base):
    def test_aprobar_crea_el_lugar_con_tipo_y_municipio_cercano(self):
        self.existente(nombre='Otro', latitud='19.950000')
        propuesta = self.propuesta(subtipo='motel', telefono='33 1234', sitio_web='https://a.mx', nota='Nota interna')
        self.assertTrue(moderar(propuesta, self.moderador, 'publicado', 'Revisada'))
        sitio = propuesta.lugar
        self.assertEqual((sitio.nombre, sitio.tipo, sitio.subtipo, sitio.telefono, sitio.es_activo, sitio.osm_id),
                         ('Fonda Nueva', 'dormir', 'motel', '33 1234', True, None))
        self.assertEqual(sitio.municipio, self.tapalpa)
        self.assertTrue(sitio.protegido)
        aviso = Notificacion.objects.get(usuario=self.ana)
        self.assertIn('Fonda Nueva', aviso.texto)
        self.assertEqual(aviso.enlace, f'/lugares/{sitio.pk}/')
        self.assertEqual(Evento.objects.filter(nombre='lugar_aprobado').count(), 1)

    def test_rechazar_no_crea_nada_y_avisa(self):
        propuesta = self.propuesta()
        moderar(propuesta, self.moderador, 'oculto', 'No existe')
        self.assertFalse(Lugar.objects.exists())
        self.assertIn('no la publicamos', Notificacion.objects.get(usuario=self.ana).texto)

    def test_ocultar_despues_retira_el_lugar_y_volver_a_aprobar_no_duplica(self):
        propuesta = self.propuesta()
        moderar(propuesta, self.moderador, 'publicado', 'Revisada')
        moderar(propuesta, self.moderador, 'oculto', 'Era falso')
        propuesta.lugar.refresh_from_db()
        self.assertFalse(propuesta.lugar.es_activo)
        moderar(propuesta, self.moderador, 'publicado', 'Era real')
        propuesta.lugar.refresh_from_db()
        self.assertTrue(propuesta.lugar.es_activo)
        self.assertEqual(Lugar.objects.count(), 1)

    def test_sin_lugares_cerca_queda_sin_municipio(self):
        propuesta = self.propuesta()
        moderar(propuesta, self.moderador, 'publicado', 'Revisada')
        self.assertIsNone(propuesta.lugar.municipio)

    def test_la_ficha_lo_identifica_sin_nombrar_a_quien_lo_propuso(self):
        propuesta = self.propuesta()
        moderar(propuesta, self.moderador, 'publicado', 'Revisada')
        ficha = self.client.get(f'/lugares/{propuesta.lugar_id}/')
        self.assertContains(ficha, 'Agregado por la comunidad')
        self.assertNotContains(ficha, 'colaboradores de OpenStreetMap')
        self.assertNotContains(ficha, 'Ana')

    def test_importar_de_osm_no_toca_lo_propuesto(self):
        propuesta = self.propuesta()
        moderar(propuesta, self.moderador, 'publicado', 'Revisada')
        datos = {'elements': [nodo(1, 'Otra', 19.9, -103.5, amenity='bar'), TAPALPA]}
        with patch('apps.destinos.management.commands.importar_lugares.descargar', return_value=datos):
            call_command('importar_lugares', retirar_ausentes=True, stdout=StringIO())
        propuesta.lugar.refresh_from_db()
        self.assertTrue(propuesta.lugar.es_activo)


class AdminTests(Base):
    def test_cola_duplicados_y_aprobar(self):
        self.existente(nombre='Fonda Nueva')
        propuesta = self.propuesta()
        self.client.force_login(self.moderador)
        self.assertContains(self.client.get('/admin/moderacion/'), 'Lugares propuestos')
        self.assertContains(self.client.get(f'/admin/comunidad/propuestalugar/{propuesta.pk}/change/'), 'Fonda Nueva</a>')
        self.client.post('/admin/comunidad/propuestalugar/', {'action': 'publicar', '_selected_action': [propuesta.pk]})
        propuesta.refresh_from_db()
        self.assertEqual(propuesta.estado, 'publicado')
        self.assertIsNotNone(propuesta.lugar)


class BajaDeCuentaTests(Base):
    def test_lo_pendiente_no_se_publica_lo_aprobado_se_queda_y_la_nota_se_borra(self):
        pendiente = self.propuesta(nota='Es de mi primo')
        aprobada = self.propuesta(nombre='Aprobada', nota='Dato personal')
        moderar(aprobada, self.moderador, 'publicado', 'Revisada')
        anonimizar_cuenta(self.ana)
        pendiente.refresh_from_db()
        aprobada.refresh_from_db()
        self.assertEqual((pendiente.estado, pendiente.nota), ('oculto', ''))
        self.assertEqual((aprobada.estado, aprobada.nota), ('publicado', ''))
        self.assertTrue(aprobada.lugar.es_activo)


class PaginaTests(Base):
    def test_pagina_y_enlaces(self):
        pagina = self.client.get('/lugares/proponer/')
        self.assertContains(pagina, 'id="propuesta-form"')
        self.assertContains(pagina, 'noindex')
        self.assertContains(pagina, 'value="motel"')
        self.assertContains(self.client.get('/destinos/'), '/lugares/proponer/')
