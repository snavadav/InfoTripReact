"""Lugares de OpenStreetMap: descarga con Overpass e interpretación de la respuesta.

Los datos de OpenStreetMap tienen licencia ODbL: hay que dar crédito (la ficha lo hace) y mantener
identificado qué viene de ahí (Destino.osm_id). Se importa de vez en cuando con el comando
`importar_osm`; nunca se consulta en una visita, porque el servidor público pide un uso moderado.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

SERVIDOR = 'https://overpass-api.de/api/interpreter'
AGENTE = 'InfoTrip-proyecto-academico/1.0 (https://github.com/snavadav/InfoTripReact)'
SEGUNDOS_MAXIMOS = 360

# Una sola consulta con los lugares y los límites de los municipios: pedirlos municipio por municipio
# tarda más de 10 minutos y carga de más al servidor. El municipio se calcula después, en local.
CONSULTA = """
[out:json][timeout:300];
area["ISO3166-2"="MX-JAL"][admin_level=4]->.jalisco;
(
  nwr["tourism"~"^(attraction|museum|viewpoint)$"]["name"](area.jalisco);
  nwr["natural"~"^(waterfall|hot_spring|beach)$"]["name"](area.jalisco);
  nwr["waterway"="waterfall"]["name"](area.jalisco);
  nwr["historic"="archaeological_site"]["name"](area.jalisco);
);
out center tags;
rel(area.jalisco)["boundary"="administrative"]["admin_level"="6"];
out geom;
"""

# Etiqueta de OSM → (nombre en una frase, categoría del catálogo o None si no hay una clara).
TIPOS = {
    'museum': ('Museo', 'Ciudad y cultura'),
    'viewpoint': ('Mirador', 'Miradores'),
    'attraction': ('Lugar de interés', None),
    'beach': ('Playa', 'Costa'),
    'waterfall': ('Cascada', 'Naturaleza'),
    'hot_spring': ('Aguas termales', 'Naturaleza'),
    'archaeological_site': ('Sitio arqueológico', 'Arqueología'),
}


class ErrorOverpass(Exception):
    """El servidor no respondió o la respuesta está incompleta: mejor no importar nada."""


def descargar():
    pedido = urllib.request.Request(SERVIDOR, data=urllib.parse.urlencode({'data': CONSULTA}).encode(),
                                    headers={'User-Agent': AGENTE})
    try:
        with urllib.request.urlopen(pedido, timeout=SEGUNDOS_MAXIMOS) as respuesta:
            return json.load(respuesta)
    except urllib.error.HTTPError as error:
        raise ErrorOverpass(f'El servidor respondió {error.code}. Suele estar saturado: prueba más tarde.') from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ErrorOverpass(f'No se pudo conectar con Overpass: {error}') from error
    except ValueError as error:
        raise ErrorOverpass('La respuesta no es JSON válido.') from error


def tipo_de(etiquetas):
    for clave in ('tourism', 'natural', 'waterway', 'historic'):
        if etiquetas.get(clave) in TIPOS:
            return etiquetas[clave]
    return None


def _segmentos(municipio):
    """Tramos del contorno exterior. No importa su orden: la prueba de abajo solo los cuenta."""
    tramos = []
    for miembro in municipio.get('members', []):
        if miembro.get('type') == 'way' and miembro.get('role') == 'outer' and miembro.get('geometry'):
            puntos = [(punto['lat'], punto['lon']) for punto in miembro['geometry']]
            tramos += zip(puntos, puntos[1:])
    return tramos


def _dentro(latitud, longitud, tramos):
    """Un punto está dentro si una línea trazada desde él cruza el contorno un número impar de veces."""
    dentro = False
    for (y1, x1), (y2, x2) in tramos:
        if (y1 > latitud) != (y2 > latitud) and longitud < (x2 - x1) * (latitud - y1) / (y2 - y1) + x1:
            dentro = not dentro
    return dentro


def _es_municipio(elemento):
    return elemento['type'] == 'relation' and elemento.get('tags', {}).get('boundary') == 'administrative'


def interpretar(datos):
    """Convierte la respuesta en lugares con su municipio. Omite lo que no tiene municipio o coordenadas."""
    if datos.get('remark'):
        raise ErrorOverpass(f"La respuesta está incompleta: {datos['remark']}")
    elementos = datos.get('elements', [])
    municipios = [(e['tags'].get('name', ''), _segmentos(e)) for e in elementos if _es_municipio(e)]
    if not municipios:
        raise ErrorOverpass('La respuesta no trae los límites de los municipios.')
    lugares, omitidos, vistos = [], 0, set()
    for elemento in elementos:
        if _es_municipio(elemento):
            continue
        clave = f"{elemento['type']}/{elemento['id']}"
        etiquetas = elemento.get('tags', {})
        centro = elemento.get('center', elemento)
        tipo = tipo_de(etiquetas)
        if clave in vistos or not etiquetas.get('name') or not tipo or 'lat' not in centro:
            omitidos += 1
            continue
        vistos.add(clave)
        municipio = next((nombre for nombre, tramos in municipios
                          if _dentro(centro['lat'], centro['lon'], tramos)), None)
        if not municipio:
            omitidos += 1
            continue
        lugares.append({
            'osm_id': clave, 'nombre': etiquetas['name'].strip(), 'tipo': tipo, 'municipio': municipio,
            'latitud': round(centro['lat'], 6), 'longitud': round(centro['lon'], 6),
            'descripcion': (etiquetas.get('description:es') or etiquetas.get('description') or '').strip(),
        })
    return lugares, omitidos
