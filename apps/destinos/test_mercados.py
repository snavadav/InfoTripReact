"""Mercados públicos (Planeador 2.0, paso A2): de OpenStreetMap y de los puestos del DENUE. Nunca consulta la red."""
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase

from apps.usuarios.models import Usuario
from .admin import GRUPO_MODERACION, puede_recomendar
from .denue import mercados
from .models import Lugar, TIPO_DE_SUBTIPO
from .osm import CONSULTA_LUGARES, CONSULTA_MERCADOS, interpretar_lugares
from .test_denue import registro
from .test_osm import TAPALPA, TLAQUEPAQUE, lugar


def puesto(identificador, mercado='MERCADO MUNICIPAL', lat='19.9450', lng='-103.7570', clase='722519', **campos):
    return registro(identificador, nombre=f'PUESTO {identificador}', clase=clase,
                    Clase_actividad='Restaurantes que preparan otro tipo de alimentos para llevar', Latitud=lat,
                    Longitud=lng, tipo_corredor_industrial='MERCADO PUBLICO', nom_corredor_industrial=mercado, **campos)


class MercadosDelDenueTests(TestCase):
    def test_un_mercado_por_nombre_y_localidad_con_la_mediana_de_sus_puestos(self):
        lugares = mercados([puesto(5, lat='19.9450'), puesto(3, lat='19.9452'), puesto(9, lat='19.9454'),
                            puesto(7, mercado='CORONA', Ubicacion='GUADALAJARA,Guadalajara,JALISCO',
                                   lat='20.6790', lng='-103.3480')])
        por_nombre = {m['nombre']: m for m in lugares}
        self.assertEqual(set(por_nombre), {'Mercado Municipal', 'Mercado Corona'})
        tapalpa = por_nombre['Mercado Municipal']
        self.assertEqual((tapalpa['tipo'], tapalpa['subtipo'], tapalpa['municipio']), ('comer', 'marketplace', 'Tapalpa'))
        self.assertEqual(tapalpa['latitud'], 19.9452)
        # La clave sale del primer puesto, con "M" para no chocar con la de un negocio.
        self.assertEqual(tapalpa['denue_id'], 'M3')
        self.assertEqual(por_nombre['Mercado Corona']['municipio'], 'Guadalajara')

    def test_mismo_nombre_en_otra_localidad_es_otro_mercado(self):
        otra = puesto(2, Ubicacion='ATACCO,Tapalpa,JALISCO', lat='19.99')
        self.assertEqual(len(mercados([puesto(1), otra])), 2)

    def test_no_inventa_mercados(self):
        sin_mercado = registro(1, clase='722519', tipo_corredor_industrial='', nom_corredor_industrial='')
        plaza = registro(2, clase='722519', tipo_corredor_industrial='CENTRO Y PLAZA COMERCIAL',
                         nom_corredor_industrial='PLAZA SOL')
        farmacia = puesto(3, clase='464111')
        self.assertEqual(mercados([sin_mercado, plaza, farmacia, puesto(4, lat='')]), [])

    def test_un_puesto_lejano_no_mueve_el_mercado(self):
        lugares = mercados([puesto(1), puesto(2), puesto(3, lat='19.99')])
        self.assertEqual(len(lugares), 1)
        self.assertAlmostEqual(lugares[0]['latitud'], 19.945, places=4)


class ImportarMercadosDelDenueTests(TestCase):
    def importar(self, *registros, **opciones):
        salida = StringIO()
        with patch('apps.destinos.management.commands.importar_denue.descargar',
                   return_value=list(registros)) as descargar:
            call_command('importar_denue', stdout=salida, **opciones)
        return salida.getvalue(), descargar

    def test_la_importacion_normal_tambien_trae_los_mercados(self):
        texto, _ = self.importar(registro(1), puesto(2), puesto(3))
        self.assertTrue(Lugar.objects.filter(subtipo='marketplace', nombre='Mercado Municipal').exists())
        self.assertIn('Mercados públicos en la descarga: 1', texto)

    def test_solo_mercados_no_toca_lo_demas(self):
        hotel = Lugar.objects.create(nombre='Hotel Viejo', tipo='dormir', subtipo='hotel', latitud=19.9,
                                     longitud=-103.7, denue_id='99')
        _, descargar = self.importar(registro(1), puesto(2), solo_mercados=True, retirar_ausentes=True)
        # Solo pide la comida al DENUE.
        self.assertEqual(descargar.call_args.kwargs['actividades'], [('722', '72/722/0/0')])
        self.assertEqual(list(Lugar.objects.values_list('subtipo', flat=True).order_by('subtipo')),
                         ['hotel', 'marketplace'])
        hotel.refresh_from_db()
        self.assertTrue(hotel.es_activo)

    def test_repetir_actualiza_sin_duplicar(self):
        self.importar(puesto(2), solo_mercados=True)
        self.importar(puesto(2, mercado='MERCADO MUNICIPAL'), puesto(5), solo_mercados=True)
        self.assertEqual(Lugar.objects.filter(subtipo='marketplace').count(), 1)


class MercadosDeOsmTests(TestCase):
    def test_marketplace_es_un_lugar_para_comer(self):
        self.assertIn('marketplace', CONSULTA_LUGARES)
        self.assertIn('"amenity"="marketplace"', CONSULTA_MERCADOS)
        lugares, _ = interpretar_lugares({'elements': [
            lugar(1, 'Mercado Juárez', 19.9, -103.5, amenity='marketplace'), TAPALPA, TLAQUEPAQUE]})
        self.assertEqual((lugares[0]['tipo'], lugares[0]['subtipo']), ('comer', 'marketplace'))
        self.assertEqual(TIPO_DE_SUBTIPO['marketplace'], 'comer')

    def test_solo_mercados_no_retira_lo_demas(self):
        fonda = Lugar.objects.create(nombre='Fonda', tipo='comer', subtipo='restaurant', latitud=19.9,
                                     longitud=-103.5, osm_id='node/50')
        datos = {'elements': [lugar(1, 'Mercado Juárez', 19.9, -103.5, amenity='marketplace'),
                              lugar(2, 'Farmacia', 19.9, -103.5, amenity='pharmacy'), TAPALPA, TLAQUEPAQUE]}
        with patch('apps.destinos.management.commands.importar_lugares.descargar', return_value=datos) as descargar:
            call_command('importar_lugares', solo_mercados=True, retirar_ausentes=True, stdout=StringIO())
        self.assertEqual(descargar.call_args.args[0], CONSULTA_MERCADOS)
        self.assertEqual(list(Lugar.objects.filter(subtipo='marketplace').values_list('nombre', flat=True)),
                         ['Mercado Juárez'])
        self.assertFalse(Lugar.objects.filter(subtipo='pharmacy').exists())
        fonda.refresh_from_db()
        self.assertTrue(fonda.es_activo)


class RecomendadoPorElEquipoTests(TestCase):
    def test_por_omision_no_y_solo_el_equipo_lo_marca(self):
        lugar_ = Lugar.objects.create(nombre='Fonda', tipo='comer', subtipo='restaurant', latitud=19.9, longitud=-103.5)
        self.assertFalse(lugar_.recomendado_equipo)
        persona = Usuario.objects.create_user('persona@example.com', 'Persona', 'X', 'x')
        self.assertFalse(puede_recomendar(persona))
        persona.groups.add(Group.objects.create(name=GRUPO_MODERACION))
        self.assertTrue(puede_recomendar(Usuario.objects.get(pk=persona.pk)))
        equipo = Usuario.objects.create_user('equipo@example.com', 'Equipo', 'X', 'x', es_staff=True)
        self.assertTrue(puede_recomendar(equipo))
