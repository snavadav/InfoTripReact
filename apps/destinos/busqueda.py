"""Búsqueda que perdona errores: acentos, mayúsculas, ortografía aproximada y sinónimos.

El catálogo de destinos es chico (cientos de filas), así que se ordena en Python con la misma lógica en
PostgreSQL y en SQLite: una clave fonética del español («tlakepake» = «Tlaquepaque»), coincidencia por
palabra y, solo si una palabra no aparece en ningún lado, similitud aproximada. Los lugares (decenas de
miles) se buscan en la base: en PostgreSQL con unaccent y trigramas apoyados en un índice GIN.
"""
import re
import unicodedata
from urllib.parse import urlencode
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache

from django.contrib.postgres.search import TrigramSimilarity, TrigramWordSimilarity
from django.contrib.postgres.lookups import Unaccent
from django.db import connection
from django.db.models import Avg, Case, IntegerField, Q, Value, When
from django.urls import reverse

from apps.comunidad.selectors import PUEBLOS_MAGICOS
from .models import Categoria, Destino, Lugar, Municipio

# Versión de las listas de abajo: súbela al cambiarlas para saber con cuál se comportó una búsqueda.
VERSION_SINONIMOS = 1

# Abreviaturas y nombres populares → cómo aparecen en el catálogo. Solo equivalencias comprobables.
ABREVIATURAS = {
    'gdl': 'guadalajara',
    'pv': 'puerto vallarta',
    'cd guzman': 'zapotlan el grande',  # Ciudad Guzmán es la cabecera de Zapotlán el Grande.
    'ciudad guzman': 'zapotlan el grande',
}

# Frases que equivalen a un conjunto de destinos ya definido en los datos. La frase también se busca
# como texto normal: el sinónimo agrega resultados, no los quita.
SLUGS_PUEBLOS_MAGICOS = frozenset(slug for slug, _ in PUEBLOS_MAGICOS)
SINONIMOS = {
    'pueblo magico': {'slugs': SLUGS_PUEBLOS_MAGICOS, 'nombre': 'Pueblos Mágicos'},
    'playa': {'categoria': 'costa'},
    'zona arqueologica': {'categoria': 'arqueologia'},
    'piramide': {'categoria': 'arqueologia'},
    'ruina': {'categoria': 'arqueologia'},
}

PALABRAS_VACIAS = frozenset('a al con de del el en la las lo los para por un una y'.split())

# Peso de cada campo por palabra encontrada.
PESOS = {'nombre': 10, 'municipio': 6, 'categoria': 4, 'region': 3, 'descripcion': 1}
# Solo se corrige la ortografía contra nombres: en descripciones daría coincidencias falsas.
CAMPOS_APROXIMADOS = ('nombre', 'municipio')
PARECIDO_MINIMO = 0.78
PARECIDO_SUGERENCIA = 0.6
LARGO_MINIMO_APROXIMADO = 4


def sin_acentos(texto):
    """Minúsculas, sin acentos ni signos, con espacios simples."""
    texto = unicodedata.normalize('NFD', (texto or '').casefold())
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^\w]+', ' ', texto).replace('_', ' ').split())


def fonetica(palabra):
    """Clave de cómo suena una palabra en español: qu/k/c, s/z/c, b/v, ll/y y h muda se escriben igual."""
    p = palabra.replace('ch', '#')
    p = p.replace('qu', 'k').replace('ce', 'se').replace('ci', 'si').replace('c', 'k')
    p = p.replace('z', 's').replace('v', 'b').replace('ll', 'y').replace('h', '').replace('#', 'ch')
    p = re.sub(r'(.)\1+', r'\1', p)
    # Singular y plural cuentan igual: «lagos» = «lago», «miradores» = «mirador», «pirámides» = «pirámide».
    if len(p) > 3 and p.endswith('s'):
        p = p[:-1]
    if len(p) > 4 and p.endswith('e'):
        p = p[:-1]
    return p


def claves(texto):
    return [fonetica(palabra) for palabra in sin_acentos(texto).split()]


def parecido(a, b, minimo=0):
    """Entre 0 y 1. Con `minimo`, devuelve 0 en cuanto se sabe que no lo alcanza (es mucho más rápido)."""
    comparador = SequenceMatcher(None, a, b)
    if minimo and (comparador.real_quick_ratio() < minimo or comparador.quick_ratio() < minimo):
        return 0
    return comparador.ratio()


def _expandir(normal):
    for abreviatura, completo in ABREVIATURAS.items():
        normal = re.sub(rf'\b{abreviatura}\b', completo, normal)
    return normal


@dataclass
class Consulta:
    original: str
    palabras: list  # (clave, palabra como la escribió la persona)
    sinonimos: list = field(default_factory=list)  # (claves de la frase, regla)

    @property
    def clave(self):
        return ' '.join(clave for clave, _ in self.palabras)


def interpretar(texto):
    normal = _expandir(sin_acentos(texto))
    palabras = [(fonetica(p), p) for p in normal.split()]
    utiles = [par for par in palabras if par[1] not in PALABRAS_VACIAS]
    consulta = Consulta(texto, utiles or palabras)
    claves_consulta = [clave for clave, _ in consulta.palabras]
    for frase, regla in SINONIMOS.items():
        frase_claves = claves(frase)
        largo = len(frase_claves)
        for inicio in range(len(claves_consulta) - largo + 1):
            if claves_consulta[inicio:inicio + largo] == frase_claves:
                consulta.sinonimos.append((frase_claves, regla))
                break
    return consulta


@dataclass
class Documento:
    pk: int
    nombre: str
    slug: str
    municipio: str
    campos: dict  # campo → lista de (clave, palabra original)
    categorias: set


@lru_cache(maxsize=20000)
def _clave_de_palabra(palabra):
    return fonetica(sin_acentos(palabra))


@lru_cache(maxsize=4096)
def _palabras(texto):
    """Memorizado: los textos del catálogo casi no cambian y así no se recalculan en cada búsqueda."""
    return tuple((clave, p) for p in re.findall(r'\w+', texto or '') if (clave := _clave_de_palabra(p)))


def documentos(queryset):
    """Lo mínimo para ordenar el catálogo. Dos consultas, sin importar cuántos destinos haya."""
    queryset = queryset.order_by()
    categorias = {}
    for pk, slug, nombre in queryset.values_list('pk', 'categorias__slug', 'categorias__nombre'):
        if slug:
            categorias.setdefault(pk, {})[slug] = nombre
    filas = queryset.values_list('pk', 'nombre', 'slug', 'descripcion', 'municipio__nombre',
                                 'municipio__region__nombre').distinct()
    return [
        Documento(pk, nombre, slug, municipio, {
            'nombre': _palabras(nombre), 'municipio': _palabras(municipio), 'region': _palabras(region),
            'categoria': _palabras(' '.join(categorias.get(pk, {}).values())), 'descripcion': _palabras(descripcion),
        }, set(categorias.get(pk, {})))
        for pk, nombre, slug, descripcion, municipio, region in filas
    ]


def _nivel_exacto(clave, palabras, prefijo=True):
    mejor = 0
    for otra, _ in palabras:
        if otra == clave:
            return 1.0
        if prefijo and len(clave) >= 3 and otra.startswith(clave):
            mejor = 0.8
    return mejor


def _nivel(clave, campo, palabras):
    # En descripciones, solo palabras completas: por prefijo, «mar» encontraría «mariscos» o «María».
    return _nivel_exacto(clave, palabras, prefijo=campo != 'descripcion')


def _nivel_aproximado(clave, palabras):
    mejor, original = 0, None
    for otra, palabra in palabras:
        valor = parecido(clave, otra, PARECIDO_MINIMO)
        if valor >= PARECIDO_MINIMO and valor > mejor:
            mejor, original = valor, palabra
    return mejor * 0.7, original


def _cercania(palabras, clave_total):
    """1 si el nombre completo es lo escrito; menos si empieza igual o se le parece mucho (con errores)."""
    nombre = ' '.join(clave for clave, _ in palabras)
    if nombre == clave_total:
        return 1
    if nombre.startswith(clave_total):
        return 0.4
    valor = parecido(nombre, clave_total, PARECIDO_MINIMO)
    return valor * 0.8 if valor >= PARECIDO_MINIMO else 0


def _en_sinonimo(documento, regla):
    return documento.slug in regla.get('slugs', ()) or regla.get('categoria') in documento.categorias


@dataclass
class Resultado:
    puntajes: dict  # pk → puntaje, solo los que coinciden
    sugerencia: str = ''


def ordenar(consulta, docs):
    """Puntaje por destino: cada palabra debe aparecer en algún campo (o caer en un sinónimo)."""
    if not consulta.palabras:
        return Resultado({doc.pk: 0 for doc in docs})
    # Una palabra se corrige solo si no aparece tal cual en ningún destino: así «talpa» no trae «Tapalpa».
    exactas = {
        clave for clave, _ in consulta.palabras
        if any(_nivel(clave, campo, palabras) for doc in docs for campo, palabras in doc.campos.items())
    }
    clave_total = consulta.clave
    puntajes, correcciones = {}, {}
    for doc in docs:
        cubiertas = set()
        for frase_claves, regla in consulta.sinonimos:
            if _en_sinonimo(doc, regla):
                cubiertas.update(frase_claves)
        puntaje = 5 * len(cubiertas)
        completo = True
        for clave, _ in consulta.palabras:
            mejor = max(PESOS[campo] * _nivel(clave, campo, palabras) for campo, palabras in doc.campos.items())
            if not mejor and clave not in exactas and len(clave) >= LARGO_MINIMO_APROXIMADO:
                for campo in CAMPOS_APROXIMADOS:
                    nivel, original = _nivel_aproximado(clave, doc.campos[campo])
                    if PESOS[campo] * nivel > mejor:
                        mejor = PESOS[campo] * nivel
                        original = original.capitalize() if original.isupper() else original
                        correcciones.setdefault(clave, {}).setdefault(original, 0)
                        correcciones[clave][original] += 1
            if not mejor and clave not in cubiertas:
                completo = False
                break
            puntaje += mejor
        if not completo:
            continue
        puntaje += 50 * _cercania(doc.campos['nombre'], clave_total)
        puntaje += 15 * _cercania(doc.campos['municipio'], clave_total)
        puntajes[doc.pk] = round(puntaje * 10)
    sugerencia = ''
    if correcciones:
        sugerencia = ' '.join(
            max(correcciones[clave], key=correcciones[clave].get) if clave in correcciones else palabra
            for clave, palabra in consulta.palabras
        )
    return Resultado(puntajes, sugerencia)


def sugerir(consulta, docs, municipios=()):
    """Sin resultados: el nombre de destino o municipio que más se parece a lo escrito, si alguno se parece."""
    clave = consulta.clave
    if len(clave) < 3:
        return ''
    candidatos = {doc.nombre for doc in docs} | set(municipios)
    mejor, valor_mejor = '', PARECIDO_SUGERENCIA
    for nombre in candidatos:
        valor = parecido(clave, ' '.join(claves(nombre)), valor_mejor)
        if valor > valor_mejor:
            mejor, valor_mejor = nombre, valor
    return mejor


def buscar_destinos(queryset, texto):
    """Filtra y anota `relevancia`; también devuelve la sugerencia («¿Quisiste decir…?»), si la hay."""
    consulta = interpretar(texto)
    docs = documentos(queryset)
    resultado = ordenar(consulta, docs)
    if not resultado.puntajes:
        municipios = Municipio.objects.filter(destinos__es_activo=True).values_list('nombre', flat=True).distinct()
        resultado.sugerencia = sugerir(consulta, docs, municipios)
        return queryset.none().annotate(relevancia=Value(0, output_field=IntegerField())), resultado
    relevancia = Case(*[When(pk=pk, then=Value(valor)) for pk, valor in resultado.puntajes.items()],
                      default=Value(0), output_field=IntegerField())
    return queryset.filter(pk__in=list(resultado.puntajes)).annotate(relevancia=relevancia), resultado


# ─── Autocompletado ───────────────────────────────────────────
MAXIMO_DESTINOS = 5
MAXIMO_MUNICIPIOS = 3
MAXIMO_LUGARES = 3
LARGO_MINIMO_AUTOCOMPLETAR = 2
LARGO_MINIMO_LUGARES = 3
CANDIDATOS_SQLITE = 200


def _coincide_nombre(consulta, palabras):
    """Todas las palabras escritas están en el nombre (completas, por inicio o, con errores, parecidas)."""
    return all(
        _nivel_exacto(clave, palabras)
        or (len(clave) >= LARGO_MINIMO_APROXIMADO and _nivel_aproximado(clave, palabras)[0])
        for clave, _ in consulta.palabras
    )


def municipios_para(consulta, limite=MAXIMO_MUNICIPIOS):
    filas = (Municipio.objects.filter(destinos__es_activo=True).distinct()
             .values_list('nombre', 'slug', 'region__nombre'))
    encontrados = []
    for nombre, slug, region in filas:
        palabras = _palabras(nombre)
        if consulta.palabras and _coincide_nombre(consulta, palabras):
            encontrados.append((-_cercania(palabras, consulta.clave), nombre, slug, region))
    return sorted(encontrados)[:limite]


def lugares_por_nombre(texto, limite=MAXIMO_LUGARES):
    """Comer, dormir, etc. por nombre. Son decenas de miles: en PostgreSQL usa trigramas con índice GIN."""
    normal = sin_acentos(texto)
    if len(normal) < LARGO_MINIMO_LUGARES:
        return []
    lugares = Lugar.objects.filter(es_activo=True).select_related('municipio')
    escritos = {' '.join(texto.split()), normal}
    if connection.vendor == 'postgresql':
        # Ojo: icontains se traduce a UPPER(nombre) LIKE … y no usa el índice (leía 45 mil filas, ~0.5 s).
        # `~*` y `%>` sobre la columna tal cual sí usan lugar_nombre_trgm_idx (unos pocos ms). La similitud
        # sin acentos solo se calcula para las filas que ya pasaron el filtro.
        patron = '|'.join(re.escape(escrito) for escrito in sorted(escritos))
        lugares = lugares.filter(Q(nombre__iregex=patron) | Q(nombre__trigram_word_similar=normal)).annotate(
            parecido=TrigramWordSimilarity(Value(normal), Unaccent('nombre')),
            # Desempate: «Birriería» antes que «Auxiliar Birriería en la Aurora».
            parecido_total=TrigramSimilarity(Unaccent('nombre'), Value(normal)),
        ).order_by('-parecido', '-parecido_total', 'nombre', 'pk')
    else:
        # SQLite no tiene unaccent: las vocales y la n pueden llevar acento, así que en el patrón valen
        # cualquier letra (.) y el filtro exacto sin acentos se hace en Python.
        patron = ''.join('.' if letra in 'aeioun' else re.escape(letra) for letra in normal)
        candidatos = lugares.filter(nombre__iregex=patron).order_by('nombre', 'pk')[:CANDIDATOS_SQLITE]
        return [lugar for lugar in candidatos if normal in sin_acentos(lugar.nombre)][:limite]
    return list(lugares[:limite])


def _redondo(valor):
    return None if valor is None else round(float(valor), 5)


def autocompletar(texto):
    """Lo que el campo de búsqueda propone mientras se escribe: destinos, municipios, colecciones y lugares."""
    consulta = interpretar(texto)
    if len(consulta.clave) < LARGO_MINIMO_AUTOCOMPLETAR:
        return {'resultados': [], 'sugerencia': ''}
    resultados = []
    for frase_claves, regla in consulta.sinonimos:
        if 'slugs' in regla:
            resultados.append({'tipo': 'coleccion', 'nombre': regla['nombre'], 'detalle': 'Colección',
                               'url': f"{reverse('destinos-listado')}?{urlencode({'q': regla['nombre']})}"})
    nombres_categoria = {
        slug: nombre for slug, nombre in
        Categoria.objects.filter(destinos__es_activo=True).distinct().values_list('slug', 'nombre')
    }
    por_sinonimo = {regla['categoria'] for _, regla in consulta.sinonimos if 'categoria' in regla}
    for slug, nombre in nombres_categoria.items():
        if slug in por_sinonimo or _coincide_nombre(consulta, _palabras(nombre)):
            resultados.append({'tipo': 'categoria', 'nombre': nombre, 'detalle': 'Categoría',
                               'url': f"{reverse('destinos-listado')}?{urlencode({'categoria': slug})}"})
    municipios = municipios_para(consulta)
    # El punto medio de sus destinos públicos: el planeador lo usa como destino del viaje.
    centros = {fila['slug']: fila for fila in Municipio.objects.filter(slug__in=[m[2] for m in municipios]).annotate(
        lat=Avg('destinos__latitud', filter=Q(destinos__es_activo=True)),
        lng=Avg('destinos__longitud', filter=Q(destinos__es_activo=True))).values('slug', 'lat', 'lng')}
    for _, nombre, slug, region in municipios:
        centro = centros.get(slug, {})
        resultados.append({'tipo': 'municipio', 'nombre': nombre, 'detalle': f'Municipio · {region}',
                           'url': f"{reverse('destinos-listado')}?{urlencode({'municipio': slug})}", 'slug': slug,
                           'latitud': _redondo(centro.get('lat')), 'longitud': _redondo(centro.get('lng'))})
    publicos = Destino.objects.filter(es_activo=True)
    destinos, busqueda = buscar_destinos(publicos, texto)
    for destino in destinos.select_related('municipio').order_by('-relevancia', 'nombre', 'pk')[:MAXIMO_DESTINOS]:
        resultados.append({'tipo': 'destino', 'nombre': destino.nombre, 'detalle': destino.municipio.nombre,
                           'url': reverse('destino-detalle', kwargs={'slug': destino.slug}), 'slug': destino.slug,
                           'latitud': _redondo(destino.latitud), 'longitud': _redondo(destino.longitud)})
    for lugar in lugares_por_nombre(texto):
        detalle = ' · '.join(filter(None, [lugar.get_subtipo_display(), getattr(lugar.municipio, 'nombre', '')]))
        resultados.append({'tipo': 'lugar', 'nombre': lugar.nombre, 'detalle': detalle,
                           'url': reverse('lugar-detalle', kwargs={'pk': lugar.pk})})
    return {'resultados': resultados, 'sugerencia': busqueda.sugerencia}
