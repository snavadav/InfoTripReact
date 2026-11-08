from django.contrib import admin

from .models import EtiquetaLugar, PrediccionLugar


@admin.register(EtiquetaLugar)
class EtiquetaLugarAdmin(admin.ModelAdmin):
    list_display = ('lugar', 'util', 'autor', 'creado')
    list_filter = ('util', 'lugar__tipo')
    search_fields = ('lugar__nombre',)
    raw_id_fields = ('lugar',)
    readonly_fields = ('autor', 'creado')

    def has_add_permission(self, request):
        return False  # Se etiqueta en /admin/etiquetar-lugares/, que registra quién lo hizo.


class RangoFiltro(admin.SimpleListFilter):
    title = 'opinión del curador'
    parameter_name = 'rango'
    RANGOS = {'no': ('Probablemente no sirve (< 30 %)', 0, 0.3), 'duda': ('Dudoso (30–70 %)', 0.3, 0.7),
              'si': ('Probablemente sirve (≥ 70 %)', 0.7, 1.01)}

    def lookups(self, request, model_admin):
        return [(clave, texto) for clave, (texto, _, _) in self.RANGOS.items()]

    def queryset(self, request, queryset):
        if self.value() in self.RANGOS:
            _, desde, hasta = self.RANGOS[self.value()]
            return queryset.filter(probabilidad__gte=desde, probabilidad__lt=hasta)
        return queryset


@admin.register(PrediccionLugar)
class PrediccionLugarAdmin(admin.ModelAdmin):
    """Solo lectura: para ocultar un lugar se edita el lugar, y esa decisión la toma una persona."""
    list_display = ('lugar', 'tipo', 'municipio', 'probabilidad_legible', 'visible')
    list_filter = (RangoFiltro, 'lugar__tipo', 'lugar__es_activo')
    search_fields = ('lugar__nombre',)
    list_select_related = ('lugar__municipio',)

    @admin.display(description='tipo', ordering='lugar__tipo')
    def tipo(self, prediccion):
        return prediccion.lugar.get_tipo_display()

    @admin.display(description='municipio')
    def municipio(self, prediccion):
        return prediccion.lugar.municipio

    @admin.display(description='probabilidad de que sirva', ordering='probabilidad')
    def probabilidad_legible(self, prediccion):
        return f'{prediccion.probabilidad:.0%}'

    @admin.display(description='visible en el mapa', boolean=True, ordering='lugar__es_activo')
    def visible(self, prediccion):
        return prediccion.lugar.es_activo

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
