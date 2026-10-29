"""Filtros del catálogo: una sola definición para la API y la exploración HTML.

Cada interfaz valida su entrada a su manera (FiltrosDestinoSerializer en la API y ExploracionForm
en la web, con sus mensajes y opciones), y las dos filtran con FiltroDestinos.
"""
import django_filters
from django.db.models import Exists, Q

from apps.comunidad.selectors import correcciones_recientes, filtrar_comunidad


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

    def buscar(self, queryset, nombre, texto):
        return queryset.filter(Q(nombre__icontains=texto) | Q(descripcion__icontains=texto)
                               | Q(municipio__nombre__icontains=texto))

    def con_datos_recientes(self, queryset, nombre, valor):
        return queryset.filter(Exists(correcciones_recientes())) if valor else queryset

    def aplicar_en_comunidad(self, queryset, nombre, valor):
        return queryset

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        return filtrar_comunidad(queryset, self.form.cleaned_data).distinct()


def filtrar_destinos(queryset, datos):
    """Aplica filtros ya validados por la interfaz; ante datos inválidos no devuelve el catálogo completo."""
    filtro = FiltroDestinos(datos, queryset=queryset)
    return filtro.qs if filtro.is_valid() else queryset.none()
