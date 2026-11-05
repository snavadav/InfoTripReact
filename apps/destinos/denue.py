"""Negocios del DENUE (Directorio Estadístico Nacional de Unidades Económicas), del INEGI.

Sus términos permiten reutilizar y transformar los datos si se cita la fuente, se avisa de los cambios y no se
presenta como postura del INEGI. Se importan de vez en cuando con `importar_denue`, nunca en una visita, porque
la clave va en la dirección de cada consulta: no debe aparecer en registros, errores ni en el navegador.
"""
import json
import re
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.utils.text import slugify

BASE = 'https://www.inegi.org.mx/app/api/denue/v1/consulta/'
AGENTE = 'InfoTrip-proyecto-academico/1.0 (https://github.com/snavadav/InfoTripReact)'
JALISCO = '14'
POR_PAGINA = 2000
SEGUNDOS_MAXIMOS = 180
# Una descarga con mucho menos de lo que el propio DENUE cuenta está incompleta: mejor no importar nada.
PROPORCION_MINIMA = 0.9
ATRIBUCION = 'Fuente: INEGI, Directorio Estadístico Nacional de Unidades Económicas (DENUE)'

# (actividad para contar, ruta sector/subsector/rama/clase). Solo lo que le sirve a quien viaja:
# 40 mil tiendas de abarrotes o estéticas harían inútil el mapa.
ACTIVIDADES = [
    ('721', '72/721/0/0'), ('722', '72/722/0/0'), ('468411', '46/468/4684/468411'), ('464111', '46/464/4641/464111'),
    ('464112', '46/464/4641/464112'), ('522110', '52/522/5221/522110'), ('462111', '46/462/4621/462111'),
    ('462112', '46/462/4621/462112'), ('462210', '46/462/4622/462210'), ('465912', '46/465/4659/465912'),
    ('461211', '46/461/4612/461211'),
]
SUBTIPO_DE_CLASE = {
    '721111': 'hotel', '721112': 'motel', '721190': 'guest_house', '721311': 'guest_house', '721312': 'apartment',
    '468411': 'fuel', '464111': 'pharmacy', '464112': 'pharmacy', '522110': 'bank', '462111': 'supermarket',
    '462112': 'convenience', '462210': 'department_store', '465912': 'craft', '461211': 'alcohol',
}
# En la zona metropolitana hay de sobra: los negocios de hasta 5 personas taparían todo el mapa.
ZONA_METROPOLITANA = {'guadalajara', 'zapopan', 'san-pedro-tlaquepaque', 'tonala', 'tlajomulco-de-zuniga', 'el-salto'}
ESTRATO_MINIMO = '0 a 5 personas'
GENERICOS = {
    'abarrotes', 'artesanias', 'bar', 'cafe', 'cafeteria', 'cantina', 'cenaduria', 'cocina-economica', 'comida',
    'farmacia', 'fonda', 'gasolinera', 'hotel', 'lonche', 'loncheria', 'mariscos', 'motel', 'pizzeria', 'pollos',
    'restaurante', 'restaurant', 'sin-nombre', 'tacos', 'taqueria', 'tortas', 'tortas-ahogadas', 'vinos-y-licores',
    'antojitos-mexicanos', 'menuderia', 'novedades', 'novedades-y-regalos', 'regalos', 'regalos-y-novedades',
    'tacos-de-barbacoa', 'tienda-de-regalos', 'venta-de-comida', 'venta-de-tacos',
}
# El DENUE los clasifica como comida o comercio, pero un viajero no puede o no vendría a ellos.
NO_PARA_VIAJEROS = ('comedor-', 'cooperativa', 'club-de-nutricion', 'herbalife', 'nutricion', 'cafeteria-escolar',
                    'escuela', 'primaria', 'secundaria')
MINUSCULAS = {'De', 'Del', 'La', 'Las', 'El', 'Los', 'Y', 'E', 'En', 'A'}


class ErrorDenue(Exception):
    """El servicio no respondió o la descarga está incompleta. Nunca incluye la dirección: lleva la clave."""


def clave():
    if not settings.DENUE_TOKEN:
        raise ErrorDenue('Falta DENUE_TOKEN en el archivo .env.')
    return settings.DENUE_TOKEN


def _pedir(ruta):
    peticion = urllib.request.Request(f'{BASE}{ruta}/{clave()}', headers={'User-Agent': AGENTE})
    try:
        with urllib.request.urlopen(peticion, timeout=SEGUNDOS_MAXIMOS) as respuesta:
            return json.loads(respuesta.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as error:
        raise ErrorDenue(f'El DENUE respondió {error.code}.') from None
    except (urllib.error.URLError, TimeoutError):
        raise ErrorDenue('No se pudo conectar con el DENUE.') from None
    except ValueError:
        return None  # Sin resultados, el servicio no siempre responde con JSON.


def contar(actividad):
    filas = _pedir(f'Cuantificar/{actividad}/{JALISCO}/0')
    return sum(int(fila['Total']) for fila in filas) if filas else 0


def descargar(espera=1):
    """Todas las páginas de cada actividad. Si falta una parte importante, no devuelve nada."""
    registros = []
    for actividad, ruta in ACTIVIDADES:
        esperados = contar(actividad)
        de_esta, inicio = [], 1
        while True:
            pagina = _pedir(f'BuscarAreaAct/{JALISCO}/0/0/0/0/{ruta}/0/{inicio}/{inicio + POR_PAGINA - 1}/0')
            if not pagina:
                break
            de_esta += pagina
            if len(pagina) < POR_PAGINA:
                break
            inicio += POR_PAGINA
            time.sleep(espera)
        if len(de_esta) < esperados * PROPORCION_MINIMA:
            raise ErrorDenue(f'Actividad {actividad}: llegaron {len(de_esta)} de {esperados}. No se importó nada.')
        registros += de_esta
        time.sleep(espera)
    return registros


def nombre_legible(texto):
    """El DENUE usa mayúsculas. Es la única transformación del nombre, y /creditos/ lo avisa."""
    palabras = re.sub(r'\s+', ' ', texto).strip().title().replace("'S", "'s").split(' ')
    return ' '.join(p.lower() if i and p in MINUSCULAS else p for i, p in enumerate(palabras))


def es_generico(nombre):
    slug = slugify(nombre)
    return not slug or slug in GENERICOS or 'sin-nombre' in slug or any(texto in slug for texto in NO_PARA_VIAJEROS)


def subtipo_de(registro):
    clase = str(registro.get('CLASE_ACTIVIDAD_ID', ''))
    if clase in SUBTIPO_DE_CLASE:
        return SUBTIPO_DE_CLASE[clase]
    if not clase.startswith('722') or clase.startswith('7223'):
        return None  # Comedores industriales y banquetes no reciben visitas; otros hospedajes tampoco aplican.
    descripcion = registro.get('Clase_actividad', '').lower()
    if clase.startswith('7224') or 'bares' in descripcion or 'centros nocturnos' in descripcion:
        return 'bar'
    if 'café' in descripcion or 'cafeter' in descripcion:
        return 'cafe'
    if clase == '722511':
        return 'restaurant'
    rapida = ('autoservicio', 'para llevar', 'tacos', 'pizzas', 'hamburguesas', 'antojitos', 'pollos')
    if any(palabra in descripcion for palabra in rapida):
        return 'fast_food'
    return 'restaurant'


def _municipio(registro):
    partes = [parte.strip() for parte in registro.get('Ubicacion', '').split(',')]
    return partes[1] if len(partes) >= 3 else ''


def _direccion(registro):
    calle = ' '.join(registro.get(campo, '').strip() for campo in ('Tipo_vialidad', 'Calle', 'Num_Exterior')).strip()
    calle = re.sub(r'\s+', ' ', calle)
    if not registro.get('Calle', '').strip() or 'NINGUNO' in calle.upper():
        return ''
    colonia = registro.get('Colonia', '').strip()
    return nombre_legible(f'{calle}, {colonia}' if colonia else calle)[:300]


def _sitio_web(valor):
    sitio = valor.strip().lower()
    if not sitio or not re.fullmatch(r'(https?://)?[a-z0-9.-]+\.[a-z]{2,}(/\S*)?', sitio) or len(sitio) > 290:
        return ''
    return sitio if sitio.startswith('http') else f'https://{sitio}'


def interpretar(registros, tipo_de_subtipo):
    """Convierte a campos de Lugar. El correo y la razón social no se traen: pueden ser datos de una persona."""
    lugares, omitidos, vistos = [], 0, set()
    for registro in registros:
        identificador, subtipo = str(registro.get('Id', '')), subtipo_de(registro)
        nombre = nombre_legible(registro.get('Nombre', ''))
        municipio = _municipio(registro)
        try:
            latitud, longitud = round(float(registro['Latitud']), 6), round(float(registro['Longitud']), 6)
        except (KeyError, TypeError, ValueError):
            latitud = None
        fuera = subtipo in ('restaurant', 'fast_food', 'cafe', 'bar') and registro.get('Estrato') == ESTRATO_MINIMO \
            and slugify(municipio) in ZONA_METROPOLITANA
        if (not identificador or identificador in vistos or not subtipo or latitud is None or es_generico(nombre)
                or registro.get('Tipo', 'Fijo') != 'Fijo' or fuera or not municipio):
            omitidos += 1
            continue
        vistos.add(identificador)
        lugares.append({
            'denue_id': identificador, 'nombre': nombre[:200], 'tipo': tipo_de_subtipo[subtipo], 'subtipo': subtipo,
            'municipio': municipio, 'latitud': latitud, 'longitud': longitud, 'direccion': _direccion(registro),
            # Algunos llegan como número decimal: 3310018621.0
            'telefono': re.sub(r'\.0$', '', registro.get('Telefono', '').strip())[:60],
            'sitio_web': _sitio_web(registro.get('Sitio_internet', '')),
        })
    return lugares, omitidos
