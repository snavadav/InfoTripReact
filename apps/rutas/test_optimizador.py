"""Reglas del itinerario y comparación del algoritmo genético con el método voraz."""
import random
from decimal import Decimal

from django.test import SimpleTestCase

from .horarios import Horario, Precio
from .optimizador import (
    COMIDA_MIN, Dia, Parametros, Problema, Sitio, _cruce_ox, decodificar, distancia_km, genetico, minutos_de_manejo,
    voraz,
)

ORIGEN = (20.6767, -103.3475)
SABADO = 5


def h(hora, minuto=0):
    return hora * 60 + minuto


def abierto(desde=h(9), hasta=h(18), dias=range(7)):
    return Horario({d: [(desde, hasta)] for d in dias})


def cerca(km_norte):
    """Un punto a tantos kilómetros al norte del origen, en línea recta."""
    return (ORIGEN[0] + km_norte / 111.2, ORIGEN[1])


def sitio(clave, km=1, puntaje=1.0, duracion=60, horario=None, precio=None):
    return Sitio(clave, cerca(km), puntaje, duracion, horario or abierto(), precio)


def un_dia(inicio=h(9), fin=h(18), dia=SABADO):
    return [Dia(dia, inicio, fin)]


def claves(problema, plan):
    return [[problema.sitios[p.sitio].clave for p in dia] for dia in plan.dias]


class ManejoTests(SimpleTestCase):
    def test_distancia_y_tiempo(self):
        self.assertAlmostEqual(distancia_km(ORIGEN, cerca(10)), 10, delta=0.05)
        self.assertEqual(minutos_de_manejo(0.1), 0)
        # 13.5 km por carretera a velocidad de ciudad (30 km/h) más 10 de estacionar.
        self.assertEqual(minutos_de_manejo(13.5), 27 + 10)
        self.assertEqual(minutos_de_manejo(70), 60 + 10)


class ReglasTests(SimpleTestCase):
    def test_respeta_el_horario_de_cada_sitio(self):
        problema = Problema(ORIGEN, un_dia(), [sitio('cerrado', horario=abierto(dias=[0])), sitio('abre_tarde',
                            horario=abierto(h(16), h(18)))], regresar=False)
        plan = decodificar(problema, [0, 1])
        self.assertEqual(claves(problema, plan), [['abre_tarde']])
        self.assertGreaterEqual(plan.dias[0][0].inicio, h(16))
        self.assertLessEqual(plan.dias[0][0].salida, h(18))

    def test_no_se_pasa_del_dia_y_regresa_a_tiempo(self):
        # 150 km en línea recta: unas 3 h de ida y 3 de vuelta. Cabe la ida, no el regreso.
        lejos = [sitio('lejos', km=150, duracion=60)]
        con_regreso = Problema(ORIGEN, un_dia(h(9), h(14)), lejos)
        self.assertEqual(claves(con_regreso, decodificar(con_regreso, [0])), [[]])
        sin_regreso = Problema(ORIGEN, un_dia(h(9), h(14)), lejos, regresar=False)
        self.assertEqual(claves(sin_regreso, decodificar(sin_regreso, [0])), [['lejos']])

    def test_presupuesto_por_persona(self):
        caro = sitio('caro', precio=Precio(Decimal('200')))
        barato = sitio('barato', km=2, precio=Precio(Decimal('50')))
        problema = Problema(ORIGEN, un_dia(), [caro, barato], personas=3, presupuesto=Decimal('500'))
        plan = decodificar(problema, [0, 1])
        # 3 personas × $200 = $600 no cabe; 3 × $50 = $150 sí.
        self.assertEqual(claves(problema, plan), [['barato']])
        self.assertEqual(plan.costo, Decimal('150'))

    def test_entrada_libre_en_su_dia(self):
        domingo_libre = sitio('museo', precio=Precio(Decimal('80'), {6}))
        problema = Problema(ORIGEN, un_dia(dia=6), [domingo_libre], personas=2, presupuesto=Decimal('0'))
        self.assertEqual(decodificar(problema, [0]).costo, Decimal('0'))

    def test_hace_una_pausa_para_comer(self):
        sitios = [sitio(n, km=1 + i * 0.5, duracion=90) for i, n in enumerate('abcde')]
        plan = decodificar(Problema(ORIGEN, un_dia(), sitios, regresar=False), range(5))
        comidas = [p for p in plan.dias[0] if p.comida_despues]
        self.assertEqual(len(comidas), 1)
        siguiente = plan.dias[0][plan.dias[0].index(comidas[0]) + 1]
        self.assertGreaterEqual(siguiente.llegada - comidas[0].salida, COMIDA_MIN)

    def test_el_segundo_dia_empieza_donde_termino_el_primero(self):
        sitios = [sitio('a', km=50, duracion=h(7)), sitio('b', km=52, duracion=60)]
        problema = Problema(ORIGEN, [Dia(SABADO, h(9), h(18)), Dia(6, h(9), h(18))], sitios, regresar=False)
        plan = decodificar(problema, [0, 1])
        self.assertEqual(claves(problema, plan), [['a'], ['b']])
        self.assertLess(plan.dias[1][0].km, 5)

    def test_costo_y_kilometros_del_plan(self):
        problema = Problema(ORIGEN, un_dia(), [sitio('a', km=10, precio=Precio(Decimal('45')))], personas=2)
        plan = decodificar(problema, [0])
        self.assertEqual(plan.costo, Decimal('90'))
        # Ida y vuelta por carretera.
        self.assertAlmostEqual(plan.km, 2 * 10 * 1.35, delta=0.2)


class MetodosTests(SimpleTestCase):
    def trampa_para_el_voraz(self):
        """El voraz toma primero lo rápido y cercano, y ya no llega al sitio valioso que cierra temprano."""
        rapido = sitio('rapido', km=0.1, puntaje=2, duracion=10)
        valioso = sitio('valioso', km=3, puntaje=5, duracion=60, horario=abierto(h(9), h(10, 20)))
        return Problema(ORIGEN, un_dia(h(9), h(11)), [rapido, valioso], regresar=False)

    def test_el_voraz_cae_en_la_trampa_y_el_genetico_no(self):
        problema = self.trampa_para_el_voraz()
        self.assertEqual(claves(problema, voraz(problema)), [['rapido']])
        plan = genetico(problema, semilla=1)
        self.assertEqual(claves(problema, plan), [['valioso', 'rapido']])
        self.assertGreater(plan.puntaje, voraz(problema).puntaje)

    def test_misma_semilla_mismo_plan(self):
        sitios = [sitio(i, km=1 + (i * 7) % 20, puntaje=1 + (i % 3), duracion=45) for i in range(15)]
        problema = Problema(ORIGEN, un_dia(), sitios)
        rapidos = Parametros(poblacion=20, generaciones=30)
        uno, otro = genetico(problema, rapidos, semilla=7), genetico(problema, rapidos, semilla=7)
        self.assertEqual(claves(problema, uno), claves(problema, otro))
        self.assertGreater(len(uno.visitados), 3)
        self.assertGreaterEqual(uno.generaciones, 1)

    def test_sin_sitios_o_con_uno(self):
        self.assertEqual(genetico(Problema(ORIGEN, un_dia(), [])).visitados, [])
        problema = Problema(ORIGEN, un_dia(), [sitio('solo')])
        self.assertEqual(claves(problema, genetico(problema)), [['solo']])

    def test_cruce_ox_conserva_todos_los_sitios(self):
        azar = random.Random(3)
        for _ in range(50):
            hijo = _cruce_ox(list(range(10)), azar.sample(range(10), 10), azar)
            self.assertEqual(sorted(hijo), list(range(10)))
