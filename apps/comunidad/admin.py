from django.contrib import admin
from django.db import transaction
from django.utils import timezone
from .models import Aporte, Colaboracion, Confirmacion, Decision, Reporte, ReporteColaboracion, RevisionColaboracion
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


class ReporteAdminBase(admin.ModelAdmin):
    """Resolver un reporte oculta el contenido; desestimarlo lo conserva. Ambos dejan constancia."""
    modelo_contenido = None
    campo_contenido = None
    permiso_contenido = None
    list_filter = ['resuelto']
    actions = ['resolver_ocultando', 'desestimar']
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.has_perm(self.permiso_contenido):
            actions.pop('resolver_ocultando', None)
        return actions

    def contenido(self, reporte):
        pk = getattr(reporte, f'{self.campo_contenido}_id')
        return self.modelo_contenido.objects.select_for_update().get(pk=pk)

    def cerrar(self, reporte):
        reporte.resuelto = True
        reporte.resuelto_en = timezone.now()
        reporte.save(update_fields=['resuelto', 'resuelto_en'])

    @admin.action(description='Resolver y ocultar contenido reportado', permissions=['change'])
    def resolver_ocultando(self, request, queryset):
        if not request.user.has_perm(self.permiso_contenido): return
        with transaction.atomic():
            for reporte in queryset.filter(resuelto=False).select_for_update():
                moderar(self.contenido(reporte), request.user, 'oculto', f'Reporte {reporte.pk}: {reporte.motivo}')
                self.cerrar(reporte)

    @admin.action(description='Desestimar reportes (conservar contenido)', permissions=['change'])
    def desestimar(self, request, queryset):
        with transaction.atomic():
            for reporte in queryset.filter(resuelto=False).select_for_update():
                objeto = self.contenido(reporte)
                motivo = f'Reporte {reporte.pk} desestimado: {reporte.motivo}'
                moderar(objeto, request.user, objeto.estado, motivo, registrar_sin_cambio=True)
                self.cerrar(reporte)


@admin.register(Reporte)
class ReporteAdmin(ReporteAdminBase):
    modelo_contenido = Aporte
    campo_contenido = 'aporte'
    permiso_contenido = 'comunidad.change_aporte'
    list_display = ['id', 'aporte', 'autor', 'resuelto', 'creado']
    readonly_fields = ['aporte', 'autor', 'motivo', 'resuelto', 'resuelto_en', 'creado']


@admin.register(ReporteColaboracion)
class ReporteColaboracionAdmin(ReporteAdminBase):
    modelo_contenido = Colaboracion
    campo_contenido = 'colaboracion'
    permiso_contenido = 'comunidad.change_colaboracion'
    list_display = ['id', 'colaboracion', 'autor', 'resuelto', 'creado']
    readonly_fields = ['colaboracion', 'autor', 'motivo', 'resuelto', 'resuelto_en', 'creado']


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
