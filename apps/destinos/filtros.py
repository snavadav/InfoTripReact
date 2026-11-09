"""Filtros del catálogo: una sola definición para la API y la exploración HTML.

Cada interfaz valida su entrada a su manera (FiltrosDestinoSerializer en la API y ExploracionForm
en la web, con sus mensajes y opciones), y las dos filtran con FiltroDestinos.
"""
import django_filters
from django.db.models import Exists

from apps.comunidad.selectors import correcciones_recientes, filtrar_comunidad, por_informacion_reciente
from .busqueda import buscar_destinos


class FiltroDestinos(django_filters.FilterSet):
    q = django_filters.CharFilter(method='buscar')
    categoria = django_filters.CharFilter(field_name='categorias__slug')
    municipio = django_filters.CharFilter(field_name='municipio__slug')
    region = django_filters.CharFilter(field_name='municipio__region__slug')
    servicio = django_filters.CharFilter(field_name='servicios__slug')
    datos_recientes = django_filters.BooleanFilter(method='con_datos_recientes')
    # Los filtros de comunidad dependen entre sí (precio_max necesita concepto), así que se
    # aplican juntos en filter_queryset.
    calificacion_min = django_filters.NumberFilter(method='aplicar_en_comunidad')
    concepto = django_filters.CharFilter(method='aplicar_en_comunidad')
    precio_max = django_filters.NumberFilter(method='aplicar_en_comunidad')
    # El orden se aplica al final, después de los filtros de comunidad.
    orden = django_filters.CharFilter(method='aplicar_en_comunidad')

    busqueda = None

    def buscar(self, queryset, nombre, texto):
        # Tolera acentos, mayúsculas, errores de escritura y sinónimos (ver busqueda.py).
        queryset, self.busqueda = buscar_destinos(queryset, texto)
        return queryset

    def con_datos_recientes(self, queryset, nombre, valor):
        return queryset.filter(Exists(correcciones_recientes())) if valor else queryset

    def aplicar_en_comunidad(self, queryset, nombre, valor):
        return queryset

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        queryset = filtrar_comunidad(queryset, self.form.cleaned_data).distinct()
        if self.form.cleaned_data.get('orden') == 'recientes':
            queryset = por_informacion_reciente(queryset)
        elif self.busqueda is not None:
            # Lo más parecido a lo escrito primero: nombre exacto, luego municipio y luego similitud.
            queryset = queryset.order_by('-relevancia', *queryset.model._meta.ordering)
        return queryset


def buscar_y_filtrar(queryset, datos):
    """Como filtrar_destinos, más la sugerencia («¿Quisiste decir…?») de la búsqueda por texto, o ''."""
    filtro = FiltroDestinos(datos, queryset=queryset)
    if not filtro.is_valid():
        return queryset.none(), ''
    resultados = filtro.qs
    return resultados, filtro.busqueda.sugerencia if filtro.busqueda else ''


def filtrar_destinos(queryset, datos):
    """Aplica filtros ya validados por la interfaz; ante datos inválidos no devuelve el catálogo completo."""
    return buscar_y_filtrar(queryset, datos)[0]
