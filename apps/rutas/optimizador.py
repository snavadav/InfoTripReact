"""Elige qué visitar y en qué orden: el problema del orientador con ventanas de tiempo, en varios días.

Hay más sitios de los que caben en el viaje. Cada uno vale un puntaje (qué tanto le interesa a la persona),
tarda un tiempo en visitarse y solo se puede visitar cuando está abierto. Se busca el mayor puntaje sin
pasarse del horario de cada día ni del presupuesto.

Dos métodos para comparar:
- `voraz`: en cada paso va al sitio que más puntaje da por minuto invertido. Rápido, pero miope.
- `genetico`: evoluciona órdenes de visita. Cada orden se convierte en itinerario con `decodificar`.

No depende de Django: recibe datos simples y se puede ejecutar y medir por separado.
"""
import math
import random
import time
from dataclasses import dataclass, field
from decimal import Decimal

# La carretera es más larga que la línea recta; 1.35 es un valor habitual en zonas con sierra y ciudad.
FACTOR_CARRETERA = 1.35
VELOCIDAD_CIUDAD_KMH = 30
VELOCIDAD_CARRETERA_KMH = 70
# Por debajo de esta distancia se maneja a velocidad de ciudad.
KM_CIUDAD = 15
ESTACIONAR_MIN = 10
COMIDA_DESDE = 13 * 60 + 30
COMIDA_HASTA = 16 * 60
COMIDA_MIN = 60
# Peso del tiempo al volante frente al puntaje: solo desempata itinerarios de interés parecido.
PESO_MANEJO = 0.002


def distancia_km(a, b):
    """Haversine. Repetida aquí para que el optimizador no dependa de otras apps."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def km_por_carretera(a, b):
    return distancia_km(a, b) * FACTOR_CARRETERA


def minutos_de_manejo(km):
    if km < 0.3:
        return 0
    velocidad = VELOCIDAD_CIUDAD_KMH if km < KM_CIUDAD else VELOCIDAD_CARRETERA_KMH
    return round(km / velocidad * 60) + ESTACIONAR_MIN


@dataclass
class Sitio:
    clave: object
    punto: tuple
    puntaje: float
    duracion: int
    # Objeto con .intervalos(dia_semana) -> [(abre, cierra)] en minutos.
    horario: object
    # Objeto con .para(dia_semana) -> Decimal | None, o None si no se conoce.
    precio: object = None

    def precio_para(self, dia_semana):
        return self.precio.para(dia_semana) if self.precio else None


@dataclass
class Dia:
    dia_semana: int
    inicio: int
    fin: int


@dataclass
class Problema:
    origen: tuple
    dias: list
    sitios: list
    personas: int = 1
    presupuesto: Decimal | None = None
    # El último día hay que volver al punto de partida antes de la hora de fin.
    regresar: bool = True

    def __post_init__(self):
        puntos = [self.origen] + [s.punto for s in self.sitios]
        km = [[km_por_carretera(a, b) for b in puntos] for a in puntos]
        self.km = km
        self.minutos = [[minutos_de_manejo(x) for x in fila] for fila in km]


@dataclass
class Parada:
    sitio: int
    llegada: int
    inicio: int
    salida: int
    km: float
    manejo: int
    # Se come al terminar esta visita.
    comida_despues: bool = False


@dataclass
class Plan:
    dias: list
    puntaje: float = 0.0
    km: float = 0.0
    manejo: int = 0
    costo: Decimal = Decimal('0')
    # Lo que tardó en calcularse, en segundos; para el experimento.
    segundos: float = 0.0
    generaciones: int = 0

    @property
    def visitados(self):
        return [p.sitio for dia in self.dias for p in dia]

    @property
    def aptitud(self):
        return self.puntaje - PESO_MANEJO * self.manejo


@dataclass
class _Estado:
    """Dónde y a qué hora está la persona mientras se arma un día."""
    lugar: int
    hora: int
    comio: bool = False
    paradas: list = field(default_factory=list)


def _ventana(sitio, dia, llegada):
    """Hora de inicio de la visita en la primera ventana donde cabe, o None."""
    for abre, cierra in sitio.horario.intervalos(dia.dia_semana):
        inicio = max(llegada, abre)
        if inicio + sitio.duracion <= cierra:
            return inicio
    return None


def _intentar(problema, estado, indice, dia, ultimo_dia, gastado):
    """La parada si el sitio cabe a continuación, o None. `indice` cuenta desde 0 en problema.sitios."""
    sitio = problema.sitios[indice]
    precio = sitio.precio_para(dia.dia_semana) or Decimal('0')
    if problema.presupuesto is not None and gastado + precio * problema.personas > problema.presupuesto:
        return None
    nodo = indice + 1
    hora = estado.hora
    comida_antes = False
    # Si ya es hora de comer y no ha comido, come donde está antes de seguir.
    if not estado.comio and COMIDA_DESDE <= hora < COMIDA_HASTA and estado.paradas:
        hora += COMIDA_MIN
        comida_antes = True
    manejo = problema.minutos[estado.lugar][nodo]
    inicio = _ventana(sitio, dia, hora + manejo)
    if inicio is None:
        return None
    salida = inicio + sitio.duracion
    limite = dia.fin - (problema.minutos[nodo][0] if ultimo_dia and problema.regresar else 0)
    if salida > limite:
        return None
    return Parada(indice, hora + manejo, inicio, salida, problema.km[estado.lugar][nodo], manejo), comida_antes


def _agregar(estado, parada, comida_antes):
    if comida_antes:
        estado.paradas[-1].comida_despues = True
        estado.comio = True
    estado.paradas.append(parada)
    estado.lugar = parada.sitio + 1
    estado.hora = parada.salida


def _cerrar(problema, plan, dias):
    plan.dias = dias
    for dia, paradas in zip(problema.dias, dias):
        for p in paradas:
            plan.puntaje += problema.sitios[p.sitio].puntaje
            plan.km += p.km
            plan.manejo += p.manejo
            precio = problema.sitios[p.sitio].precio_para(dia.dia_semana)
            plan.costo += (precio or Decimal('0')) * problema.personas
    if problema.regresar and dias and dias[-1]:
        ultimo = dias[-1][-1].sitio + 1
        plan.km += problema.km[ultimo][0]
        plan.manejo += problema.minutos[ultimo][0]
    return plan


def decodificar(problema, orden):
    """Convierte un orden de sitios en itinerario: llena cada día con los que caben, en ese orden.

    Un día empieza donde terminó el anterior (ahí se duerme); el primero, en el origen.
    """
    pendientes = list(orden)
    dias = []
    lugar = 0
    gastado = Decimal('0')
    for numero, dia in enumerate(problema.dias):
        estado = _Estado(lugar, dia.inicio)
        ultimo = numero == len(problema.dias) - 1
        quedan = []
        for indice in pendientes:
            intento = _intentar(problema, estado, indice, dia, ultimo, gastado)
            if intento is None:
                quedan.append(indice)
                continue
            parada, comida_antes = intento
            _agregar(estado, parada, comida_antes)
            gastado += (problema.sitios[indice].precio_para(dia.dia_semana) or Decimal('0')) * problema.personas
        pendientes = quedan
        dias.append(estado.paradas)
        lugar = estado.lugar
    return _cerrar(problema, Plan([]), dias)


def voraz(problema):
    """En cada paso, el sitio que cabe y da más puntaje por minuto de manejo y visita."""
    inicio_reloj = time.perf_counter()
    pendientes = set(range(len(problema.sitios)))
    dias = []
    lugar = 0
    gastado = Decimal('0')
    for numero, dia in enumerate(problema.dias):
        estado = _Estado(lugar, dia.inicio)
        ultimo = numero == len(problema.dias) - 1
        while True:
            mejor = None
            for indice in sorted(pendientes):
                intento = _intentar(problema, estado, indice, dia, ultimo, gastado)
                if intento is None:
                    continue
                parada, _ = intento
                costo_tiempo = parada.salida - estado.hora
                razon = problema.sitios[indice].puntaje / max(costo_tiempo, 1)
                if mejor is None or razon > mejor[0]:
                    mejor = (razon, indice, intento)
            if mejor is None:
                break
            _, indice, (parada, comida_antes) = mejor
            _agregar(estado, parada, comida_antes)
            gastado += (problema.sitios[indice].precio_para(dia.dia_semana) or Decimal('0')) * problema.personas
            pendientes.discard(indice)
        dias.append(estado.paradas)
        lugar = estado.lugar
    plan = _cerrar(problema, Plan([]), dias)
    plan.segundos = time.perf_counter() - inicio_reloj
    return plan


@dataclass
class Parametros:
    poblacion: int = 60
    generaciones: int = 150
    # Se detiene antes si el mejor no mejora en este número de generaciones.
    paciencia: int = 40
    torneo: int = 3
    cruce: float = 0.9
    mutacion: float = 0.3
    elite: int = 2


def _cruce_ox(padre, madre, azar):
    """Cruce de orden (OX): conserva un tramo del padre y completa con el orden relativo de la madre."""
    n = len(padre)
    a, b = sorted(azar.sample(range(n), 2))
    tramo = padre[a:b + 1]
    presentes = set(tramo)
    resto = [x for x in madre if x not in presentes]
    return resto[:a] + tramo + resto[a:]


def _mutar(orden, azar):
    """Intercambio de dos sitios o inversión de un tramo, con la misma probabilidad."""
    hijo = list(orden)
    a, b = sorted(azar.sample(range(len(hijo)), 2))
    if azar.random() < 0.5:
        hijo[a], hijo[b] = hijo[b], hijo[a]
    else:
        hijo[a:b + 1] = reversed(hijo[a:b + 1])
    return hijo


def genetico(problema, parametros=None, semilla=None):
    """Algoritmo genético con torneo, cruce OX, mutación y élite. Con la misma semilla da el mismo plan."""
    parametros = parametros or Parametros()
    azar = random.Random(semilla)
    inicio_reloj = time.perf_counter()
    n = len(problema.sitios)
    if n < 2:
        plan = decodificar(problema, list(range(n)))
        plan.segundos = time.perf_counter() - inicio_reloj
        return plan

    def evaluar(orden):
        return decodificar(problema, orden).aptitud

    poblacion = [azar.sample(range(n), n) for _ in range(parametros.poblacion)]
    aptitudes = [evaluar(orden) for orden in poblacion]
    mejor_aptitud, sin_mejora, generacion = max(aptitudes), 0, 0
    for generacion in range(1, parametros.generaciones + 1):
        ordenados = sorted(range(len(poblacion)), key=aptitudes.__getitem__, reverse=True)
        nueva = [poblacion[i] for i in ordenados[:parametros.elite]]
        nuevas_aptitudes = [aptitudes[i] for i in ordenados[:parametros.elite]]

        def torneo():
            rivales = azar.sample(range(len(poblacion)), parametros.torneo)
            return poblacion[max(rivales, key=aptitudes.__getitem__)]

        while len(nueva) < parametros.poblacion:
            padre, madre = torneo(), torneo()
            hijo = _cruce_ox(padre, madre, azar) if azar.random() < parametros.cruce else list(padre)
            if azar.random() < parametros.mutacion:
                hijo = _mutar(hijo, azar)
            nueva.append(hijo)
            nuevas_aptitudes.append(evaluar(hijo))
        poblacion, aptitudes = nueva, nuevas_aptitudes
        actual = max(aptitudes)
        if actual > mejor_aptitud + 1e-9:
            mejor_aptitud, sin_mejora = actual, 0
        else:
            sin_mejora += 1
            if sin_mejora >= parametros.paciencia:
                break
    mejor = poblacion[max(range(len(poblacion)), key=aptitudes.__getitem__)]
    plan = decodificar(problema, mejor)
    plan.segundos = time.perf_counter() - inicio_reloj
    plan.generaciones = generacion
    return plan
