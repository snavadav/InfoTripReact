from django.contrib import admin
from .models import Destino, Region, Municipio, Categoria, Servicio


@admin.register(Destino)
class DestinoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'municipio', 'es_activo']
    list_filter = ['es_activo', 'municipio__region', 'categorias']
    search_fields = ['nombre', 'municipio__nombre']
    prepopulated_fields = {'slug': ('nombre',)}
    filter_horizontal = ['categorias', 'servicios']
    readonly_fields = ['fecha_creacion', 'fecha_actualizacion']
    def has_delete_permission(self, request, obj=None): return False


class CatalogoAdmin(admin.ModelAdmin):
    search_fields = ['nombre']
    prepopulated_fields = {'slug': ('nombre',)}

for modelo in [Region, Municipio, Categoria, Servicio]:
    admin.site.register(modelo, CatalogoAdmin)
