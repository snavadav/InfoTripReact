"""Compara el método voraz, el genético puro y el genético híbrido en escenarios reales.

Cada escenario sale de los destinos, horarios y precios de la base. El voraz es determinista y corre una vez;
cada genético corre `--corridas` veces con semillas 1..N, para medir su variación. Se puede repetir con el
mismo resultado.

    python manage.py experimento_rutas --corridas 35 --salida experimento.csv
"""
import csv
import math
import statistics
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.rutas.optimizador import Parametros, genetico, voraz
from apps.rutas.servicio import construir_problema, municipios_de_salida, resolver_destino

# Origen, días, intereses, ritmo, personas y presupuesto para entradas. Fechas fijas para que sea repetible:
# un sábado y un lunes, porque muchos museos cierran en lunes. Los primeros 12 son sin destino (en círculo);
# los últimos agregan un destino con los tipos de viaje del Planeador 2.0: (…, tipo de viaje, destino).
ESCENARIOS = [
    ('guadalajara', 1, ['ciudad-y-cultura'], 'normal', 2, None, date(2026, 11, 14)),
    ('guadalajara', 2, ['ciudad-y-cultura', 'pueblos'], 'normal', 2, None, date(2026, 11, 14)),
    ('guadalajara', 2, ['ciudad-y-cultura'], 'intenso', 4, Decimal('600'), date(2026, 11, 14)),
    ('guadalajara', 1, ['ciudad-y-cultura', 'miradores'], 'normal', 2, None, date(2026, 11, 16)),
    ('guadalajara', 3, ['naturaleza', 'miradores', 'lago'], 'tranquilo', 2, None, date(2026, 11, 14)),
    ('zapopan', 1, ['ciudad-y-cultura', 'naturaleza'], 'normal', 3, Decimal('300'), date(2026, 11, 14)),
    ('tlaquepaque', 2, ['ciudad-y-cultura', 'arqueologia'], 'normal', 2, None, date(2026, 11, 14)),
    ('puerto-vallarta', 2, ['costa', 'naturaleza', 'miradores'], 'normal', 2, None, date(2026, 11, 14)),
    ('puerto-vallarta', 1, ['ciudad-y-cultura', 'costa'], 'intenso', 1, None, date(2026, 11, 16)),
    ('tequila', 2, ['ciudad-y-cultura', 'pueblos', 'arqueologia'], 'normal', 2, Decimal('800'), date(2026, 11, 14)),
    ('chapala', 1, ['lago', 'ciudad-y-cultura', 'miradores'], 'tranquilo', 2, None, date(2026, 11, 14)),
    ('tapalpa', 2, ['naturaleza', 'miradores', 'pueblos'], 'normal', 4, None, date(2026, 11, 14)),
    ('guadalajara', 1, ['pueblos', 'naturaleza', 'miradores'], 'normal', 2, None, date(2026, 11, 14), 'ida',
     'municipio:tapalpa'),
    ('guadalajara', 2, ['costa', 'pueblos', 'ciudad-y-cultura'], 'normal', 2, None, date(2026, 11, 14), 'ida',
     'municipio:puerto-vallarta'),
    ('zapopan', 2, ['ciudad-y-cultura', 'pueblos', 'arqueologia'], 'normal', 3, Decimal('600'), date(2026, 11, 16),
     'ida', 'destino:tequila'),
    ('guadalajara', 3, ['naturaleza', 'pueblos', 'miradores'], 'tranquilo', 2, None, date(2026, 11, 14), 'base',
     'municipio:mazamitla'),
    ('guadalajara', 2, ['lago', 'pueblos', 'ciudad-y-cultura'], 'normal', 4, None, date(2026, 11, 14), 'base',
     'municipio:chapala'),
    ('tlaquepaque', 3, ['pueblos', 'naturaleza', 'ciudad-y-cultura'], 'intenso', 2, None, date(2026, 11, 14), 'base',
     'destino:tapalpa'),
]
METODOS = ['voraz', 'genetico_puro', 'genetico_hibrido']


def prueba_de_signos(mejoras, empeoras):
    """Valor p de dos colas de la prueba de signos exacta: ¿gana uno más veces de lo que daría el azar?"""
    n = mejoras + empeoras
    if n == 0:
        return 1.0
    extremos = min(mejoras, empeoras)
    cola = sum(math.comb(n, k) for k in range(extremos + 1)) / 2 ** n
    return min(1.0, 2 * cola)


class Command(BaseCommand):
    help = 'Compara el voraz y el genético (puro e híbrido) en escenarios reales; escribe un CSV y un resumen.'

    def add_arguments(self, parser):
        parser.add_argument('--corridas', type=int, default=35, help='Corridas de cada genético por escenario.')
        parser.add_argument('--salida', help='Ruta del CSV con cada corrida.')
        parser.add_argument('--escenarios', type=int, help='Usar solo los primeros N escenarios.')

    def handle(self, *args, corridas, salida, escenarios, **opciones):
        if corridas < 1:
            raise CommandError('--corridas debe ser al menos 1.')
        origenes = {m.slug: (float(m.lat), float(m.lng)) for m in municipios_de_salida()}
        filas = []
        # El CSV se escribe escenario por escenario: si la corrida se interrumpe, lo avanzado queda guardado.
        archivo = open(salida, 'w', newline='', encoding='utf-8') if salida else None
        escritor = None
        try:
            for numero, escenario in enumerate(ESCENARIOS[:escenarios], start=1):
                municipio, dias, intereses, ritmo, personas, presupuesto, fecha = escenario[:7]
                modo, hacia = escenario[7:] or ('circulo', None)
                destino = resolver_destino(hacia) if hacia else None
                if municipio not in origenes or (hacia and destino is None):
                    self.stdout.write(f'Escenario {numero}: {municipio} o {hacia} no tiene destinos en esta base; '
                                      'se omite.')
                    continue
                problema, _, _ = construir_problema(origenes[municipio], fecha, dias, 9 * 60, 19 * 60, intereses,
                                                    ritmo, personas, presupuesto, modo=modo, destino=destino)
                base = {'escenario': numero, 'origen': municipio, 'dias': dias, 'intereses': '+'.join(intereses),
                        'modo': modo, 'destino': hacia or '', 'candidatos': len(problema.sitios)}
                del_escenario = [{**base, 'metodo': 'voraz', 'semilla': '', **self.medidas(voraz(problema))}]
                for metodo, parametros in (('genetico_puro', Parametros(sembrados=0)),
                                           ('genetico_hibrido', Parametros())):
                    for semilla in range(1, corridas + 1):
                        plan = genetico(problema, parametros, semilla=semilla)
                        del_escenario.append({**base, 'metodo': metodo, 'semilla': semilla, **self.medidas(plan)})
                filas += del_escenario
                if archivo:
                    if escritor is None:
                        escritor = csv.DictWriter(archivo, fieldnames=list(del_escenario[0]))
                        escritor.writeheader()
                    escritor.writerows(del_escenario)
                    archivo.flush()
                self.stdout.write(f'Escenario {numero} listo: {municipio}, {dias} día(s), {modo}'
                                  f'{" a " + hacia if hacia else ""}, {len(problema.sitios)} candidatos.')
                self.stdout.flush()
        finally:
            if archivo:
                archivo.close()
        if not filas:
            raise CommandError('No hay escenarios con datos: carga los destinos primero (ver docs/mvp.md).')
        if salida:
            self.stdout.write(f'CSV: {salida} ({len(filas)} filas)')
        self.resumen(filas)

    @staticmethod
    def medidas(plan):
        return {'puntaje': round(plan.puntaje, 4), 'aptitud': round(plan.aptitud, 4), 'sitios': len(plan.visitados),
                'km': round(plan.km, 1), 'manejo_min': plan.manejo, 'costo': str(plan.costo),
                'segundos': round(plan.segundos, 4), 'generaciones': plan.generaciones}

    def resumen(self, filas):
        self.resumen_de(filas, 'todos los escenarios')
        modos = sorted({f['modo'] for f in filas})
        if len(modos) > 1:
            for modo in modos:
                self.resumen_de([f for f in filas if f['modo'] == modo], f'tipo de viaje «{modo}»')

    def resumen_de(self, filas, titulo):
        self.stdout.write(f'\nPor método ({titulo}, todas las corridas):')
        self.stdout.write(f'{"método":<18}{"n":>5}{"aptitud media":>15}{"desv. est.":>12}{"sitios":>8}'
                          f'{"km":>8}{"segundos":>10}')
        for metodo in METODOS:
            de_metodo = [f for f in filas if f['metodo'] == metodo]
            aptitudes = [f['aptitud'] for f in de_metodo]
            desviacion = statistics.stdev(aptitudes) if len(aptitudes) > 1 else 0
            self.stdout.write(
                f'{metodo:<18}{len(de_metodo):>5}{statistics.mean(aptitudes):>15.3f}{desviacion:>12.3f}'
                f'{statistics.mean(f["sitios"] for f in de_metodo):>8.2f}'
                f'{statistics.mean(f["km"] for f in de_metodo):>8.1f}'
                f'{statistics.mean(f["segundos"] for f in de_metodo):>10.3f}')
        self.stdout.write('\nCada genético frente al voraz, corrida por corrida (aptitud):')
        voraz_por_escenario = {f['escenario']: f['aptitud'] for f in filas if f['metodo'] == 'voraz'}
        for metodo in METODOS[1:]:
            mejora = empata = empeora = 0
            diferencias = []
            for fila in (f for f in filas if f['metodo'] == metodo):
                diferencia = fila['aptitud'] - voraz_por_escenario[fila['escenario']]
                diferencias.append(diferencia)
                if diferencia > 1e-6:
                    mejora += 1
                elif diferencia < -1e-6:
                    empeora += 1
                else:
                    empata += 1
            p = prueba_de_signos(mejora, empeora)
            self.stdout.write(f'{metodo}: mejora {mejora}, empata {empata}, empeora {empeora}; '
                              f'diferencia media {statistics.mean(diferencias):+.3f}; prueba de signos p = {p:.4g}')
