"""Visita comprobada: se guarda el resultado, nunca las coordenadas."""
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.core.geo import distancia_km
from apps.destinos.models import Destino, Municipio, Region
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario
from .cuenta import anonimizar_cuenta
from .models import Aporte, VisitaComprobada


class DistanciaTests(SimpleTestCase):
    def test_distancias_conocidas(self):
        self.assertAlmostEqual(distancia_km(20, -103, 21, -103), 111.19, places=1)
        self.assertEqual(distancia_km(20, -103, 20, -103), 0)
        # Un grado de longitud mide menos lejos del ecuador.
        self.assertAlmostEqual(distancia_km(20, -103, 20, -102), 104.5, delta=0.1)


class VisitaTests(APITestCase):
    def setUp(self):
        self.ana = Usuario.objects.create_user('ana@example.com', 'Ana', 'P', 'Prueba-segura-493!', es_verificado=True)
        self.leo = Usuario.objects.create_user('leo@example.com', 'Leo', 'P', 'Prueba-segura-493!', es_verificado=True)
        municipio = Municipio.objects.create(nombre='Tapalpa', slug='tapalpa',
                                             region=Region.objects.create(nombre='Sierra', slug='sierra'))
        self.lugar = Destino.objects.create(nombre='Tapalpa', slug='tapalpa', municipio=municipio, descripcion='-',
                                            latitud='19.945000', longitud='-103.757778')
        self.url = '/api/v1/destinos/tapalpa/visita/'
        self.cerca = {'latitud': 19.96, 'longitud': -103.75}
        self.client.force_authenticate(self.ana)

    def test_cerca_se_comprueba_y_no_guarda_coordenadas(self):
        respuesta = self.client.post(self.url, self.cerca, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data['comprobada'])
        visita = VisitaComprobada.objects.get()
        self.assertEqual((visita.autor, visita.destino, visita.fecha), (self.ana, self.lugar, timezone.localdate()))
        campos = {campo.name for campo in VisitaComprobada._meta.get_fields()}
        self.assertEqual(campos, {'id', 'autor', 'destino', 'fecha', 'creado'})

    def test_lejos_se_rechaza_sin_registrar_nada(self):
        respuesta = self.client.post(self.url, {'latitud': 20.67, 'longitud': -103.34}, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(VisitaComprobada.objects.exists())
        self.assertFalse(Evento.objects.filter(nombre='visita_comprobada').exists())

    def test_coordenadas_invalidas(self):
        for datos in [{}, {'latitud': 91, 'longitud': 0}, {'latitud': 0, 'longitud': 181}, {'latitud': 'x', 'longitud': 0}]:
            self.assertEqual(self.client.post(self.url, datos, format='json').status_code, 400, datos)

    def test_repetir_no_duplica_ni_vuelve_a_medir(self):
        self.client.post(self.url, self.cerca, format='json')
        self.client.post(self.url, self.cerca, format='json')
        self.assertEqual(VisitaComprobada.objects.count(), 1)
        self.assertEqual(Evento.objects.filter(nombre='visita_comprobada', destino='tapalpa').count(), 1)

    def test_consultar_el_estado(self):
        self.assertEqual(self.client.get(self.url).data, {'comprobada': False, 'fecha': None})
        self.client.post(self.url, self.cerca, format='json')
        self.assertTrue(self.client.get(self.url).data['comprobada'])
        self.client.force_authenticate(self.leo)
        self.assertFalse(self.client.get(self.url).data['comprobada'])

    def test_requiere_sesion_y_destino_publicado(self):
        Destino.objects.filter(pk=self.lugar.pk).update(es_activo=False)
        self.assertEqual(self.client.post(self.url, self.cerca, format='json').status_code, 404)
        Destino.objects.filter(pk=self.lugar.pk).update(es_activo=True)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.url, self.cerca, format='json').status_code, 401)

    def aporte(self, autor):
        return Aporte.objects.create(destino=self.lugar, autor=autor, tipo='resena', texto='Bonito', calificacion=5,
                                     fecha_visita=timezone.localdate(), estado='publicado')

    def test_la_etiqueta_solo_aparece_en_quien_comprobo_este_lugar(self):
        self.aporte(self.ana)
        self.aporte(self.leo)
        otro = Destino.objects.create(nombre='Otro', slug='otro', municipio=self.lugar.municipio, descripcion='-',
                                      latitud='19', longitud='-103')
        VisitaComprobada.objects.create(autor=self.leo, destino=otro, fecha=timezone.localdate())
        self.assertNotContains(self.client.get('/destinos/tapalpa/'), 'class="visit-badge"')
        self.client.post(self.url, self.cerca, format='json')
        self.assertContains(self.client.get('/destinos/tapalpa/'), 'class="visit-badge"', count=1)
        datos = {a['autor_nombre']: a['visita_comprobada'] for a in self.client.get('/api/v1/destinos/tapalpa/aportes/').data['results']}
        self.assertEqual(datos, {'Ana': True, 'Leo': False})

    def test_la_ficha_explica_el_limite_de_la_etiqueta(self):
        ficha = self.client.get('/destinos/tapalpa/')
        self.assertContains(ficha, 'id="visit-check"')
        self.assertContains(ficha, 'No la guardamos')

    def test_al_eliminar_la_cuenta_se_borran_sus_visitas(self):
        self.client.post(self.url, self.cerca, format='json')
        anonimizar_cuenta(self.ana)
        self.assertFalse(VisitaComprobada.objects.exists())
