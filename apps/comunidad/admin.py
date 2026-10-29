from django.contrib import admin
from django.db import transaction
from .models import Aporte, Colaboracion, Confirmacion, Decision, Reporte, RevisionColaboracion
from .moderacion import moderar


@admin.register(Aporte)
class AporteAdmin(admin.ModelAdmin):
    list_display = ['id', 'destino', 'autor', 'tipo', 'estado', 'fecha_visita']
    list_filter = ['estado', 'tipo']
    search_fields = ['destino__nombre', 'autor__email', 'texto']
    readonly_fields = [
        'destino',
        'autor',
        'tipo',
        'texto',
        'fecha_visita',
        'calificacion',
        'imagen',
        'monto',
        'concepto',
        'estado',
        'creado',
        'actualizado',
    ]
    actions = ['publicar', 'ocultar']
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    @admin.action(description='Publicar aportes seleccionados', permissions=['change'])
    def publicar(self, request, queryset):
        with transaction.atomic():
            for aporte in queryset.select_for_update():
                moderar(aporte, request.user, 'publicado', 'Revisión editorial: publicación desde administración.')
    @admin.action(description='Ocultar aportes seleccionados', permissions=['change'])
    def ocultar(self, request, queryset):
        with transaction.atomic():
            for aporte in queryset.select_for_update():
                moderar(aporte, request.user, 'oculto', 'Revisión editorial: ocultación desde administración.')


@admin.register(Reporte)
class ReporteAdmin(admin.ModelAdmin):
    list_display = ['id', 'aporte', 'autor', 'resuelto', 'creado']
    list_filter = ['resuelto']
    readonly_fields = ['aporte', 'autor', 'motivo', 'resuelto', 'creado']
    actions = ['resolver_ocultando', 'desestimar']
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.has_perm('comunidad.change_aporte'):
            actions.pop('resolver_ocultando', None)
        return actions
    @admin.action(description='Resolver y ocultar contenido reportado', permissions=['change'])
    def resolver_ocultando(self, request, queryset):
        if not request.user.has_perm('comunidad.change_aporte'): return
        with transaction.atomic():
            for reporte in queryset.filter(resuelto=False).select_for_update():
                aporte = Aporte.objects.select_for_update().get(pk=reporte.aporte_id)
                moderar(aporte, request.user, 'oculto', f'Reporte {reporte.pk}: {reporte.motivo}')
                reporte.resuelto = True
                reporte.save(update_fields=['resuelto'])
    @admin.action(description='Desestimar reportes (conservar contenido)', permissions=['change'])
    def desestimar(self, request, queryset):
        with transaction.atomic():
            for reporte in queryset.filter(resuelto=False).select_for_update():
                aporte = Aporte.objects.select_for_update().get(pk=reporte.aporte_id)
                motivo = f'Reporte {reporte.pk} desestimado: {reporte.motivo}'
                moderar(aporte, request.user, aporte.estado, motivo, registrar_sin_cambio=True)
                reporte.resuelto = True
                reporte.save(update_fields=['resuelto'])


@admin.register(Decision)
class DecisionAdmin(admin.ModelAdmin):
    list_display = ['aporte', 'moderador', 'estado_anterior', 'estado_nuevo', 'creado']
    readonly_fields = ['aporte', 'moderador', 'estado_anterior', 'estado_nuevo', 'motivo', 'creado']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(Colaboracion)
class ColaboracionAdmin(admin.ModelAdmin):
    list_display = ['id', 'destino', 'tipo', 'campo', 'estado', 'fecha_dato', 'creado']
    list_filter = ['estado', 'tipo', 'campo']
    search_fields = ['destino__nombre', 'texto', 'fuente']
    readonly_fields = [
        'destino',
        'autor',
        'tipo',
        'campo',
        'texto',
        'fuente',
        'fecha_dato',
        'pregunta',
        'estado',
        'creado',
    ]
    actions = ['publicar', 'ocultar']

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

    @admin.action(description='Publicar información o conversación revisada', permissions=['change'])
    def publicar(self, request, queryset):
        with transaction.atomic():
            for item in queryset.select_for_update():
                moderar(item, request.user, 'publicado', 'Publicación tras revisión editorial.')

    @admin.action(description='Ocultar información o conversación', permissions=['change'])
    def ocultar(self, request, queryset):
        with transaction.atomic():
            for item in queryset.select_for_update():
                moderar(item, request.user, 'oculto', 'Ocultación tras revisión editorial.')


@admin.register(RevisionColaboracion)
class RevisionColaboracionAdmin(admin.ModelAdmin):
    list_display = ['colaboracion', 'moderador', 'estado_anterior', 'estado_nuevo', 'creado']
    readonly_fields = ['colaboracion', 'moderador', 'estado_anterior', 'estado_nuevo', 'motivo', 'creado']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(Confirmacion)
class ConfirmacionAdmin(admin.ModelAdmin):
    """Confirmaciones de "¿Sigue vigente?": no se editan; el personal puede borrar las abusivas."""
    list_display = ['dato', 'autor', 'fecha', 'creado']
    search_fields = ['dato__destino__nombre', 'autor__email']
    readonly_fields = ['dato', 'autor', 'fecha', 'creado']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
