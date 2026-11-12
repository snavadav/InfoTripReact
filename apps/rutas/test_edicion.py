"""Planeador 2.0, paso A3: ruta editable (fijar, quitar, descansar), alternativas y guardar como escapada."""
import json
from unittest import mock

from django.core.cache import cache
from django.utils.text import slugify
from rest_framework.test import APITestCase

from apps.comunidad.models import Viaje
from apps.destinos.models import Destino, Lugar
from apps.usuarios.models import Usuario
from .models import RutaCompartida
from .optimizador import Dia, Problema, Sitio, genetico, voraz
from .horarios import Horario
from .test_planeador import PlaneadorTests, proximo

URL = '/api/v1/rutas/planear/'
ALTERNATIVAS = '/api/v1/rutas/alternativas/'
GUARDAR = '/api/v1/rutas/guardar-escapada/'


class ConDatosDelPlaneador(APITestCase):
    """Los mismos destinos que PlaneadorTests (Guadalajara, sábado), sin repetir sus pruebas."""
    setUp = PlaneadorTests.setUp
    peticion = PlaneadorTests.peticion
    nombres = PlaneadorTests.nombres

    def dia(self, respuesta, numero=0):
        return respuesta.json()['dias'][numero]


class OptimizadorConObligatoriosTests(APITestCase):
    def test_descanso_sin_manejar_y_fijado_en_su_dia(self):
        abierto = Horario({d: [(8 * 60, 20 * 60)] for d in range(7)})
        cerca = [Sitio(i, (20.67 + i / 1000, -103.34), 1.0, 60, abierto) for i in range(4)]
        descanso = Sitio('descanso', (0, 0), 0, 45, Horario({d: [(12 * 60, 13 * 60 + 15)] for d in range(7)}),
                         dia=0, obligatorio=True, en_sitio=True, objetivo=12 * 60)
        fijo = cerca[0]
        fijo.obligatorio, fijo.dia = True, 1
        problema = Problema((20.67, -103.35), [Dia(5, 9 * 60, 18 * 60), Dia(6, 9 * 60, 18 * 60)],
                            cerca + [descanso])
        plan = genetico(problema, semilla=1)
        self.assertEqual(plan.obligatorios, 2)
        self.assertNotIn(0, [p.sitio for p in plan.dias[0]])
        self.assertIn(0, [p.sitio for p in plan.dias[1]])
        libre = next(p for p in plan.dias[0] if p.sitio == 4)
        # Se descansa donde se está: sin kilómetros ni manejo, dentro de su ventana.
        self.assertEqual((libre.km, libre.manejo), (0, 0))
        self.assertTrue(12 * 60 <= libre.inicio <= 12 * 60 + 30)
        # El híbrido nunca queda por debajo del voraz, ni con obligatorios.
        self.assertGreaterEqual(plan.aptitud, voraz(problema).aptitud)


class RutaEditableTests(ConDatosDelPlaneador):
    def test_quitados_nunca_entran(self):
        respuesta = self.peticion(excluidos=[self.cabanas.pk])
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('Hospicio Cabañas', self.nombres(respuesta))
        self.assertIn('Museo Regional', self.nombres(respuesta))

    def test_fijado_en_otro_dia(self):
        respuesta = self.peticion(dias=2, fijados=[{'destino': self.mirador.pk, 'dia': 1}])
        self.assertNotIn('Mirador Lejano', self.nombres(respuesta, 0))
        self.assertIn('Mirador Lejano', self.nombres(respuesta, 1))
        fijada = next(p for p in self.dia(respuesta, 1)['paradas'] if p['destino']['id'] == self.mirador.pk)
        self.assertTrue(fijada['fijado'])

    def test_fijado_fuera_de_la_zona_tambien_entra(self):
        lejano = Destino.objects.create(nombre='Peña del Frayle', slug='pena-del-frayle', municipio=self.gdl,
                                        descripcion='-', latitud=19.94, longitud=-103.76)
        lejano.categorias.add(self.miradores)
        self.assertNotIn('Peña del Frayle', self.nombres(self.peticion()))
        respuesta = self.peticion(fijados=[{'destino': lejano.pk, 'dia': 0, 'hora': '13:00'}])
        self.assertIn('Peña del Frayle', self.nombres(respuesta))

    def test_descanso_en_su_dia_y_aparte_de_las_paradas(self):
        respuesta = self.peticion(excluidos=[self.mirador.pk],
                                  descansos=[{'dia': 0, 'inicio': '12:00', 'duracion': 60}])
        dia = self.dia(respuesta)
        self.assertEqual(len(dia['descansos']), 1)
        libre = dia['descansos'][0]
        self.assertEqual(libre['duracion_min'], 60)
        self.assertTrue('11:30' <= libre['inicio'] <= '12:30', libre)
        self.assertTrue(0 <= libre['despues_de'] <= len(dia['paradas']))
        # El descanso no cuenta como sitio, ni va en el enlace de Google Maps.
        self.assertEqual(respuesta.json()['totales']['sitios'], len(dia['paradas']))
        self.assertEqual(dia['google_maps']['total'], len(dia['paradas']))

    def test_lo_que_no_cupo_se_avisa(self):
        respuesta = self.peticion(hora_inicio='09:00', hora_fin='12:00',
                                  fijados=[{'destino': self.cabanas.pk, 'dia': 0, 'hora': '17:30'},
                                           {'destino': self.regional.pk, 'dia': 0}],
                                  descansos=[{'dia': 0, 'inicio': '09:00', 'duracion': 240}])
        avisos = ' '.join(respuesta.json()['avisos'])
        self.assertIn('descanso(s) no cupieron', avisos)

    def test_ediciones_invalidas(self):
        casos = [
            {'fijados': [{'destino': self.mirador.pk, 'dia': 1}]},
            {'fijados': [{'destino': self.mirador.pk, 'dia': 0}], 'excluidos': [self.mirador.pk]},
            {'fijados': [{'destino': self.mirador.pk, 'dia': 0}, {'destino': self.mirador.pk, 'dia': 0}]},
            {'fijados': [{'destino': 999999, 'dia': 0}]},
            {'descansos': [{'dia': 0, 'inicio': '07:00', 'duracion': 30}]},
            {'descansos': [{'dia': 0, 'inicio': '12:00', 'duracion': 5}]},
            {'descansos': [{'dia': 0, 'inicio': '12:00', 'duracion': 30}] * 7},
        ]
        for cambio in casos:
            self.assertEqual(self.peticion(**cambio).status_code, 400, cambio)
        self.mirador.es_activo = False
        self.mirador.save()
        self.assertEqual(self.peticion(fijados=[{'destino': self.mirador.pk, 'dia': 0}]).status_code, 400)

    def test_la_ruta_compartida_guarda_la_edicion_y_muestra_el_descanso(self):
        datos = {'municipio': 'guadalajara', 'fecha': proximo(5).isoformat(), 'dias': 1, 'hora_inicio': '09:00',
                 'hora_fin': '19:00', 'intereses': ['ciudad-y-cultura'], 'excluidos': [self.mirador.pk],
                 'descansos': [{'dia': 0, 'inicio': '12:00', 'duracion': 45}]}
        self.assertEqual(self.client.post('/api/v1/rutas/compartidas/', datos, format='json').status_code, 201)
        ruta = RutaCompartida.objects.get()
        self.assertEqual(ruta.parametros['excluidos'], [self.mirador.pk])
        pagina = self.client.get(ruta.get_absolute_url())
        self.assertContains(pagina, 'Tiempo libre · 45 min')
        self.assertContains(self.client.get(f'{ruta.get_absolute_url()}calendario.ics'), 'BEGIN:VEVENT')


class AlternativasTests(ConDatosDelPlaneador):
    def hueco(self, **cambios):
        datos = {'fecha': proximo(5).isoformat(), 'desde': '11:30', 'hasta': '15:00',
                 'anterior': {'latitud': 20.6768, 'longitud': -103.3378},
                 'siguiente': {'latitud': 20.6774, 'longitud': -103.3459},
                 'intereses': ['ciudad-y-cultura'], 'excluidos': [self.cabanas.pk, self.regional.pk], **cambios}
        return self.client.post(ALTERNATIVAS, datos, format='json')

    def test_solo_lo_que_cabe_y_lo_afin_primero(self):
        afin = Destino.objects.create(nombre='Museo de la Ciudad', slug='museo-de-la-ciudad', municipio=self.gdl,
                                      descripcion='-', latitud=20.6780, longitud=-103.3440)
        afin.categorias.add(self.cabanas.categorias.first())
        respuesta = self.hueco()
        self.assertEqual(respuesta.status_code, 200)
        opciones = respuesta.json()['alternativas']
        nombres = [o['destino']['nombre'] for o in opciones]
        # El de los lunes está cerrado el sábado; los ya puestos en la ruta no se proponen.
        self.assertEqual(nombres, ['Museo de la Ciudad', 'Mirador Lejano'])
        for opcion in opciones:
            self.assertTrue('11:30' <= opcion['inicio'] and opcion['salida'] <= '15:00', opcion)
        self.assertFalse(opciones[1]['horario_confirmado'])
        self.assertLessEqual(len(self.hueco().json()['alternativas']), 3)

    def test_hueco_corto_sin_opciones(self):
        self.assertEqual(self.hueco(desde='11:30', hasta='11:50').json()['alternativas'], [])

    def test_ultimo_del_dia_sin_siguiente(self):
        respuesta = self.hueco(siguiente=None, desde='16:00', hasta='19:00')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('Mirador Lejano', [o['destino']['nombre'] for o in respuesta.json()['alternativas']])

    def test_peticiones_invalidas_y_limite(self):
        for cambio in [{'hasta': '11:00'}, {'anterior': {'latitud': 48.8, 'longitud': 2.3}}, {'intereses': []}]:
            self.assertEqual(self.hueco(**cambio).status_code, 400, cambio)
        cache.clear()
        with mock.patch('apps.rutas.views.alternativas', return_value=[]):
            codigos = [self.hueco().status_code for _ in range(21)]
        self.assertEqual(codigos[-1], 429)


class GuardarEscapadaTests(ConDatosDelPlaneador):
    def setUp(self):
        super().setUp()
        self.persona = Usuario.objects.create_user('viajera@example.com', 'Viajera', 'X', 'x')

    def guardar(self, **cambios):
        datos = {'municipio': 'guadalajara', 'fecha': proximo(5).isoformat(), 'dias': 2, 'hora_inicio': '11:00',
                 'hora_fin': '19:00', 'intereses': ['ciudad-y-cultura'], 'ritmo': 'tranquilo', 'personas': 2,
                 **cambios}
        return self.client.post(GUARDAR, {k: v for k, v in datos.items() if v is not None}, format='json')

    def test_requiere_sesion(self):
        self.assertIn(self.guardar().status_code, (401, 403))
        self.assertFalse(Viaje.objects.exists())

    def test_crea_la_escapada_con_agenda_y_presupuesto_conocido(self):
        self.client.force_authenticate(self.persona)
        respuesta = self.guardar(descansos=[{'dia': 1, 'inicio': '12:00', 'duracion': 30}])
        self.assertEqual(respuesta.status_code, 201)
        viaje = Viaje.objects.get(autor=self.persona)
        self.assertEqual(respuesta.json()['url'], f'/mis-viajes/?editar={viaje.pk}')
        self.assertEqual((viaje.fecha_inicio, (viaje.fecha_fin - viaje.fecha_inicio).days, viaje.personas),
                         (proximo(5), 1, 2))
        self.assertEqual(set(viaje.lugares.values_list('nombre', flat=True)),
                         {'Hospicio Cabañas', 'Museo Regional', 'Mirador Lejano'})
        titulos = [a['titulo'] for a in viaje.actividades]
        self.assertIn('Tiempo libre', titulos)
        self.assertIn('Comer en Fonda Doña Paz', titulos)
        self.assertIn('Dormir: Hotel Centro', titulos)
        # Con salida a las 11:00 y fin a las 19:00 la ruta no incluye desayuno ni cena.
        self.assertFalse([t for t in titulos if t.startswith(('Desayunar', 'Cenar'))])
        self.assertEqual(viaje.actividades, sorted(viaje.actividades, key=lambda a: (a['dia'], a['hora'] or '99:99')))
        # Presupuesto: solo entradas con precio publicado (sábado: 80 y 95 por persona), nada inventado.
        self.assertEqual(viaje.presupuesto, 2 * (80 + 95))
        self.assertEqual({g['concepto'] for g in viaje.gastos}, {'entradas'})
        # La escapada se abre en el editor de Mis viajes (la misma API la lee).
        self.assertEqual(self.client.get(f'/api/v1/mis-viajes/{viaje.pk}/').status_code, 200)

    def test_guarda_desayuno_y_cena_cuando_tocan(self):
        Lugar.objects.create(nombre='Cenaduría El Mirador', tipo='comer', subtipo='restaurant', latitud=20.7501,
                             longitud=-103.3001)
        self.client.force_authenticate(self.persona)
        self.assertEqual(self.guardar(dias=1, hora_inicio='09:00', hora_fin='21:00').status_code, 201)
        actividades = {a['titulo']: a for a in Viaje.objects.get(autor=self.persona).actividades}
        self.assertIn('Desayunar en Fonda Doña Paz', actividades)
        self.assertIn('Cenar en Cenaduría El Mirador', actividades)
        self.assertGreater(actividades['Cenar en Cenaduría El Mirador']['hora'],
                           actividades['Mirador Lejano']['hora'])

    def test_respeta_la_comida_elegida_si_era_una_opcion(self):
        mercado = Lugar.objects.create(nombre='Mercado Corona', tipo='comer', subtipo='marketplace', latitud=20.6769,
                                       longitud=-103.3392)
        lejos = Lugar.objects.create(nombre='Fonda Lejana', tipo='comer', subtipo='restaurant', latitud=21.5,
                                     longitud=-104.0)
        self.client.force_authenticate(self.persona)
        fonda = Lugar.objects.get(nombre='Fonda Doña Paz')
        self.guardar(comidas=[fonda.pk, lejos.pk])
        titulos = [a['titulo'] for a in Viaje.objects.get().actividades]
        # El mercado es la sugerida, pero la persona eligió la fonda; la lejana no era una opción.
        self.assertIn('Comer en Fonda Doña Paz', titulos)
        self.assertNotIn(f'Comer en {mercado.nombre}', titulos)
        self.assertNotIn('Comer en Fonda Lejana', titulos)

    def test_sin_coordenadas_de_quien_la_armo(self):
        self.client.force_authenticate(self.persona)
        respuesta = self.guardar(municipio=None, latitud=20.671234, longitud=-103.351234)
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        viaje = Viaje.objects.get()
        guardado = json.dumps([viaje.nombre, viaje.destino, viaje.notas, viaje.actividades, viaje.gastos])
        self.assertNotIn('20.671', guardado)
        self.assertNotIn('103.351', guardado)

    def test_destino_y_nombre_del_viaje(self):
        self.client.force_authenticate(self.persona)
        slug = slugify('Museo Regional')
        self.guardar(destino=f'destino:{slug}', modo='ida_vuelta')
        viaje = Viaje.objects.get()
        self.assertEqual((viaje.nombre, viaje.destino), ('Escapada a Museo Regional', 'Museo Regional'))
