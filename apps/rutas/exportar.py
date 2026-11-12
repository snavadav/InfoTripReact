"""Llevar una ruta a otras aplicaciones: Google Maps por día y un calendario .ics."""
from urllib.parse import urlencode

from django.conf import settings
from django.utils import timezone

# Google Maps acepta hasta 9 paradas intermedias en un enlace; más allá las ignora.
MAXIMO_WAYPOINTS = 9
ZONA = 'America/Mexico_City'


# ── Google Maps por día ───────────────────────────────────────
def _punto(lugar):
    return f'{lugar["latitud"]},{lugar["longitud"]}'


def enlace_google_maps(paradas, origen=None, destino=None):
    """{'url', 'incluidas', 'total'}: la ruta del día en Google Maps.

    Sin `origen`, Google sale desde donde esté quien abre el enlace. Si las paradas no caben, el enlace
    llega hasta donde alcanza y lo dice en `incluidas`.
    """
    puntos = [_punto(p['destino']) for p in paradas]
    if not puntos:
        return None
    if destino is None:
        destino, intermedios = puntos[-1], puntos[:-1]
    else:
        intermedios = puntos
    if len(intermedios) > MAXIMO_WAYPOINTS:
        destino, intermedios = intermedios[MAXIMO_WAYPOINTS], intermedios[:MAXIMO_WAYPOINTS]
    consulta = {'api': 1}
    if origen:
        consulta['origin'] = origen
    consulta['destination'] = destino
    if intermedios:
        consulta['waypoints'] = '|'.join(intermedios)
    consulta['travelmode'] = 'driving'
    incluidas = min(len(puntos), MAXIMO_WAYPOINTS + 1)
    return {'url': 'https://www.google.com/maps/dir/?' + urlencode(consulta), 'incluidas': incluidas,
            'total': len(puntos)}


def con_enlaces(plan, regresar, origen_publico=True):
    """Agrega a cada día su enlace de Google Maps, de donde empieza el día a donde termina.

    Si se sale desde la ubicación de la persona (`origen_publico=False`), el enlace no la lleva: Google
    usa la ubicación del teléfono que lo abre. El destino del viaje es público (un destino o un municipio):
    en solo ida el último día termina ahí, y quedándose en el destino cada día empieza (desde el 2) y termina ahí.
    """
    origen = plan['origen']
    viaje = plan.get('viaje') or {}
    modo = viaje.get('modo', 'circulo')
    final = _punto(viaje['destino']) if viaje.get('destino') and modo in ('ida', 'base') else None
    inicio = _punto(origen) if origen_publico and 'latitud' in origen else None
    anterior = inicio
    for numero, dia in enumerate(plan['dias']):
        ultimo = numero == len(plan['dias']) - 1
        if modo == 'base' and numero:
            anterior = final
        if final and (modo == 'base' or ultimo):
            vuelta = final
        else:
            vuelta = inicio if ultimo and regresar else None
        dia['google_maps'] = enlace_google_maps(dia['paradas'], anterior, vuelta)
        if dia['paradas']:
            anterior = _punto(dia['paradas'][-1]['destino'])
    return plan


def duracion(minutos):
    horas, resto = divmod(minutos, 60)
    if not horas:
        return f'{resto} min'
    return f'{horas} h {resto} min' if resto else f'{horas} h'


# ── Calendario (.ics) ─────────────────────────────────────────
def _escapar(texto):
    return (str(texto).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            .replace('\r\n', '\\n').replace('\n', '\\n'))


def _plegar(linea):
    """Corta las líneas a 75 octetos, como pide RFC 5545, sin partir un carácter UTF-8."""
    partes, actual = [], ''
    for caracter in linea:
        limite = 75 if not partes else 74
        if len((actual + caracter).encode('utf-8')) > limite:
            partes.append(actual)
            actual = caracter
        else:
            actual += caracter
    partes.append(actual)
    return '\r\n '.join(partes)


def _fecha_hora(fecha, hora):
    return f'{fecha.replace("-", "")}T{hora.replace(":", "")}00'


def calendario_ics(ruta, url_publica):
    """Un evento por parada, con su hora de llegada y de salida, en la hora del centro de México."""
    sello = timezone.now().strftime('%Y%m%dT%H%M%SZ')
    lineas = [
        'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//InfoTrip//Planeador de rutas//ES', 'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH', f'X-WR-CALNAME:{_escapar(ruta.titulo)}', f'X-WR-TIMEZONE:{ZONA}',
        # Desde 2022 el centro de México no cambia de horario: UTC−6 todo el año.
        'BEGIN:VTIMEZONE', f'TZID:{ZONA}', 'BEGIN:STANDARD', 'DTSTART:19700101T000000', 'TZOFFSETFROM:-0600',
        'TZOFFSETTO:-0600', 'TZNAME:CST', 'END:STANDARD', 'END:VTIMEZONE',
    ]
    for numero, dia in enumerate(ruta.plan['dias'], start=1):
        for orden, parada in enumerate(dia['paradas'], start=1):
            destino = parada['destino']
            precio = 'precio desconocido' if parada['precio'] is None else (
                f'entrada ${parada["precio"]} por persona' if float(parada['precio']) else 'entrada libre')
            notas = [f'Día {numero}, parada {orden} de tu ruta en InfoTrip.',
                     f'Llegas a las {parada["llegada"]}; visita de {duracion(parada["visita_min"])}; {precio}.']
            if not parada['horario_confirmado']:
                notas.append('Horario no confirmado: confírmalo antes de ir.')
            if orden == 1 and (dia.get('desayuno') or {}).get('comida'):
                notas.append(f'Antes, a desayunar ({dia["desayuno"]["hora"]}): {dia["desayuno"]["comida"]["nombre"]}.')
            if parada.get('comida'):
                notas.append(f'Después, a comer: {parada["comida"]["nombre"]}.')
            if orden == len(dia['paradas']) and (dia.get('cena') or {}).get('comida'):
                notas.append(f'Al terminar, a cenar ({dia["cena"]["hora"]}): {dia["cena"]["comida"]["nombre"]}.')
            notas.append('Horas y tiempos de manejo estimados.')
            notas.append(f'Ficha: {settings.PUBLIC_BASE_URL}{destino["url"]}')
            lineas += [
                'BEGIN:VEVENT', f'UID:{ruta.enlace}-{numero}-{orden}@infotrip', f'DTSTAMP:{sello}',
                f'DTSTART;TZID={ZONA}:{_fecha_hora(dia["fecha"], parada["inicio"])}',
                f'DTEND;TZID={ZONA}:{_fecha_hora(dia["fecha"], parada["salida"])}',
                f'SUMMARY:{_escapar(destino["nombre"])}',
                f'LOCATION:{_escapar(destino["nombre"] + ", " + destino["municipio"] + ", Jalisco")}',
                f'GEO:{destino["latitud"]};{destino["longitud"]}',
                f'DESCRIPTION:{_escapar(chr(10).join(notas))}', f'URL:{url_publica}', 'END:VEVENT',
            ]
    lineas.append('END:VCALENDAR')
    return '\r\n'.join(_plegar(linea) for linea in lineas) + '\r\n'
