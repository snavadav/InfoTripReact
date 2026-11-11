"""Planeador 2.0, paso A2: opciones de comida con lo local primero y las cadenas abajo."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.comunidad.models import ResenaLugar
from apps.destinos.models import Lugar
from apps.usuarios.models import Usuario
from .comida import VERSION_CADENAS, clase_de, es_cadena, opciones_comida

PUNTO = (20.6767, -103.3475)


def a_metros(metros):
    """Un punto a tantos metros al norte de PUNTO."""
    return PUNTO[0] + metros / 111_200, PUNTO[1]


def comer(nombre, subtipo, metros, **campos):
    lat, lng = a_metros(metros)
    return Lugar.objects.create(nombre=nombre, tipo='comer', subtipo=subtipo, latitud=round(lat, 6),
                                longitud=lng, **campos)


class OpcionesDeComidaTests(TestCase):
    def setUp(self):
        self.cadena = comer("McDonald's Centro", 'fast_food', 50)
        self.cafe = comer('Café La Esquina', 'cafe', 100)
        self.restaurante = comer('Restaurante El Patio', 'restaurant', 300)
        self.mercado = comer('Mercado Corona', 'marketplace', 900)
        self.bar = comer('Cantina La Fuente', 'bar', 20)

    def nombres(self, **opciones):
        return [o['nombre'] for o in opciones_comida(PUNTO, **opciones)]

    def test_mercado_primero_cadena_abajo_y_sin_bares(self):
        self.assertEqual(self.nombres(), ['Mercado Corona', 'Restaurante El Patio', 'Café La Esquina'])
        todas = self.nombres(cuantas=10)
        self.assertEqual(todas[-1], "McDonald's Centro")
        self.assertNotIn('Cantina La Fuente', todas)

    def test_la_cadena_baja_pero_no_desaparece(self):
        Lugar.objects.exclude(pk=self.cadena.pk).delete()
        opciones = opciones_comida(PUNTO)
        self.assertEqual([o['nombre'] for o in opciones], ["McDonald's Centro"])
        self.assertTrue(opciones[0]['cadena'])

    def test_fonda_por_su_nombre_vale_como_mercado(self):
        fonda = comer('Fonda Doña Paz', 'restaurant', 600)
        self.assertEqual(clase_de(fonda), 'fonda')
        self.assertEqual(self.nombres()[:2], ['Fonda Doña Paz', 'Mercado Corona'])

    def test_tarjeta_sin_datos_inventados(self):
        tarjeta = opciones_comida(PUNTO)[0]
        self.assertEqual((tarjeta['tipo'], tarjeta['distancia']), ('Mercado', '900 m'))
        self.assertIsNone(tarjeta['calificacion'])
        self.assertIsNone(tarjeta['precio'])
        self.assertFalse(tarjeta['recomendado_equipo'])
        self.assertTrue(tarjeta['url'].startswith('/lugares/'))

    def test_calificacion_y_precio_solo_de_resenas_publicadas(self):
        autores = [Usuario.objects.create_user(f'p{i}@example.com', f'P{i}', 'X', 'x') for i in range(3)]
        hace_un_mes = timezone.localdate() - timedelta(days=30)
        for i, autor in enumerate(autores):
            ResenaLugar.objects.create(lugar=self.restaurante, autor=autor, calificacion=5, texto='Muy rico.',
                                       fecha_visita=hace_un_mes, monto=Decimal(120 + 40 * i), estado='publicado')
        ResenaLugar.objects.create(lugar=self.cafe, autor=autores[0], calificacion=1, texto='Pendiente.',
                                   fecha_visita=hace_un_mes, monto=Decimal(10), estado='pendiente')
        por_nombre = {o['nombre']: o for o in opciones_comida(PUNTO)}
        restaurante = por_nombre['Restaurante El Patio']
        self.assertEqual((restaurante['calificacion'], restaurante['num_resenas']), (5.0, 3))
        self.assertEqual(restaurante['precio'], {'minimo': '120.00', 'maximo': '200.00', 'reportes': 3})
        # La reseña pendiente de moderación no cuenta.
        self.assertIsNone(por_nombre['Café La Esquina']['calificacion'])
        self.assertIsNone(por_nombre['Café La Esquina']['precio'])

    def test_recomendado_por_el_equipo_sube_y_lleva_distintivo(self):
        comer('Café del Jardín', 'cafe', 1500, recomendado_equipo=True)
        opciones = {o['nombre']: o for o in opciones_comida(PUNTO, cuantas=10)}
        nombres = list(opciones)
        # Más lejos, pero recomendado: va antes que la otra cafetería.
        self.assertLess(nombres.index('Café del Jardín'), nombres.index('Café La Esquina'))
        self.assertTrue(opciones['Café del Jardín']['recomendado_equipo'])

    def test_nada_cerca(self):
        self.assertEqual(opciones_comida((25.0, -100.0)), [])


class CadenasTests(TestCase):
    def test_lista_versionada(self):
        self.assertRegex(VERSION_CADENAS, r'^\d{4}-\d{2}-\d{2}$')
        for nombre in ["McDonald's Plaza del Sol", 'STARBUCKS COFFEE', 'Restaurante Toks Centro', 'KFC']:
            self.assertTrue(es_cadena(nombre), nombre)
        for nombre in ['Buffalo Wings Tapalpa', 'Fonda Doña Paz', 'Tortas Toño', 'Vipsa']:
            self.assertFalse(es_cadena(nombre), nombre)

