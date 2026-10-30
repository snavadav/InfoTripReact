from django.contrib import admin
from django.utils.html import format_html
from .models import Destino, Lugar, Region, Municipio, Categoria, Servicio


class OrigenFilter(admin.SimpleListFilter):
    title = 'origen'
    parameter_name = 'origen'

    def lookups(self, request, model_admin):
        return [
            ('osm_pendiente', 'OpenStreetMap, sin publicar'), ('osm', 'OpenStreetMap'), ('propio', 'Registro propio'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'osm_pendiente':
            return queryset.exclude(osm_id=None).filter(es_activo=False)
        if self.value() == 'osm':
            return queryset.exclude(osm_id=None)
        if self.value() == 'propio':
            return queryset.filter(osm_id=None)
        return queryset


@admin.register(Destino)
class DestinoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'municipio', 'es_activo', 'ver_en_osm']
    list_filter = ['es_activo', OrigenFilter, 'municipio__region', 'categorias']
    actions = ['publicar', 'ocultar']
    search_fields = ['nombre', 'municipio__nombre']
    prepopulated_fields = {'slug': ('nombre',)}
    filter_horizontal = ['categorias', 'servicios']
    readonly_fields = ['fecha_creacion', 'fecha_actualizacion', 'ver_en_osm']
    def has_delete_permission(self, request, obj=None): return False

    @admin.display(description='OpenStreetMap')
    def ver_en_osm(self, destino):
        if not destino.osm_id:
            return '—'
        return format_html('<a href="https://www.openstreetmap.org/{}" target="_blank" rel="noopener">{}</a>',
                           destino.osm_id, destino.osm_id)

    @admin.action(description='Publicar destinos seleccionados', permissions=['change'])
    def publicar(self, request, queryset):
        queryset.update(es_activo=True)

    @admin.action(description='Ocultar destinos seleccionados', permissions=['change'])
    def ocultar(self, request, queryset):
        queryset.update(es_activo=False)


class CatalogoAdmin(admin.ModelAdmin):
    search_fields = ['nombre']
    prepopulated_fields = {'slug': ('nombre',)}

for modelo in [Region, Municipio, Categoria, Servicio]:
    admin.site.register(modelo, CatalogoAdmin)


@admin.register(Lugar)
class LugarAdmin(admin.ModelAdmin):
    """Editar un lugar lo protege de la siguiente importación. Para retirarlo, se oculta."""
    list_display = ['nombre', 'subtipo', 'municipio', 'es_activo', 'protegido']
    list_filter = ['tipo', 'es_activo', 'protegido', 'municipio__region']
    search_fields = ['nombre', 'municipio__nombre', 'osm_id']
    readonly_fields = ['fecha_creacion', 'fecha_actualizacion', 'osm_id', 'protegido']
    list_select_related = ['municipio']
    actions = ['ocultar', 'publicar']
    def has_delete_permission(self, request, obj=None): return False

    def save_model(self, request, obj, form, change):
        obj.protegido = True
        super().save_model(request, obj, form, change)

    @admin.action(description='Ocultar lugares seleccionados', permissions=['change'])
    def ocultar(self, request, queryset):
        queryset.update(es_activo=False, protegido=True)

    @admin.action(description='Publicar lugares seleccionados', permissions=['change'])
    def publicar(self, request, queryset):
        queryset.update(es_activo=True, protegido=True)
