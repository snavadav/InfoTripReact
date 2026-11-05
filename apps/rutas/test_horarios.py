"""El lector de horarios y precios con los textos reales del Sistema de Información Cultural."""
import json
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase

from .horarios import leer_horario, leer_precio

CONTENIDO = Path(__file__).resolve().parent.parent / 'destinos' / 'datos' / 'contenido_inicial.json'
LU, MA, MI, JU, VI, SA, DO = range(7)


def h(hora, minuto=0):
    return hora * 60 + minuto


class HorarioTests(SimpleTestCase):
    def dias(self, texto):
        return leer_horario(texto).dias

    def test_rango_simple_y_dias_cerrados(self):
        dias = self.dias('Martes a domingo de 10 a 17 hrs.')
        self.assertEqual(dias[MA], [(h(10), h(17))])
        self.assertNotIn(LU, dias)

    def test_dos_turnos_y_minutos(self):
        self.assertEqual(self.dias('Martes a domingos de 10 a 14:30 y de 16 a 18 hrs.')[VI],
                         [(h(10), h(14, 30)), (h(16), h(18))])

    def test_lo_posterior_corrige_lo_anterior(self):
        dias = self.dias('Martes a domingo de 9:30 a 17:30 h. Sábado y domingo de 9 h a 16 h')
        self.assertEqual((dias[MI], dias[SA], dias[DO]), ([(h(9, 30), h(17, 30))], [(h(9), h(16))], [(h(9), h(16))]))

    def test_semana_que_da_la_vuelta(self):
        self.assertEqual(sorted(self.dias('Viernes a miércoles de 10 a 14 y de 16 a 18 hrs.')), [LU, MA, MI, VI, SA, DO])
        dias = self.dias('Martes a viernes 10 a 18 h. Sábado a lunes de 10 a 16 h')
        self.assertEqual((dias[LU], dias[MA]), ([(h(10), h(16))], [(h(10), h(18))]))

    def test_cerrado_explicito(self):
        dias = self.dias('Miércoles a lunes de 9 a 18 h. Martes cerrado')
        self.assertNotIn(MA, dias)
        self.assertNotIn(DO, self.dias('Lunes a viernes: 9 a 18 h. Sábados: 10 a 14 h. Domingos: Cerrado'))

    def test_puntos_y_guiones_de_la_fuente(self):
        self.assertEqual(self.dias('Lunes a. Viernes: 8:30 a 15:00 h.')[JU], [(h(8, 30), h(15))])
        self.assertEqual(self.dias('Martes-Domingo: 09:00-15:00 hrs. Lunes: cerrado')[DO], [(h(9), h(15))])
        self.assertEqual(self.dias('Todos los días del año de 11 a 19 hrs.')[LU], [(h(11), h(19))])
        self.assertEqual(self.dias('Las 24 horas.')[DO], [(0, h(24))])

    def test_dias_que_esperan_su_hora(self):
        dias = self.dias('Lunes a viernes y sábado de 9 a 14 h')
        self.assertEqual((dias[LU], dias[SA]), ([(h(9), h(14))], [(h(9), h(14))]))

    def test_recorridos_a_horas_fijas(self):
        horario = leer_horario('Martes a sábado en horario de 10, 11, 13 y 14 hrs.')
        self.assertTrue(horario.guiado)
        self.assertEqual(horario.dias[MA], [(h(10), h(15))])

    def test_con_cita_o_sin_horas_no_se_adivina(self):
        for texto in ['Por el momento previa cita de grupos de escuelas', 'Lunes a viernes de 16 a 19 h Previa cita: 33 3105',
                      'Consultar en taquilla', '', None]:
            self.assertIsNone(leer_horario(texto), texto)

    def test_todos_los_textos_reales_se_entienden(self):
        textos = [s['datos']['horarios'] for s in json.loads(CONTENIDO.read_text(encoding='utf-8'))
                  if s.get('datos', {}).get('horarios')]
        sin_leer = [t for t in textos if leer_horario(t) is None and 'cita' not in t.lower()]
        self.assertGreater(len(textos), 80)
        self.assertEqual(sin_leer, [])
        for texto in textos:
            horario = leer_horario(texto)
            for intervalos in (horario.dias.values() if horario else []):
                self.assertTrue(all(0 <= a < b <= h(24) for a, b in intervalos), texto)


class PrecioTests(SimpleTestCase):
    def adulto(self, texto):
        return leer_precio(texto).adulto

    def test_entrada_general_antes_que_otras_cifras(self):
        self.assertEqual(self.adulto('Entrada libre a personas con capacidades diferentes y niños menores de 6 años '
                                     'Entrada general $ 45, niños $ 30'), Decimal('45'))
        self.assertEqual(self.adulto('Entrada General $ 37 Estudiantes y Profesores $ 18'), Decimal('37'))

    def test_precio_de_adultos(self):
        self.assertEqual(self.adulto('Menores $20 Adultos $80 Estudiantes $50'), Decimal('80'))
        self.assertEqual(self.adulto('La entrada tiene un costo de $10 pesos para adultos y $5 pesos para niños.'),
                         Decimal('10'))
        self.assertEqual(self.adulto('dos boletos Adulto - $160 Niño/Inapam - $140'), Decimal('160'))

    def test_libre_y_voluntario(self):
        for texto in ['Entrada libre.', 'Entrada gratuita', 'Entrada es libre', 'Cuota voluntaria']:
            self.assertEqual(self.adulto(texto), Decimal('0'), texto)

    def test_dias_de_entrada_libre(self):
        precio = leer_precio('Entrada general: $20 Estudiantes $10 Domingos: entrada libre')
        self.assertEqual((precio.para(SA), precio.para(DO)), (Decimal('20'), Decimal('0')))
        solo_domingo = leer_precio('Domingo entrada libre')
        self.assertEqual((solo_domingo.para(LU), solo_domingo.para(DO)), (None, Decimal('0')))

    def test_sin_precio(self):
        self.assertIsNone(leer_precio('Consultar en taquilla'))
        self.assertIsNone(leer_precio(''))

    def test_todos_los_textos_reales_se_entienden(self):
        textos = [s['datos']['precios'] for s in json.loads(CONTENIDO.read_text(encoding='utf-8'))
                  if s.get('datos', {}).get('precios')]
        self.assertGreater(len(textos), 60)
        self.assertEqual([t for t in textos if leer_precio(t) is None], [])
