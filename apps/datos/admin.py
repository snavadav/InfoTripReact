from django.contrib import admin, messages
from django.utils.html import format_html

from .models import EjecucionTarea, FuenteOficial, PropuestaActualizacion
from .moderacion import PropuestaNoAplicable, aprobar, rechazar


@admin.register(EjecucionTarea)
class EjecucionTareaAdmin(admin.ModelAdmin):
    """Bitácora de las tareas programadas: solo lectura."""
    list_display = ['tarea', 'resultado', 'inicio', 'fin', 'resumen']
    list_filter = ['tarea', 'resultado']
    readonly_fields = ['tarea', 'resultado', 'inicio', 'fin', 'mensaje', 'conteos']

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    @admin.display(description='Resumen')
    def resumen(self, obj):
        if obj.mensaje:
            return obj.mensaje[:120]
        return ', '.join(f'{clave} {valor}' for clave, valor in obj.conteos.items())


@admin.register(FuenteOficial)
class FuenteOficialAdmin(admin.ModelAdmin):
    """Lista cerrada de sitios oficiales. Google, TripAdvisor, Facebook y similares se rechazan al guardar."""
    list_display = ['nombre', 'objetivo', 'tipo_dato', 'activo', 'estado', 'ultima_revision', 'frecuencia_dias']
    list_filter = ['tipo_dato', 'activo', 'estado']
    search_fields = ['nombre', 'url', 'destino__nombre', 'lugar__nombre']
    autocomplete_fields = ['destino', 'lugar', 'referencia']
    readonly_fields = ['estado', 'nota', 'ultima_revision', 'huella']
    list_select_related = ['destino', 'lugar']
    actions = ['revisar_de_nuevo']

    @admin.action(description='Revisar en la próxima corrida (olvida la huella)', permissions=['change'])
    def revisar_de_nuevo(self, request, queryset):
        queryset.update(huella='', ultima_revision=None)


@admin.register(PropuestaActualizacion)
class PropuestaActualizacionAdmin(admin.ModelAdmin):
    """Dato anterior → dato nuevo, con la cita y la fuente. Aprobar lo publica; rechazar lo descarta."""
    list_display = ['objetivo', 'tipo_dato', 'cambio', 'ver_fuente', 'estado', 'creado']
    list_filter = ['estado', 'tipo_dato']
    search_fields = ['fuente__nombre', 'fuente__destino__nombre', 'fuente__lugar__nombre', 'cita']
    readonly_fields = ['fuente', 'tipo_dato', 'dato_anterior', 'dato_nuevo', 'cita', 'ver_fuente', 'fecha_consulta',
                       'modelo_ia', 'estado', 'creado', 'revisado', 'revisado_por']
    fields = readonly_fields
    list_select_related = ['fuente__destino', 'fuente__lugar']
    actions = ['aprobar', 'rechazar']

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

    @admin.display(description='Destino o lugar')
    def objetivo(self, obj):
        return obj.fuente.objetivo

    @admin.display(description='Cambio')
    def cambio(self, obj):
        return f'{obj.dato_anterior or "—"} → {obj.dato_nuevo}'

    @admin.display(description='Fuente')
    def ver_fuente(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">ver fuente</a>', obj.url)

    @admin.action(description='Aprobar y publicar las propuestas seleccionadas', permissions=['change'])
    def aprobar(self, request, queryset):
        hechas = 0
        for propuesta in queryset.filter(estado='pendiente'):
            try:
                hechas += aprobar(propuesta, request.user)
            except PropuestaNoAplicable as error:
                self.message_user(request, f'{propuesta}: {error}', messages.WARNING)
        self.message_user(request, f'{hechas} propuestas aprobadas y publicadas.')

    @admin.action(description='Rechazar las propuestas seleccionadas', permissions=['change'])
    def rechazar(self, request, queryset):
        hechas = sum(rechazar(propuesta, request.user) for propuesta in queryset.filter(estado='pendiente'))
        self.message_user(request, f'{hechas} propuestas rechazadas.')
