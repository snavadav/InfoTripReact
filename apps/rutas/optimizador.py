"""Elige qué visitar y en qué orden: el problema del orientador con ventanas de tiempo, en varios días.

Hay más sitios de los que caben en el viaje. Cada uno vale un puntaje (qué tanto le interesa a la persona),
tarda un tiempo en visitarse y solo se puede visitar cuando está abierto. Se busca el mayor puntaje sin
pasarse del horario de cada día ni del presupuesto.

Dos métodos para comparar:
- `voraz`: en cada paso va al sitio que más puntaje da por minuto invertido. Rápido, pero miope.
- `genetico`: evoluciona órdenes de visita. Cada orden se convierte en itinerario con `decodificar`.

El viaje puede terminar en otro punto (`Problema.final`, solo ida), volver a casa (`Problema.regresar`) o tener
días que empiezan y terminan en un lugar fijo (`Dia.desde` y `Dia.hasta`, para quedarse en el destino). La
persona puede fijar sitios o pedir descansos (`Sitio.obligatorio`): la aptitud los premia con BONO_OBLIGATORIO.

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
# Bono de aptitud por cada sitio obligatorio (fijado por la persona o un descanso) que entra al plan. Es mucho
# mayor que cualquier puntaje real (alrededor de 1 por sitio): un plan que respeta lo fijado siempre gana. No se
# suma a `Plan.puntaje`, que sigue midiendo solo el interés, igual que antes.
BONO_OBLIGATORIO = 100


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
    # Solo cabe en ese día (0 = el primero); None, en cualquiera. Lo usan los fijados y los descansos.
    dia: int | None = None
    # La persona lo pidió: la aptitud suma BONO_OBLIGATORIO si entra.
    obligatorio: bool = False
    # Un descanso: ocurre donde se esté, sin manejar, así que `punto` no se usa.
    en_sitio: bool = False
    # Minuto en que la persona lo esperaba (el de su plan anterior); solo ordena las semillas del genético.
    objetivo: int | None = None

    def precio_para(self, dia_semana):
        return self.precio.para(dia_semana) if self.precio else None


@dataclass
class Dia:
    dia_semana: int
    inicio: int
    fin: int
    # Nodo donde empieza el día (0 = origen; Problema.nodo_final = destino). None: donde terminó el anterior,
    # que es donde se durmió; el primero, en el origen.
    desde: int | None = None
    # Nodo al que hay que llegar antes de `fin` (por ejemplo, volver a dormir al destino). None: el día acaba
    # en la última parada, salvo el último (ver Problema.cierre).
    hasta: int | None = None


@dataclass
class Problema:
    origen: tuple
    dias: list
    sitios: list
    personas: int = 1
    presupuesto: Decimal | None = None
    # El último día hay que volver al punto de partida antes de la hora de fin.
    regresar: bool = True
    # Punto donde termina el viaje (solo ida o quedarse en el destino). Con él, `regresar` no aplica: el último
    # día hay que llegar aquí y ningún día anterior puede alejarse tanto que ya no dé tiempo de llegar.
    final: tuple | None = None

    def __post_init__(self):
        # Nodos: 0 = origen, 1..n = sitios, n + 1 = punto final (si hay).
        puntos = [self.origen] + [self.origen if s.en_sitio else s.punto for s in self.sitios]
        if self.final is not None:
            puntos.append(self.final)
        km = [[km_por_carretera(a, b) for b in puntos] for a in puntos]
        self.km = km
        self.minutos = [[minutos_de_manejo(x) for x in fila] for fila in km]
        self.cierres = [self.cierre(numero) for numero in range(len(self.dias))]
        # Minutos de los días que faltan después de cada uno: para saber si todavía da tiempo de llegar al final.
        self.resto = [sum(d.fin - d.inicio for d in self.dias[numero + 1:]) for numero in range(len(self.dias))]

    @property
    def nodo_final(self):
        return len(self.sitios) + 1 if self.final is not None else None

    def cierre(self, numero):
        """Nodo al que hay que llegar al terminar ese día, o None si el día acaba donde quede."""
        dia = self.dias[numero]
        if dia.hasta is not None:
            return dia.hasta
        if numero == len(self.dias) - 1:
            if self.final is not None:
                return self.nodo_final
            if self.regresar:
                return 0
        return None


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
    # Cuántos sitios obligatorios (fijados o descansos) entraron.
    obligatorios: int = 0

    @property
    def visitados(self):
        return [p.sitio for dia in self.dias for p in dia]

    @property
    def aptitud(self):
        return self.puntaje + BONO_OBLIGATORIO * self.obligatorios - PESO_MANEJO * self.manejo


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


def _intentar(problema, estado, indice, numero, gastado):
    """La parada si el sitio cabe a continuación, o None. `indice` cuenta desde 0 en problema.sitios."""
    sitio = problema.sitios[indice]
    if sitio.dia is not None and sitio.dia != numero:
        return None
    dia = problema.dias[numero]
    precio = sitio.precio_para(dia.dia_semana) or Decimal('0')
    if problema.presupuesto is not None and gastado + precio * problema.personas > problema.presupuesto:
        return None
    hora = estado.hora
    comida_antes = False
    # Si ya es hora de comer y no ha comido, come donde está antes de seguir.
    if not estado.comio and COMIDA_DESDE <= hora < COMIDA_HASTA and estado.paradas:
        hora += COMIDA_MIN
        comida_antes = True
    if sitio.en_sitio:
        nodo, manejo, km = estado.lugar, 0, 0.0
    else:
        nodo = indice + 1
        manejo, km = problema.minutos[estado.lugar][nodo], problema.km[estado.lugar][nodo]
    inicio = _ventana(sitio, dia, hora + manejo)
    if inicio is None:
        return None
    salida = inicio + sitio.duracion
    cierre = problema.cierres[numero]
    if cierre is not None:
        if salida + problema.minutos[nodo][cierre] > dia.fin:
            return None
    elif problema.final is not None:
        # Hoy no hay que llegar a ningún lado, pero se duerme en la última parada: los días que faltan deben
        # alcanzar para manejar de ahí al final.
        if salida > dia.fin or problema.minutos[nodo][problema.nodo_final] > problema.resto[numero]:
            return None
    elif salida > dia.fin:
        return None
    return Parada(indice, hora + manejo, inicio, salida, km, manejo), comida_antes


def _agregar(problema, estado, parada, comida_antes):
    if comida_antes:
        estado.paradas[-1].comida_despues = True
        estado.comio = True
    estado.paradas.append(parada)
    if not problema.sitios[parada.sitio].en_sitio:
        estado.lugar = parada.sitio + 1
    estado.hora = parada.salida


def _empezar(problema, numero, lugar):
    """El estado al empezar ese día: donde diga el día o, si no dice, donde se durmió."""
    dia = problema.dias[numero]
    return _Estado(lugar if dia.desde is None else dia.desde, dia.inicio)


def _terminar(problema, numero, estado, inicio, recorrido):
    """Anota el día y devuelve el nodo donde se duerme."""
    cierre = problema.cierres[numero]
    recorrido.append((estado.paradas, inicio, estado.lugar, cierre))
    return estado.lugar if cierre is None else cierre


def _cerrar(problema, plan, recorrido):
    plan.dias = [paradas for paradas, _, _, _ in recorrido]
    for dia, (paradas, inicio, lugar, cierre) in zip(problema.dias, recorrido):
        for p in paradas:
            sitio = problema.sitios[p.sitio]
            plan.puntaje += sitio.puntaje
            plan.obligatorios += sitio.obligatorio
            plan.km += p.km
            plan.manejo += p.manejo
            plan.costo += (sitio.precio_para(dia.dia_semana) or Decimal('0')) * problema.personas
        # El tramo hasta donde termina el día. El regreso a casa de siempre (sin punto final ni cierre propio del
        # día) solo cuenta si el día tuvo paradas, como en la versión original.
        if cierre is not None and (paradas or problema.final is not None or dia.hasta is not None):
            desde = lugar if paradas else inicio
            plan.km += problema.km[desde][cierre]
            plan.manejo += problema.minutos[desde][cierre]
    return plan


def decodificar(problema, orden):
    """Convierte un orden de sitios en itinerario: llena cada día con los que caben, en ese orden.

    Un día empieza donde terminó el anterior (ahí se duerme) o donde diga `Dia.desde`; el primero, en el origen.
    """
    pendientes = list(orden)
    recorrido = []
    lugar = 0
    gastado = Decimal('0')
    for numero, dia in enumerate(problema.dias):
        estado = _empezar(problema, numero, lugar)
        inicio = estado.lugar
        quedan = []
        for indice in pendientes:
            intento = _intentar(problema, estado, indice, numero, gastado)
            if intento is None:
                quedan.append(indice)
                continue
            parada, comida_antes = intento
            _agregar(problema, estado, parada, comida_antes)
            gastado += (problema.sitios[indice].precio_para(dia.dia_semana) or Decimal('0')) * problema.personas
        pendientes = quedan
        lugar = _terminar(problema, numero, estado, inicio, recorrido)
    return _cerrar(problema, Plan([]), recorrido)


def voraz(problema):
    """En cada paso, el sitio que cabe y da más puntaje por minuto de manejo y visita."""
    inicio_reloj = time.perf_counter()
    pendientes = set(range(len(problema.sitios)))
    recorrido = []
    lugar = 0
    gastado = Decimal('0')
    for numero, dia in enumerate(problema.dias):
        estado = _empezar(problema, numero, lugar)
        inicio = estado.lugar
        while True:
            mejor = None
            for indice in sorted(pendientes):
                intento = _intentar(problema, estado, indice, numero, gastado)
                if intento is None:
                    continue
                parada, _ = intento
                costo_tiempo = parada.salida - estado.hora
                # Lo obligatorio vale lo mismo que en la aptitud, para comparar ambos métodos con la misma vara.
                sitio = problema.sitios[indice]
                razon = (sitio.puntaje + BONO_OBLIGATORIO * sitio.obligatorio) / max(costo_tiempo, 1)
                if mejor is None or razon > mejor[0]:
                    mejor = (razon, indice, intento)
            if mejor is None:
                break
            _, indice, (parada, comida_antes) = mejor
            _agregar(problema, estado, parada, comida_antes)
            gastado += (problema.sitios[indice].precio_para(dia.dia_semana) or Decimal('0')) * problema.personas
            pendientes.discard(indice)
        lugar = _terminar(problema, numero, estado, inicio, recorrido)
    plan = _cerrar(problema, Plan([]), recorrido)
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
    # Híbrido: parte de la población inicial sale del método voraz y de variaciones suyas.
    # Con 0 es un genético puro, que empieza solo con órdenes al azar.
    sembrados: float = 0.25


def _cruce_ox(padre, madre, azar):
    """Cruce de orden (OX): conserva un tramo del padre y completa con el orden relativo de la madre."""
    n = len(padre)
    a, b = sorted(azar.sample(range(n), 2))
    tramo = padre[a:b + 1]
    presentes = set(tramo)
    resto = [x for x in madre if x not in presentes]
    return resto[:a] + tramo + resto[a:]


def _mutar(orden, azar):
    """Intercambio de dos sitios, inversión de un tramo o mover un sitio a otra posición."""
    hijo = list(orden)
    a, b = sorted(azar.sample(range(len(hijo)), 2))
    tipo = azar.random()
    if tipo < 1 / 3:
        hijo[a], hijo[b] = hijo[b], hijo[a]
    elif tipo < 2 / 3:
        hijo[a:b + 1] = reversed(hijo[a:b + 1])
    else:
        # Mover suele meter un sitio que no cabía en el hueco justo de otro día.
        hijo.insert(b, hijo.pop(a))
    return hijo


def _resto_por_puntaje(problema, usados):
    return sorted(set(range(len(problema.sitios))) - set(usados), key=lambda i: -problema.sitios[i].puntaje)


def _orden_voraz(problema, plan=None):
    """El orden que eligió el voraz, seguido de los sitios que no visitó, de más a menos puntaje."""
    visitados = (plan or voraz(problema)).visitados
    return visitados + _resto_por_puntaje(problema, visitados)


def _orden_con_obligatorios(problema, plan):
    """El plan voraz con lo obligatorio intercalado en su día y a la hora que la persona esperaba.

    El voraz no sabe de fijados ni de descansos; este orden le da al genético un punto de partida que sí los
    respeta, sin perder lo que el voraz ya había acomodado alrededor.
    """
    momento = {}
    for numero, paradas in enumerate(plan.dias):
        for parada in paradas:
            momento[parada.sitio] = (numero, parada.inicio, 1)
    for indice, sitio in enumerate(problema.sitios):
        # Si la persona lo vio a una hora (fijado o descanso), va a esa hora aunque el voraz lo haya puesto en
        # otra: así, con toda la ruta fijada, la semilla repite el plan que ya tenía.
        if sitio.obligatorio and (indice not in momento or sitio.objetivo is not None):
            hora = sitio.objetivo if sitio.objetivo is not None else problema.dias[sitio.dia or 0].inicio
            # A la misma hora, lo obligatorio va primero.
            momento[indice] = (sitio.dia or 0, hora, 0)
    elegidos = sorted(momento, key=momento.get)
    return elegidos + _resto_por_puntaje(problema, elegidos)


def genetico(problema, parametros=None, semilla=None):
    """Algoritmo genético con torneo, cruce OX, mutación y élite. Con la misma semilla da el mismo plan.

    Por omisión es híbrido (ver `Parametros.sembrados`): nunca queda por debajo del voraz y lo mejora cuando
    hay un orden mejor. Si hay sitios obligatorios, también siembra un orden que los respeta.
    """
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

    sembrados = round(parametros.poblacion * parametros.sembrados)
    poblacion = []
    if sembrados:
        plan_voraz = voraz(problema)
        base = _orden_voraz(problema, plan_voraz)
        if any(s.obligatorio for s in problema.sitios):
            # Mitad de las variaciones de cada semilla: la del voraz y la que respeta lo obligatorio.
            respetuoso = _orden_con_obligatorios(problema, plan_voraz)
            poblacion = [base, respetuoso]
            while len(poblacion) < max(sembrados, 2):
                poblacion.append(_mutar(poblacion[len(poblacion) % 2], azar))
        else:
            poblacion = [base] + [_mutar(base, azar) for _ in range(sembrados - 1)]
    poblacion += [azar.sample(range(n), n) for _ in range(parametros.poblacion - len(poblacion))]
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
