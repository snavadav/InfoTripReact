from django.contrib import admin

from .models import EtiquetaLugar


@admin.register(EtiquetaLugar)
class EtiquetaLugarAdmin(admin.ModelAdmin):
    list_display = ('lugar', 'util', 'autor', 'creado')
    list_filter = ('util', 'lugar__tipo')
    search_fields = ('lugar__nombre',)
    raw_id_fields = ('lugar',)
    readonly_fields = ('autor', 'creado')

    def has_add_permission(self, request):
        return False  # Se etiqueta en /admin/etiquetar-lugares/, que registra quién lo hizo.
