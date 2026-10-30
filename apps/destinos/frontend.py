"""Presentación pública del catálogo y selección editorial inicial."""
from random import sample
from urllib.parse import urlencode
import unicodedata

from django import forms
from django.core.paginator import Paginator
from django.db.models import F
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.templatetags.static import static
from django.utils import timezone
from django.utils.text import slugify

from apps.comunidad.models import Aporte, Colaboracion
from apps.comunidad.selectors import (
    MINIMO_CRONISTA, MINIMO_REPORTES, SLUGS_PUEBLOS, aportes_publicos, con_info_reciente, costos_de_destino,
    costos_por_destino, cronistas, estado_de_lugar, ficha_practica, misiones_por_destino, preguntas_publicas,
    resenas_publicas_de_lugar, resumen,
)
from .filtros import filtrar_destinos
from .lugares import activos as lugares_activos, cercanos_de_destino
from .fotos import FOTOS_CATALOGO
from .models import Destino, Categoria, Lugar, Municipio, Region, Servicio, TIPO_DE_SUBTIPO
from .seo import seo_de_destino
from .views import destinos_publicos


INSPIRACION = [
    {
        'nombre': 'Puerto Vallarta',
        'slug': 'puerto-vallarta',
        'municipio': 'Puerto Vallarta',
        'region': 'Costa de Jalisco',
        'categoria': 'Costa',
        'categorias': ['Costa'],
        'imagen': 'images/ptVallarta.jpg',
        'alt': 'Vista de la bahía de Puerto Vallarta al atardecer',
        'descripcion': ('Una escapada junto al mar. Encuentra inspiración en el paisaje de la bahía, '
                        'sus paseos y los colores del atardecer.'),
        'servicios': [],
        'direccion': '',
        'editorial': True,
    },
    {
        'nombre': 'Tequila',
        'slug': 'tequila',
        'municipio': 'Tequila',
        'region': 'Jalisco',
        'categoria': 'Pueblos',
        'categorias': ['Pueblos'],
        'imagen': 'images/tequila.jpg',
        'alt': 'Calle peatonal de Tequila con arquitectura tradicional y vegetación',
        'descripcion': ('Una pausa entre calles con historia. Camina sin prisa, descubre rincones llenos '
                        'de color y disfruta el ambiente de un pueblo de Jalisco.'),
        'servicios': [],
        'direccion': '',
        'editorial': True,
    },
]
FOTOS = {lugar['slug']: (lugar['imagen'], lugar['alt']) for lugar in INSPIRACION}


def presentar(destino):
    categorias = [categoria.nombre for categoria in destino.categorias.all()]
    catalogo = FOTOS_CATALOGO.get(destino.slug)
    foto, alt = (catalogo['imagen'], catalogo['alt']) if catalogo else FOTOS.get(destino.slug, ('', ''))
    fotos = getattr(destino, 'fotos_publicas', [])
    return {
        'nombre': destino.nombre, 'slug': destino.slug, 'descripcion': destino.descripcion,
        'municipio': destino.municipio.nombre, 'region': destino.municipio.region.nombre,
        'categorias': categorias, 'categoria': categorias[0] if categorias else 'Por descubrir',
        'servicios': [servicio.nombre for servicio in destino.servicios.all()],
        'direccion': destino.direccion, 'latitud': str(destino.latitud), 'longitud': str(destino.longitud),
        'imagen': foto, 'foto_url': fotos[0].imagen.url if fotos else '',
        'alt': fotos[0].texto if fotos else alt, 'editorial': False,
        'credito': None if fotos else catalogo,
        'osm_url': f'https://www.openstreetmap.org/{destino.osm_id}' if destino.osm_id else '',
        'miniatura_url': (fotos[0].miniatura.url if fotos and fotos[0].miniatura else
                          static(catalogo['miniatura']) if catalogo and not fotos else ''),
    }


def completar(lugar):
    lugar = dict(lugar)
    lugar['url'] = reverse('destino-detalle', kwargs={'slug': lugar['slug']})
    lugar['foto_url'] = lugar.get('foto_url') or (static(lugar['imagen']) if lugar['imagen'] else '')
    lugar['miniatura_url'] = lugar.get('miniatura_url') or lugar['foto_url']
    if lugar['editorial']:
        # En inspiración se busca el nombre del lugar; no se inventa un punto GPS.
        destino_maps = f"{lugar['nombre']}, Jalisco, México"
    else:
        destino_maps = f"{lugar['latitud']},{lugar['longitud']}"
    lugar['maps_url'] = 'https://www.google.com/maps/dir/?' + urlencode({'api': 1, 'destination': destino_maps})
    lugar['mapa_embed'] = 'https://maps.google.com/maps?' + urlencode({'q': destino_maps, 'output': 'embed'})
    return lugar


def primero_lo_curado(destinos):
    """Lo registrado por el equipo antes que lo importado: es lo que tiene descripción y fotografía."""
    return destinos.order_by(F('osm_id').asc(nulls_first=True), 'nombre', 'pk')


def punto_de_mapa(destino):
    """Solo lo que el mapa pinta al abrir: con cientos de puntos, cada campo se nota en el tamaño de la página."""
    lugar = completar(presentar(destino))
    return {
        'slug': lugar['slug'], 'nombre': lugar['nombre'], 'municipio': lugar['municipio'], 'region': lugar['region'],
        'categoria': lugar['categoria'], 'categorias': lugar['categorias'],
        'latitud': lugar['latitud'], 'longitud': lugar['longitud'],
        'url': lugar['url'], 'maps_url': lugar['maps_url'], 'miniatura_url': lugar['miniatura_url'],
        'destacado': bool(lugar['miniatura_url']),
    }


def inicio(request):
    lugares = [presentar(destino) for destino in primero_lo_curado(destinos_publicos(con_fotos=True))[:12]]
    # La selección editorial solo se usa en una instalación sin destinos (ni siquiera inactivos).
    if not lugares and not Destino.objects.exists():
        lugares = INSPIRACION
    seleccion = sample(lugares, min(3, len(lugares)))
    return render(request, 'index.html', {
        'lugares': [completar(lugar) for lugar in seleccion],
        'exploracion': [completar(lugar) for lugar in lugares],
        'puntos_mapa': [punto_de_mapa(destino) for destino in destinos_publicos(con_fotos=True)],
        'categorias_inicio': sorted({categoria for lugar in lugares for categoria in lugar['categorias']}),
    })


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto.casefold()) if not unicodedata.combining(c))


class ExploracionForm(forms.Form):
    q = forms.CharField(label='Destino o municipio', required=False, max_length=200,
                        widget=forms.TextInput(attrs={'placeholder': '¿A dónde quieres ir?'}))
    categoria = forms.ChoiceField(label='Categoría', required=False)
    municipio = forms.ChoiceField(label='Municipio', required=False)
    region = forms.ChoiceField(label='Región', required=False)
    servicio = forms.ChoiceField(label='Servicio', required=False)
    calificacion_min = forms.DecimalField(
        label='Calificación mínima', required=False, min_value=1, max_value=5, decimal_places=1
    )
    concepto = forms.ChoiceField(
        label='Tipo de gasto',
        required=False,
        choices=[
            ('', 'Cualquiera'),
            ('entrada', 'Entrada por persona'),
            ('comida', 'Comida por persona'),
            ('alojamiento', 'Alojamiento por noche'),
            ('transporte', 'Transporte por persona'),
        ],
    )
    precio_max = forms.DecimalField(
        label='Promedio máximo (MXN)', required=False, min_value=0, max_value=9999999, decimal_places=2
    )
    datos_recientes = forms.BooleanField(
        label='Con información práctica consultada o confirmada en los últimos 90 días', required=False
    )
    orden = forms.ChoiceField(
        label='Ordenar por', required=False,
        choices=[('', 'Destacados primero'), ('recientes', 'Información práctica más reciente')],
    )

    def clean(self):
        datos = super().clean()
        if datos.get('precio_max') is not None and not datos.get('concepto'):
            self.add_error('concepto', 'Selecciona el tipo de gasto para comparar precios.')
        return datos

    def __init__(self, *args, editorial=False, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo lo que tiene destinos publicados: un filtro sin resultados no le sirve a nadie.
        for campo, modelo, relacion in [
            ('categoria', Categoria, 'destinos__es_activo'),
            ('municipio', Municipio, 'destinos__es_activo'),
            ('region', Region, 'municipios__destinos__es_activo'),
            ('servicio', Servicio, 'destinos__es_activo'),
        ]:
            opciones = list(modelo.objects.filter(**{relacion: True}).distinct().values_list('slug', 'nombre'))
            if editorial and campo != 'servicio':
                opciones = sorted({(slugify(lugar[campo]), lugar[campo]) for lugar in INSPIRACION})
            self.fields[campo].choices = [('', 'Todos')] + opciones


def listado(request):
    editorial = not Destino.objects.exists()
    formulario = ExploracionForm(request.GET, editorial=editorial)
    valido = formulario.is_valid()
    datos = formulario.cleaned_data if valido else {}
    texto = datos.get('q', '')
    if editorial:
        resultados = (
            [
                lugar
                for lugar in INSPIRACION
                if normalizar(texto)
                in normalizar(lugar['nombre'] + ' ' + lugar['descripcion'] + ' ' + lugar['municipio'])
                and all(
                    not datos.get(campo) or datos[campo] == slugify(lugar[campo])
                    for campo in ['categoria', 'municipio', 'region']
                )
                and not datos.get('servicio')
                and not datos.get('datos_recientes')
                and datos.get('calificacion_min') is None
                and datos.get('precio_max') is None
                and not datos.get('concepto')
            ]
            if valido
            else []
        )
    else:
        queryset = con_info_reciente(destinos_publicos(con_fotos=True))
        resultados = filtrar_destinos(queryset, datos) if valido else queryset.none()
        if not datos.get('orden'):
            resultados = primero_lo_curado(resultados)
    pagina = Paginator(resultados, 8).get_page(request.GET.get('page'))
    lugares = []
    for destino in pagina:
        lugar = completar(destino if isinstance(destino, dict) else presentar(destino))
        lugar['tiene_info_reciente'] = getattr(destino, 'tiene_info_reciente', False)
        lugares.append(lugar)
    # El mapa muestra todos los resultados, no solo los de esta página de la lista.
    puntos = [] if editorial else [punto_de_mapa(destino) for destino in resultados]
    return render(
        request,
        'destinos/listado.html',
        {
            'lugares': lugares,
            'pagina': pagina,
            'q': texto,
            'formulario': formulario,
            'categoria': datos.get('categoria', ''),
            'filtros': urlencode({k: v for k, v in datos.items() if v not in (None, '', False)}),
            'filtros_activos': any(v not in (None, '', False) for k, v in datos.items() if k != 'q'),
            'puntos_mapa': puntos,
            'editorial': editorial,
        },
    )


def detalle(request, slug):
    destino = None
    if not Destino.objects.exists():
        lugar = next((item for item in INSPIRACION if item['slug'] == slug), None)
        if lugar is None:
            raise Http404('Destino no encontrado')
    else:
        destino = get_object_or_404(destinos_publicos(con_fotos=True), slug=slug)
        lugar = presentar(destino)
    lugar = completar(lugar)
    contexto = {'lugar': lugar, 'hoy': timezone.localdate().isoformat(), 'da_sello': slug in SLUGS_PUEBLOS}
    if destino is not None:
        contexto['practica'] = ficha_practica(destino)
        contexto['campos_practicos'] = Colaboracion.CAMPOS
        contexto['preguntas'] = Paginator(preguntas_publicas(destino), 8).get_page(request.GET.get('preguntas'))
        contexto['resumen'] = resumen(destino)
        contexto['aportes'] = Paginator(aportes_publicos(destino), 9).get_page(request.GET.get('aportes'))
        contexto['cerca'] = cercanos_de_destino(destino)
    contexto['seo'] = seo_de_destino(lugar, contexto.get('resumen'))
    return render(request, 'destinos/detalle.html', contexto)


def creditos(request):
    return render(request, 'legal/creditos.html', {'fotos': FOTOS_CATALOGO.values()})


def costos_destino(request, slug):
    destino = get_object_or_404(destinos_publicos(con_fotos=True), slug=slug)
    lugar = completar(presentar(destino))
    costos = costos_de_destino(destino)
    seo = seo_de_destino(lugar)
    seo['titulo'] = f"¿Cuánto cuesta ir a {lugar['nombre']}? Gastos reales de viajeros — InfoTrip"
    seo['descripcion'] = descripcion_de_costos(lugar['nombre'], costos)
    return render(request, 'destinos/costos.html', {
        'lugar': lugar, 'costos': costos, 'seo': seo, 'minimo': MINIMO_REPORTES,
    })


def descripcion_de_costos(nombre, costos):
    if costos['dia']:
        return (f"Un día típico cuesta cerca de ${costos['dia']['total']:,.0f} MXN por persona en {nombre}, "
                'según gastos reportados por viajeros en el último año.')
    return f'Gastos reportados por viajeros en {nombre}: entrada, comida, alojamiento y transporte.'


def costos_indice(request):
    costos = costos_por_destino()
    # Por concepto y por nombre: un ranking de totales compararía destinos con datos distintos.
    filas = [{'destino': destino, 'montos': [fila['mediana'] for fila in costos[destino.pk]['conceptos']]}
             for destino in Destino.objects.filter(pk__in=costos, es_activo=True).order_by('nombre')]
    seo = {'titulo': '¿Cuánto cuesta viajar por Jalisco? — InfoTrip',
           'descripcion': ('Compara lo que gastaron viajeros en destinos de Jalisco: '
                           'entrada, comida, alojamiento y transporte.')}
    return render(request, 'destinos/costos_indice.html', {
        'filas': filas, 'seo': seo, 'minimo': MINIMO_REPORTES,
        'encabezados': [nombre for _, nombre in Aporte.CONCEPTOS],
    })


def misiones(request):
    destinos = Destino.objects.filter(es_activo=True).select_related('municipio').order_by('nombre')
    municipio = request.GET.get('municipio', '')
    municipios = Municipio.objects.filter(destinos__es_activo=True).distinct().order_by('nombre')
    if municipio:
        destinos = destinos.filter(municipio__slug=municipio)
    destinos = list(destinos)
    pendientes = misiones_por_destino([destino.pk for destino in destinos])
    filas = [{'destino': destino, **pendientes[destino.pk]} for destino in destinos
             if pendientes[destino.pk]['faltan'] or pendientes[destino.pk]['confirmar']]
    seo = {'titulo': 'Misiones de la comunidad: qué falta saber en Jalisco — InfoTrip',
           'descripcion': 'Ayuda a otros viajeros: cuenta los horarios, accesos y precios que aún faltan en Jalisco.'}
    return render(request, 'destinos/misiones.html', {
        'pagina': Paginator(filas, 12).get_page(request.GET.get('pagina')), 'municipios': municipios,
        'municipio_actual': municipio, 'seo': seo, 'cronistas': cronistas(), 'minimo_cronista': MINIMO_CRONISTA,
        'total_misiones': sum(len(fila['faltan']) + len(fila['confirmar']) for fila in filas),
    })


def lugar_detalle(request, pk):
    sitio = get_object_or_404(lugares_activos(), pk=pk)
    municipio = f', {sitio.municipio.nombre}' if sitio.municipio else ''
    seo = {'titulo': f'{sitio.nombre}{municipio} — InfoTrip',
           'descripcion': f'{sitio.get_subtipo_display()} en Jalisco: ubicación, contacto y reseñas de viajeros.'}
    return render(request, 'destinos/lugar.html', {
        'sitio': sitio, 'seo': seo, 'estado': estado_de_lugar(sitio), 'hoy': timezone.localdate().isoformat(),
        'resenas': Paginator(resenas_publicas_de_lugar(sitio), 10).get_page(request.GET.get('resenas')),
        'como_llegar': 'https://www.google.com/maps/dir/?' + urlencode(
            {'api': 1, 'destination': f'{sitio.latitud},{sitio.longitud}'}),
    })


def proponer_lugar(request):
    # "pub" y "bar" se ven igual para quien propone: basta una opción.
    opciones = [(clave, nombre) for clave, nombre in Lugar.SUBTIPOS if clave != 'pub']
    return render(request, 'destinos/proponer_lugar.html', {'subtipos': [
        {'nombre': nombre, 'opciones': [opcion for opcion in opciones if TIPO_DE_SUBTIPO[opcion[0]] == tipo]}
        for tipo, nombre in Lugar.TIPOS
    ]})
