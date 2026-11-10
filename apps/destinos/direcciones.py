"""Direcciones con OpenStreetMap: sugerencias al escribir, búsqueda de una dirección y de un punto a su dirección.

El navegador solo habla con nuestro dominio; desde aquí se consulta al proveedor (por defecto Photon para
las sugerencias y Nominatim para lo demás). Reglas que se cumplen siempre (detalle en docs/direcciones.md):
- Nominatim no se usa para autocompletar (su política lo prohíbe) y recibe como máximo una petición por
  segundo entre todos los procesos, con un turno en la caché compartida (Redis).
- Cada petición se identifica con un User-Agent con contacto y, a Nominatim, con `email`.
- Las respuestas se guardan 30 días por consulta normalizada; no se guarda quién buscó qué. Las claves de
  la caché son huellas, y las coordenadas llegan redondeadas a 5 decimales y nunca se escriben en el registro.
- El proveedor se cambia solo con configuración (`GEOCODIFICACION_PROVEEDOR` y sus URL).

Datos: © colaboradores de OpenStreetMap, licencia ODbL.
"""
import hashlib
import json
import logging
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.utils.module_loading import import_string
from drf_spectacular.utils import extend_schema
from redis.exceptions import RedisError
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.core.limites import _Tolerante

registro = logging.getLogger('infotrip.direcciones')

SITIO = 'https://infotrip.online'
MAXIMO_RESULTADOS = 5
MINIMO_PARA_SUGERIR = 3
MAXIMO_CONSULTA = 200
DECIMALES = 5  # unos 1.1 m: suficiente para una dirección y no más preciso de lo necesario
SEGUNDOS_MAXIMOS = 5
DIAS_EN_CACHE = 30
# Jalisco con un pequeño margen: (oeste, sur, este, norte).
JALISCO = (-105.75, 18.85, -101.45, 22.80)
ESPERA_POR_TURNO = 0.2
INTENTOS_POR_TURNO = 8  # hasta ~1.6 s esperando turno antes de responder 503
ATRIBUCION = '© colaboradores de OpenStreetMap (ODbL)'
NO_DISPONIBLE = 'El buscador de direcciones no responde ahora. Puedes marcar el punto directamente en el mapa.'
OCUPADO = ('Hay muchas búsquedas de direcciones en este momento. '
           'Intenta de nuevo en unos segundos o marca el punto en el mapa.')


class ErrorDeProveedor(Exception):
    """El servicio externo falló, tardó demasiado o no dio turno: la vista responde 503 con un mensaje amable."""


class SinTurno(ErrorDeProveedor):
    pass


# ─── Utilidades ───────────────────────────────────────────────

def normalizar(texto):
    """Minúsculas, sin acentos y con espacios colapsados: «  Av. JUÁREZ  10 » → «av. juarez 10»."""
    sin_acentos = ''.join(c for c in unicodedata.normalize('NFKD', texto) if not unicodedata.combining(c))
    return ' '.join(sin_acentos.lower().split())


def redondear(valor):
    return round(float(valor), DECIMALES)


def en_jalisco(lat, lon):
    oeste, sur, este, norte = JALISCO
    return sur <= lat <= norte and oeste <= lon <= este


def contacto():
    return getattr(settings, 'CONTACTO_GEOCODIFICACION', '') or ''


def agente():
    datos = f'+{SITIO}; {contacto()}' if contacto() else f'+{SITIO}'
    return f'InfoTrip/1.0 ({datos})'


def pedir_json(url, parametros):
    pedido = urllib.request.Request(f'{url}?{urllib.parse.urlencode(parametros)}',
                                    headers={'User-Agent': agente(), 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(pedido, timeout=SEGUNDOS_MAXIMOS) as respuesta:
            return json.load(respuesta)
    except urllib.error.HTTPError as error:
        # Sin la URL: lleva la consulta o las coordenadas.
        registro.warning('El servicio de direcciones respondió %s', error.code)
        raise ErrorDeProveedor(NO_DISPONIBLE) from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        registro.warning('No se pudo consultar el servicio de direcciones: %s', type(error).__name__)
        raise ErrorDeProveedor(NO_DISPONIBLE) from None
    except ValueError:
        registro.warning('El servicio de direcciones no devolvió JSON válido')
        raise ErrorDeProveedor(NO_DISPONIBLE) from None


def esperar_turno(servicio):
    """Como máximo una petición por intervalo entre todos los procesos: `cache.add` es atómico en Redis (SET NX EX)."""
    intervalo = getattr(settings, 'GEOCODIFICACION_SEGUNDOS_ENTRE_PETICIONES', 1)
    if not intervalo:
        return
    clave = f'direcciones:turno:{servicio}'
    for intento in range(INTENTOS_POR_TURNO):
        try:
            if cache.add(clave, 1, timeout=intervalo):
                return
        except (RedisError, OSError):
            # Sin la caché compartida no se puede garantizar el límite: mejor no consultar.
            registro.error('Sin caché compartida no se puede respetar el límite del servicio de direcciones')
            raise SinTurno(NO_DISPONIBLE) from None
        if intento < INTENTOS_POR_TURNO - 1:
            time.sleep(ESPERA_POR_TURNO)
    raise SinTurno(OCUPADO)


def resultado(etiqueta, lat, lon, calle='', colonia='', municipio='', estado=''):
    return {'etiqueta': etiqueta, 'calle': calle, 'colonia': colonia, 'municipio': municipio, 'estado': estado,
            'lat': redondear(lat), 'lon': redondear(lon)}


def solo_jalisco(resultados):
    """Dentro del recuadro y, si el proveedor dice el estado, que sea Jalisco: el recuadro roza estados vecinos."""
    return [r for r in resultados if en_jalisco(r['lat'], r['lon'])
            and (not r['estado'] or normalizar(r['estado']) == 'jalisco')][:MAXIMO_RESULTADOS]


# ─── Proveedores ──────────────────────────────────────────────

class Proveedor:
    """Interfaz pequeña: cada método devuelve una lista de resultados normalizados (ver `resultado`)."""
    nombre = 'base'

    def sugerir(self, consulta):
        raise NotImplementedError

    def buscar(self, consulta):
        raise NotImplementedError

    def inversa(self, lat, lon):
        raise NotImplementedError


class Desactivado(Proveedor):
    """Sin servicio externo: nunca sale a la red. Lo usan las pruebas y quien no quiera geocodificación."""
    nombre = 'desactivado'

    def sugerir(self, consulta):
        return []

    def buscar(self, consulta):
        return []

    def inversa(self, lat, lon):
        return []


def _union(*partes):
    vistas, unidas = set(), []
    for parte in partes:
        if parte and parte not in vistas:
            vistas.add(parte)
            unidas.append(parte)
    return ', '.join(unidas)


def desde_photon(rasgo):
    p = rasgo.get('properties') or {}
    lon, lat = (rasgo.get('geometry') or {}).get('coordinates', (None, None))[:2]
    if lat is None or lon is None or (p.get('countrycode') or '').upper() not in ('', 'MX'):
        return None
    calle = ' '.join(filter(None, [p.get('street'), p.get('housenumber')]))
    if not calle and p.get('osm_key') == 'highway':
        calle = p.get('name', '')
    colonia = p.get('district') or p.get('locality') or ''
    municipio = p.get('city') or p.get('county') or ''
    nombre = p.get('name') if p.get('name') != calle else ''
    etiqueta = _union(nombre, calle, colonia, municipio, p.get('state'))
    return resultado(etiqueta, lat, lon, calle, colonia, municipio, p.get('state') or '')


def desde_nominatim(lugar):
    d = lugar.get('address') or {}
    try:
        lat, lon = float(lugar['lat']), float(lugar['lon'])
    except (KeyError, TypeError, ValueError):
        return None
    if (d.get('country_code') or 'mx').lower() != 'mx':
        return None
    calle = ' '.join(filter(None, [d.get('road') or d.get('pedestrian') or d.get('footway'), d.get('house_number')]))
    colonia = d.get('neighbourhood') or d.get('suburb') or d.get('quarter') or d.get('hamlet') or ''
    municipio = d.get('city') or d.get('town') or d.get('village') or d.get('municipality') or d.get('county') or ''
    nombre = lugar.get('name') or ''
    if nombre and nombre in calle:
        nombre = ''
    etiqueta = _union(nombre, calle, colonia, municipio, d.get('state'))
    return resultado(etiqueta or lugar.get('display_name', ''), lat, lon, calle, colonia, municipio,
                     d.get('state') or '')


class OSMPublico(Proveedor):
    """Photon (komoot) para sugerir y Nominatim para buscar y la inversa. Con otra URL sirve un Nominatim propio
    o uno compatible (LocationIQ: añade `GEOCODIFICACION_CLAVE`)."""
    nombre = 'osm'

    @property
    def nominatim(self):
        return settings.GEOCODIFICACION_NOMINATIM_URL.rstrip('/')

    @property
    def photon(self):
        return settings.GEOCODIFICACION_PHOTON_URL

    def _nominatim(self, ruta, parametros):
        parametros = {**parametros, 'format': 'jsonv2', 'addressdetails': 1, 'accept-language': 'es'}
        if contacto():
            parametros['email'] = contacto()
        if getattr(settings, 'GEOCODIFICACION_CLAVE', ''):
            parametros['key'] = settings.GEOCODIFICACION_CLAVE
        esperar_turno('nominatim')
        return pedir_json(f'{self.nominatim}/{ruta}', parametros)

    def sugerir(self, consulta):
        oeste, sur, este, norte = JALISCO
        datos = pedir_json(self.photon, {'q': consulta, 'limit': MAXIMO_RESULTADOS * 2,
                                         'bbox': f'{oeste},{sur},{este},{norte}'})
        return [r for r in map(desde_photon, (datos or {}).get('features') or []) if r]

    def buscar(self, consulta):
        oeste, sur, este, norte = JALISCO
        datos = self._nominatim('search', {'q': consulta, 'limit': MAXIMO_RESULTADOS, 'countrycodes': 'mx',
                                           'viewbox': f'{oeste},{norte},{este},{sur}', 'bounded': 1})
        return [r for r in map(desde_nominatim, datos if isinstance(datos, list) else []) if r]

    def inversa(self, lat, lon):
        datos = self._nominatim('reverse', {'lat': lat, 'lon': lon, 'zoom': 18})
        if not isinstance(datos, dict) or 'error' in datos:
            return []
        encontrado = desde_nominatim(datos)
        return [encontrado] if encontrado else []


def proveedor():
    return import_string(settings.GEOCODIFICACION_PROVEEDOR)()


# ─── Caché ────────────────────────────────────────────────────

def con_cache(operacion, llave, consultar):
    """Guarda 30 días por consulta. La clave es una huella: en Redis no queda legible qué se buscó."""
    actual = proveedor()
    huella = hashlib.sha256(f'{actual.nombre}|{operacion}|{llave}'.encode()).hexdigest()[:32]
    clave = f'direcciones:{operacion}:{huella}'
    try:
        guardado = cache.get(clave)
    except (RedisError, OSError):
        guardado = None
    if guardado is not None:
        return guardado
    encontrados = solo_jalisco(consultar(actual))
    try:
        cache.set(clave, encontrados, timeout=DIAS_EN_CACHE * 24 * 3600)
    except (RedisError, OSError):
        pass
    return encontrados


def sugerir(consulta):
    return con_cache('sugerir', normalizar(consulta), lambda p: p.sugerir(' '.join(consulta.split())))


def buscar(consulta):
    return con_cache('buscar', normalizar(consulta), lambda p: p.buscar(' '.join(consulta.split())))


def inversa(lat, lon):
    lat, lon = redondear(lat), redondear(lon)
    if not en_jalisco(lat, lon):
        return []
    return con_cache('inversa', f'{lat:.{DECIMALES}f},{lon:.{DECIMALES}f}', lambda p: p.inversa(lat, lon))


# ─── API ──────────────────────────────────────────────────────

class _Limite(_Tolerante, UserRateThrottle):
    """Por usuario si entró y, si no, por IP."""


class LimiteSugerir(_Limite):
    # Con la espera al escribir, una persona hace unas cuantas por dirección.
    scope = 'direcciones_sugerir'
    rate = '60/min'


class LimiteBuscar(_Limite):
    scope = 'direcciones_buscar'
    rate = '20/min'


class LimiteInversa(_Limite):
    scope = 'direcciones_inversa'
    rate = '30/min'


class ConsultaSerializer(serializers.Serializer):
    q = serializers.CharField(max_length=MAXIMO_CONSULTA, trim_whitespace=True)


class PuntoSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class DireccionSerializer(serializers.Serializer):
    etiqueta = serializers.CharField()
    calle = serializers.CharField()
    colonia = serializers.CharField()
    municipio = serializers.CharField()
    estado = serializers.CharField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()


class _Direcciones(APIView):
    permission_classes = [AllowAny]

    def responder(self, consultar):
        try:
            encontrados = consultar()
        except ErrorDeProveedor as error:
            respuesta = Response({'detail': str(error)}, status=503, headers={'Retry-After': '5'})
            # Ya quedó un aviso propio, sin la consulta: que Django no lo repita como error (y Sentry no lo
            # cuente como fallo nuestro cada vez que el servicio externo se satura).
            respuesta._has_been_logged = True
            return respuesta
        # Privado: el navegador no debe guardar en su caché compartida lo que buscó la persona.
        return Response(encontrados, headers={'Cache-Control': 'private, max-age=300'})


class SugerirView(_Direcciones):
    """GET: sugerencias mientras se escribe (Photon). Menos de 3 caracteres devuelve una lista vacía."""
    throttle_classes = [LimiteSugerir]

    @extend_schema(parameters=[ConsultaSerializer], responses={200: DireccionSerializer(many=True)})
    def get(self, request):
        datos = ConsultaSerializer(data=request.query_params)
        datos.is_valid(raise_exception=True)
        consulta = datos.validated_data['q']
        if len(normalizar(consulta)) < MINIMO_PARA_SUGERIR:
            return Response([])
        return self.responder(lambda: sugerir(consulta))


class BuscarView(_Direcciones):
    """GET: búsqueda de una dirección completa (Nominatim)."""
    throttle_classes = [LimiteBuscar]

    @extend_schema(parameters=[ConsultaSerializer], responses={200: DireccionSerializer(many=True)})
    def get(self, request):
        datos = ConsultaSerializer(data=request.query_params)
        datos.is_valid(raise_exception=True)
        consulta = datos.validated_data['q']
        if len(normalizar(consulta)) < MINIMO_PARA_SUGERIR:
            return Response([])
        return self.responder(lambda: buscar(consulta))


class InversaView(_Direcciones):
    """GET: la dirección de un punto (Nominatim). Las coordenadas no se guardan ni se registran."""
    throttle_classes = [LimiteInversa]

    @extend_schema(parameters=[PuntoSerializer], responses={200: DireccionSerializer(many=True)})
    def get(self, request):
        datos = PuntoSerializer(data=request.query_params)
        datos.is_valid(raise_exception=True)
        return self.responder(lambda: inversa(datos.validated_data['lat'], datos.validated_data['lon']))
