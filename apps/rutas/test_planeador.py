"""La API y la página del planeador, con destinos, horarios y precios en la base."""
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.test import APITestCase

from apps.comunidad.models import Colaboracion
from apps.destinos.models import Categoria, Destino, Lugar, Municipio, Region
from apps.metricas.models import Evento
from apps.usuarios.models import Usuario

URL = '/api/v1/rutas/planear/'


def proximo(dia_semana):
    """La próxima fecha (desde mañana) que cae en ese día de la semana; 0 = lunes."""
    fecha = timezone.localdate() + timedelta(days=1)
    return fecha + timedelta(days=(dia_semana - fecha.weekday()) % 7)


class PlaneadorTests(APITestCase):
    def setUp(self):
        cache.clear()
        region = Region.objects.create(nombre='Centro', slug='centro')
        self.gdl = Municipio.objects.create(nombre='Guadalajara', slug='guadalajara', region=region)
        cultura = Categoria.objects.create(nombre='Ciudad y cultura', slug='ciudad-y-cultura')
        self.miradores = Categoria.objects.create(nombre='Miradores', slug='miradores')
        self.equipo = Usuario.objects.create_user('equipo@example.com', 'Equipo', 'I', 'x')

        def destino(nombre, lat, lng, categoria, horarios='', precios=''):
            nuevo = Destino.objects.create(nombre=nombre, slug=slugify(nombre), municipio=self.gdl,
                                           descripcion='-', latitud=lat, longitud=lng)
            nuevo.categorias.add(categoria)
            for campo, texto in (('horarios', horarios), ('precios', precios)):
                if texto:
                    Colaboracion.objects.create(destino=nuevo, autor=self.equipo, tipo='correccion', campo=campo,
                                                texto=texto, fuente='https://sic.cultura.gob.mx/', estado='publicado',
                                                fecha_dato=timezone.localdate())
            return nuevo

        self.cabanas = destino('Hospicio Cabañas', 20.6768, -103.3378, cultura, 'Martes a domingo de 10 a 18 h',
                               'Entrada general $80. Martes entrada libre.')
        self.regional = destino('Museo Regional', 20.6774, -103.3459, cultura, 'Martes a domingo de 9 a 17 h',
                                'Entrada general $95')
        self.lunes = destino('Museo de Lunes', 20.6700, -103.3500, cultura, 'Lunes de 10 a 14 h', 'Entrada libre')
        self.mirador = destino('Mirador Lejano', 20.75, -103.30, self.miradores)
        Lugar.objects.create(nombre='Fonda Doña Paz', tipo='comer', subtipo='restaurant', latitud=20.6770,
                             longitud=-103.3400)
        Lugar.objects.create(nombre='Hotel Centro', tipo='dormir', subtipo='hotel', latitud=20.6765,
                             longitud=-103.3420)

    def peticion(self, **cambios):
        datos = {'municipio': 'guadalajara', 'fecha': proximo(5).isoformat(), 'dias': 1, 'hora_inicio': '09:00',
                 'hora_fin': '19:00', 'intereses': ['ciudad-y-cultura'], 'ritmo': 'normal', 'personas': 2,
                 'presupuesto': None, 'regresar': True, **cambios}
        return self.client.post(URL, datos, format='json')

    def nombres(self, respuesta, dia=0):
        return [p['destino']['nombre'] for p in respuesta.json()['dias'][dia]['paradas']]

    def test_itinerario_con_horarios_precios_y_comida(self):
        respuesta = self.peticion()
        self.assertEqual(respuesta.status_code, 200)
        plan = respuesta.json()
        # Sábado: el museo que solo abre en lunes no entra.
        self.assertEqual(set(self.nombres(respuesta)), {'Hospicio Cabañas', 'Museo Regional', 'Mirador Lejano'})
        paradas = {p['destino']['nombre']: p for p in plan['dias'][0]['paradas']}
        self.assertGreaterEqual(paradas['Hospicio Cabañas']['inicio'], '10:00')
        self.assertEqual(paradas['Museo Regional']['precio'], '95')
        self.assertTrue(paradas['Museo Regional']['horario_confirmado'])
        self.assertFalse(paradas['Mirador Lejano']['horario_confirmado'])
        self.assertEqual(plan['totales']['costo_entradas'], str(2 * 80 + 2 * 95))
        self.assertIn('sin horario publicado', ' '.join(plan['avisos']))
        self.assertIn('sin precio conocido', ' '.join(plan['avisos']))
        self.assertEqual(plan['origen']['nombre'], 'Guadalajara')
        self.assertEqual(plan['metodo']['nombre'], 'Algoritmo genético')
        self.assertGreaterEqual(plan['metodo']['puntaje'], plan['metodo']['voraz']['puntaje'])
        self.assertEqual(Evento.objects.filter(nombre='ruta_planeada').count(), 1)

    def test_lunes_y_entrada_libre_del_dia(self):
        respuesta = self.peticion(fecha=proximo(0).isoformat())
        self.assertIn('Museo de Lunes', self.nombres(respuesta))
        self.assertNotIn('Hospicio Cabañas', self.nombres(respuesta))
        martes = self.peticion(fecha=proximo(1).isoformat())
        paradas = {p['destino']['nombre']: p for p in martes.json()['dias'][0]['paradas']}
        self.assertEqual(paradas['Hospicio Cabañas']['precio'], '0')

    def test_presupuesto_para_entradas(self):
        respuesta = self.peticion(presupuesto='200', intereses=['ciudad-y-cultura'])
        self.assertLessEqual(int(respuesta.json()['totales']['costo_entradas']), 200)
        self.assertEqual(len([n for n in self.nombres(respuesta) if n in ('Hospicio Cabañas', 'Museo Regional')]), 1)

    def test_comida_y_dormir_cerca(self):
        respuesta = self.peticion(dias=2, hora_inicio='11:00', ritmo='tranquilo')
        dias = respuesta.json()['dias']
        comidas = [p['comida'] for dia in dias for p in dia['paradas'] if p['comida_despues']]
        self.assertTrue(comidas)
        self.assertEqual(comidas[0]['nombre'], 'Fonda Doña Paz')
        self.assertEqual(dias[0]['dormir']['nombre'], 'Hotel Centro')
        # Regresa al origen el último día: no se sugiere dónde dormir.
        self.assertIsNone(dias[-1]['dormir'])

    def test_desde_mi_ubicacion_sin_guardarla(self):
        datos = {'latitud': 20.6770, 'longitud': -103.3450, 'fecha': proximo(5).isoformat(), 'dias': 1,
                 'hora_inicio': '09:00', 'hora_fin': '19:00', 'intereses': ['ciudad-y-cultura']}
        respuesta = self.client.post(URL, datos, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['origen']['nombre'], 'Tu ubicación')
        # Sin municipio ni punto completo no hay de dónde salir.
        del datos['longitud']
        self.assertEqual(self.client.post(URL, datos, format='json').status_code, 400)
        # Fuera de México.
        self.assertEqual(self.client.post(URL, {**datos, 'latitud': 48.8, 'longitud': 2.3}, format='json').status_code,
                         400)

    def test_peticiones_invalidas(self):
        casos = [
            {'intereses': ['no-existe']}, {'intereses': []}, {'hora_fin': '10:00'}, {'dias': 4},
            {'fecha': (timezone.localdate() - timedelta(days=5)).isoformat()}, {'municipio': 'atlantida'},
            {'personas': 0}, {'ritmo': 'veloz'}, {'presupuesto': '-1'},
        ]
        for cambio in casos:
            self.assertEqual(self.peticion(**cambio).status_code, 400, cambio)

    def test_sin_sitios_que_quepan(self):
        respuesta = self.peticion(intereses=['miradores'], hora_inicio='20:00', hora_fin='23:30')
        self.assertEqual(respuesta.json()['totales']['sitios'], 0)
        self.assertIn('No encontramos sitios', ' '.join(respuesta.json()['avisos']))

    def test_misma_peticion_mismo_plan(self):
        self.assertEqual(self.nombres(self.peticion()), self.nombres(self.peticion()))

    def test_limite_de_peticiones(self):
        with mock.patch('apps.rutas.views.planear', return_value={'dias': []}):
            codigos = [self.peticion().status_code for _ in range(11)]
        self.assertEqual(codigos[-1], 429)

    def test_pagina_y_enlace_en_el_menu(self):
        pagina = self.client.get('/planeador/')
        self.assertContains(pagina, 'id="ruta-form"')
        self.assertContains(pagina, '<option value="guadalajara" selected>Guadalajara</option>', html=True)
        self.assertContains(pagina, 'value="miradores"')
        # Días como opciones grandes, con dos marcado; atajos de fecha con la fecha de mañana.
        self.assertContains(pagina, '<input type="radio" name="dias" value="2" checked>', html=True)
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.assertContains(pagina, f'data-fecha="{manana}"')
        self.assertContains(self.client.get('/destinos/'), 'href="/planeador/"')
        self.assertContains(self.client.get('/sitemap.xml'), '/planeador/')
