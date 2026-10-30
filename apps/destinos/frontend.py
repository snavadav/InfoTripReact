"""Presentación pública del catálogo y selección editorial inicial."""
from random import sample
from urllib.parse import urlencode
import unicodedata

from django import forms
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.templatetags.static import static
from django.utils import timezone
from django.utils.text import slugify

from apps.comunidad.models import Colaboracion
from apps.comunidad.selectors import (
    aportes_publicos, con_info_reciente, ficha_practica, preguntas_publicas, resumen,
)
from .filtros import filtrar_destinos
from .models import Destino, Categoria, Municipio, Region, Servicio
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
    foto, alt = FOTOS.get(destino.slug, ('', ''))
    fotos = getattr(destino, 'fotos_publicas', [])
    return {
        'nombre': destino.nombre, 'slug': destino.slug, 'descripcion': destino.descripcion,
        'municipio': destino.municipio.nombre, 'region': destino.municipio.region.nombre,
        'categorias': categorias, 'categoria': categorias[0] if categorias else 'Por descubrir',
        'servicios': [servicio.nombre for servicio in destino.servicios.all()],
        'direccion': destino.direccion, 'latitud': str(destino.latitud), 'longitud': str(destino.longitud),
        'imagen': foto, 'foto_url': fotos[0].imagen.url if fotos else '',
        'alt': fotos[0].texto if fotos else alt, 'editorial': False,
    }


def completar(lugar):
    lugar = dict(lugar)
    lugar['url'] = reverse('destino-detalle', kwargs={'slug': lugar['slug']})
    lugar['foto_url'] = lugar.get('foto_url') or (static(lugar['imagen']) if lugar['imagen'] else '')
    if lugar['editorial']:
        # En inspiración se busca el nombre del lugar; no se inventa un punto GPS.
        destino_maps = f"{lugar['nombre']}, Jalisco, México"
    else:
        destino_maps = f"{lugar['latitud']},{lugar['longitud']}"
    lugar['maps_url'] = 'https://www.google.com/maps/dir/?' + urlencode({'api': 1, 'destination': destino_maps})
    lugar['mapa_embed'] = 'https://maps.google.com/maps?' + urlencode({'q': destino_maps, 'output': 'embed'})
    return lugar


def inicio(request):
    lugares = [presentar(destino) for destino in destinos_publicos(con_fotos=True)[:12]]
    # La selección editorial solo se usa en una instalación sin destinos (ni siquiera inactivos).
    if not lugares and not Destino.objects.exists():
        lugares = INSPIRACION
    seleccion = sample(lugares, min(3, len(lugares)))
    return render(request, 'index.html', {
        'lugares': [completar(lugar) for lugar in seleccion],
        'exploracion': [completar(lugar) for lugar in lugares],
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
        choices=[('', 'Nombre'), ('recientes', 'Información práctica más reciente')],
    )

    def clean(self):
        datos = super().clean()
        if datos.get('precio_max') is not None and not datos.get('concepto'):
            self.add_error('concepto', 'Selecciona el tipo de gasto para comparar precios.')
        return datos

    def __init__(self, *args, editorial=False, **kwargs):
        super().__init__(*args, **kwargs)
        for campo, modelo in [
            ('categoria', Categoria),
            ('municipio', Municipio),
            ('region', Region),
            ('servicio', Servicio),
        ]:
            opciones = list(modelo.objects.values_list('slug', 'nombre'))
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
    pagina = Paginator(resultados, 8).get_page(request.GET.get('page'))
    lugares = []
    for destino in pagina:
        lugar = completar(destino if isinstance(destino, dict) else presentar(destino))
        lugar['tiene_info_reciente'] = getattr(destino, 'tiene_info_reciente', False)
        lugares.append(lugar)
    puntos = [lugar for lugar in lugares if not lugar['editorial']]
    return render(
        request,
        'destinos/listado.html',
        {
            'lugares': lugares,
            'pagina': pagina,
            'q': texto,
            'formulario': formulario,
            'categoria': datos.get('categoria', ''),
            'filtros': urlencode({k: v for k, v in datos.items() if v is not None and v != ''}),
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
    contexto = {'lugar': completar(lugar), 'hoy': timezone.localdate().isoformat()}
    if destino is not None:
        contexto['practica'] = ficha_practica(destino)
        contexto['campos_practicos'] = Colaboracion.CAMPOS
        contexto['preguntas'] = Paginator(preguntas_publicas(destino), 8).get_page(request.GET.get('preguntas'))
        contexto['resumen'] = resumen(destino)
        contexto['aportes'] = Paginator(aportes_publicos(destino), 9).get_page(request.GET.get('aportes'))
    return render(request, 'destinos/detalle.html', contexto)
