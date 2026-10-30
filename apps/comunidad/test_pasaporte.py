"""Pasaporte de Pueblos Mágicos: sellos por visita comprobada y tarjeta para compartir."""
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.destinos.models import Destino, Municipio, Region
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario
from .cuenta import anonimizar_cuenta
from .models import Notificacion, PasaporteCompartido, VisitaComprobada
from .selectors import PUEBLOS_MAGICOS


class ListaTests(SimpleTestCase):
    def test_son_doce_pueblos_sin_repetir(self):
        self.assertEqual(len(PUEBLOS_MAGICOS), 12)
        self.assertEqual(len(dict(PUEBLOS_MAGICOS)), 12)


class PasaporteBase(APITestCase):
    def setUp(self):
        self.ana = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.leo = Usuario.objects.create_user('leo@example.com', 'Leo', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa',
                                                  region=Region.objects.create(nombre='Sierra', slug='sierra'))
        self.tapalpa = self.destino('tapalpa')
        self.mazamitla = self.destino('mazamitla', latitud='19.916111', longitud='-103.020556')
        self.client.force_authenticate(self.ana)

    def destino(self, slug, latitud='19.945', longitud='-103.757778', **campos):
        return Destino.objects.create(nombre=slug.title(), slug=slug, municipio=self.municipio, descripcion='-',
                                      latitud=latitud, longitud=longitud, **campos)

    def visitar(self, destino=None, usuario=None):
        return VisitaComprobada.objects.create(autor=usuario or self.ana, destino=destino or self.tapalpa,
                                               fecha=timezone.localdate())


class MiPasaporteTests(PasaporteBase):
    def sellos(self):
        return {s['slug']: s for s in self.client.get('/api/v1/mi-pasaporte/').data['sellos']}

    def test_cuenta_solo_los_sellos_propios(self):
        self.visitar()
        self.visitar(self.mazamitla, self.leo)
        datos = self.client.get('/api/v1/mi-pasaporte/').data
        self.assertEqual((datos['total'], datos['de'], datos['enlace']), (1, 12, None))
        self.assertTrue(self.sellos()['tapalpa']['sello'])
        self.assertFalse(self.sellos()['mazamitla']['sello'])

    def test_pueblo_sin_ficha_no_esta_disponible(self):
        self.assertFalse(self.sellos()['cocula']['disponible'])
        self.assertTrue(self.sellos()['tapalpa']['disponible'])
        self.destino('cocula', es_activo=False)
        self.assertFalse(self.sellos()['cocula']['disponible'])

    def test_destino_que_no_es_pueblo_magico_no_da_sello(self):
        self.visitar(self.destino('guadalajara'))
        self.assertEqual(self.client.get('/api/v1/mi-pasaporte/').data['total'], 0)

    def test_ocultar_el_destino_retira_el_sello_de_la_cuenta(self):
        self.visitar()
        Destino.objects.filter(pk=self.tapalpa.pk).update(es_activo=False)
        self.assertEqual(self.client.get('/api/v1/mi-pasaporte/').data['total'], 0)

    def test_requiere_sesion(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/v1/mi-pasaporte/').status_code, 401)
        self.assertEqual(self.client.post('/api/v1/mi-pasaporte/compartir/').status_code, 401)


class GanarSelloTests(PasaporteBase):
    def comprobar(self, slug='tapalpa', latitud=19.95, longitud=-103.75):
        return self.client.post(f'/api/v1/destinos/{slug}/visita/', {'latitud': latitud, 'longitud': longitud},
                                format='json')

    def test_comprobar_en_un_pueblo_da_sello_avisa_y_mide(self):
        self.assertTrue(self.comprobar().data['sello'])
        aviso = Notificacion.objects.get(usuario=self.ana)
        self.assertIn('1 de 12', aviso.texto)
        self.assertEqual(aviso.enlace, '/pasaporte/')
        self.assertEqual(Evento.objects.filter(nombre='sello_obtenido', destino='tapalpa').count(), 1)

    def test_repetir_no_vuelve_a_avisar(self):
        self.comprobar()
        self.assertTrue(self.comprobar().data['sello'])
        self.assertEqual(Notificacion.objects.count(), 1)
        self.assertEqual(Evento.objects.filter(nombre='sello_obtenido').count(), 1)

    def test_otro_lugar_comprueba_sin_sello(self):
        self.destino('guadalajara')
        self.assertFalse(self.comprobar('guadalajara').data['sello'])
        self.assertFalse(Notificacion.objects.exists())
        self.assertFalse(Evento.objects.filter(nombre='sello_obtenido').exists())


class TarjetaTests(PasaporteBase):
    def enlace(self):
        return self.client.post('/api/v1/mi-pasaporte/compartir/').data['enlace']

    def test_la_tarjeta_muestra_nombre_y_sellos_sin_fechas_ni_correo(self):
        self.visitar()
        enlace = self.enlace()
        self.assertEqual(self.enlace(), enlace)
        self.client.force_authenticate(None)
        pagina = self.client.get(f'/pasaporte/{enlace}/')
        self.assertContains(pagina, 'Ana lleva 1 de 12')
        self.assertContains(pagina, 'noindex')
        self.assertContains(pagina, 'passport-stamp--done', count=1)
        self.assertNotContains(pagina, 'ana@example.com')
        self.assertNotContains(pagina, timezone.localdate().strftime('%d/%m/%Y'))

    def test_retirar_invalida_el_enlace(self):
        enlace = self.enlace()
        self.assertEqual(self.client.delete('/api/v1/mi-pasaporte/compartir/').status_code, 204)
        self.assertEqual(self.client.get(f'/pasaporte/{enlace}/').status_code, 404)

    def test_enlace_inexistente_o_de_cuenta_inactiva(self):
        self.assertEqual(self.client.get('/pasaporte/00000000-0000-0000-0000-000000000000/').status_code, 404)
        enlace = self.enlace()
        Usuario.objects.filter(pk=self.ana.pk).update(es_activo=False)
        self.assertEqual(self.client.get(f'/pasaporte/{enlace}/').status_code, 404)

    def test_eliminar_la_cuenta_borra_la_tarjeta(self):
        self.enlace()
        anonimizar_cuenta(self.ana)
        self.assertFalse(PasaporteCompartido.objects.exists())


class PaginasTests(PasaporteBase):
    def test_pagina_publica_con_los_doce_pueblos(self):
        self.client.force_authenticate(None)
        pagina = self.client.get('/pasaporte/')
        self.assertContains(pagina, 'class="passport-stamp"', count=12)
        self.assertContains(pagina, '/destinos/tapalpa/')
        self.assertContains(pagina, 'Aún sin ficha')
        self.assertContains(pagina, 'no está afiliado')
        self.assertContains(self.client.get('/sitemap.xml'), '/pasaporte/')

    def test_la_ficha_avisa_solo_en_los_pueblos(self):
        self.assertContains(self.client.get('/destinos/tapalpa/'), 'suma un sello')
        self.destino('guadalajara')
        self.assertNotContains(self.client.get('/destinos/guadalajara/'), 'suma un sello')
