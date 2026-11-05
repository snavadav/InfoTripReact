"""Lee horarios y precios escritos en español, como los publica el Sistema de Información Cultural.

No depende de Django ni de otras apps: recibe texto y devuelve datos. Si un texto no se entiende, devuelve
None y el planeador lo trata como "sin horario confirmado" en vez de adivinar.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
_DIA = r'(lunes|martes|miercoles|jueves|viernes|sabado|domingo)s?'
# "martes a domingo", "lunes y sabados", "todos los dias".
_RANGO_DIAS = re.compile(rf'{_DIA}\s+a\s+{_DIA}')
_LISTA_DIAS = re.compile(rf'{_DIA}(?:\s*(?:,|y)\s*{_DIA})*')
_TODOS = re.compile(r'todos los dias(?: del ano)?|diario')
_HORA = r'(\d{1,2})(?:[:.](\d{2}))?'
_INTERVALO = re.compile(rf'{_HORA}\s*(?:h\w*\.?)?\s*(?:a|-)\s*{_HORA}')
# Recorridos guiados a horas fijas: "11, 12, 13 y 15 h".
_HORAS_SUELTAS = re.compile(r'\b(\d{1,2})(?:[:.](\d{2}))?\b')


def normalizar(texto):
    sin_acentos = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = sin_acentos.lower()
    # "Lunes a. Sábado", "y. Sábado": puntos que dejó la fuente en medio de la frase.
    texto = re.sub(r'\b(a|y)\.\s', r'\1 ', texto)
    # "Martes-Domingo".
    texto = re.sub(rf'{_DIA}\s*-\s*{_DIA}', r'\1 a \2', texto)
    return texto


@dataclass
class Horario:
    """Minutos desde medianoche en que abre y cierra, por día de la semana (0 = lunes)."""
    dias: dict = field(default_factory=dict)
    # Solo con recorridos a horas fijas: la ventana va de la primera a la última salida.
    guiado: bool = False

    def intervalos(self, dia_semana):
        return self.dias.get(dia_semana, [])

    def abre(self, dia_semana):
        return bool(self.intervalos(dia_semana))


def _dias_de(coincidencia_texto):
    texto = coincidencia_texto
    if _TODOS.fullmatch(texto):
        return list(range(7))
    rango = _RANGO_DIAS.fullmatch(texto)
    if rango:
        inicio, fin = DIAS.index(rango.group(1)), DIAS.index(rango.group(2))
        # "viernes a miércoles" da la vuelta a la semana.
        return [(inicio + i) % 7 for i in range((fin - inicio) % 7 + 1)]
    return [DIAS.index(d) for d in re.findall(_DIA, texto)]


def _minutos(hora, minuto):
    return int(hora) * 60 + int(minuto or 0)


def _intervalos(segmento):
    if 'cerrado' in segmento:
        return [], False
    resultado = []
    for h1, m1, h2, m2 in _INTERVALO.findall(segmento):
        inicio, fin = _minutos(h1, m1), _minutos(h2, m2)
        if 0 <= inicio < fin <= 24 * 60:
            resultado.append((inicio, fin))
    if resultado:
        return resultado, False
    sueltas = [_minutos(h, m) for h, m in _HORAS_SUELTAS.findall(segmento) if int(h) <= 23]
    if len(sueltas) >= 2:
        # Se entra a la hora de cada recorrido; el último dura aproximadamente una hora.
        return [(min(sueltas), max(sueltas) + 60)], True
    return None, False


def leer_horario(texto):
    """Horario a partir del texto, o None si no se entiende o solo se visita con cita."""
    if not texto:
        return None
    texto = normalizar(texto)
    if 'previa cita' in texto:
        return None
    if re.search(r'\b24 horas\b', texto):
        return Horario({d: [(0, 24 * 60)] for d in range(7)})
    patron = re.compile(rf'{_TODOS.pattern}|{_RANGO_DIAS.pattern}|{_LISTA_DIAS.pattern}')
    coincidencias = list(patron.finditer(texto))
    horario = Horario()
    # Días que aún esperan su hora: "lunes a viernes y sábado de 9 a 14".
    pendientes = []
    for i, actual in enumerate(coincidencias):
        fin = coincidencias[i + 1].start() if i + 1 < len(coincidencias) else len(texto)
        segmento = texto[actual.end():fin]
        dias = pendientes + _dias_de(actual.group(0))
        intervalos, guiado = _intervalos(segmento)
        if intervalos is None:
            pendientes = dias if not re.search(r'\d', segmento) else []
            continue
        pendientes = []
        horario.guiado |= guiado
        # Lo que se dice después corrige a lo anterior: "martes a domingo de 9:30 a 17:30. Sábado de 9 a 16".
        for dia in dias:
            if intervalos:
                horario.dias[dia] = intervalos
            else:
                horario.dias.pop(dia, None)
    return horario if horario.dias else None


@dataclass
class Precio:
    """Entrada general para una persona adulta; None si la fuente no la da."""
    adulto: Decimal | None
    # Días en que la entrada general es libre ("Domingos: entrada libre").
    dias_gratis: set = field(default_factory=set)

    def para(self, dia_semana):
        if dia_semana in self.dias_gratis:
            return Decimal('0')
        return self.adulto


_MONTO = r'\$\s*(\d+(?:\.\d{1,2})?)'
_GENERAL = re.compile(rf'general\s*:?\s*{_MONTO}')
_ADULTO = re.compile(rf'adultos?\s*[-:]?\s*{_MONTO}')
_PARA_ADULTOS = re.compile(rf'{_MONTO}\s*(?:pesos\s*)?(?:para\s+)?adultos?')
_CUALQUIERA = re.compile(_MONTO)
_LIBRE = re.compile(r'entrada (?:es )?(?:libre|gratuita)|cuota voluntaria|cooperacion voluntaria')
_DIA_LIBRE = re.compile(rf'{_DIA}\s*:?\s*entrada libre|entrada libre\s*:?\s*{_DIA}')


def leer_precio(texto):
    """Precio de la entrada general a partir del texto, o None si no se entiende."""
    if not texto:
        return None
    texto = normalizar(texto)
    dias_gratis = {DIAS.index(a or b) for a, b in _DIA_LIBRE.findall(texto)}
    for patron in (_GENERAL, _ADULTO, _PARA_ADULTOS, _CUALQUIERA):
        encontrado = patron.search(texto)
        if encontrado:
            monto = next(g for g in encontrado.groups() if g)
            return Precio(Decimal(monto), dias_gratis)
    if dias_gratis:
        # "Domingo entrada libre": el resto de los días no sabemos cuánto cuesta.
        return Precio(None, dias_gratis)
    if _LIBRE.search(texto):
        return Precio(Decimal('0'))
    return None
