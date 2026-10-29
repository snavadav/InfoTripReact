from django.contrib import admin
from django.db import transaction
from .models import Aporte, Reporte, Decision


def decidir(aporte, moderador, estado, motivo):
    anterior = aporte.estado
    if anterior == 'retirado' or anterior == estado:
        return
    aporte.estado = estado
    aporte.save(update_fields=['estado', 'actualizado'])
    Decision.objects.create(
        aporte=aporte, moderador=moderador, estado_anterior=anterior, estado_nuevo=estado, motivo=motivo
    )


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
                decidir(aporte, request.user, 'publicado', 'Revisión editorial: publicación desde administración.')
    @admin.action(description='Ocultar aportes seleccionados', permissions=['change'])
    def ocultar(self, request, queryset):
        with transaction.atomic():
            for aporte in queryset.select_for_update():
                decidir(aporte, request.user, 'oculto', 'Revisión editorial: ocultación desde administración.')


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
                decidir(aporte, request.user, 'oculto', f'Reporte {reporte.pk}: {reporte.motivo}')
                reporte.resuelto = True
                reporte.save(update_fields=['resuelto'])
    @admin.action(description='Desestimar reportes (conservar contenido)', permissions=['change'])
    def desestimar(self, request, queryset):
        with transaction.atomic():
            for reporte in queryset.filter(resuelto=False).select_for_update():
                aporte = Aporte.objects.select_for_update().get(pk=reporte.aporte_id)
                Decision.objects.create(aporte=aporte, moderador=request.user, estado_anterior=aporte.estado,
                    estado_nuevo=aporte.estado, motivo=f'Reporte {reporte.pk} desestimado: {reporte.motivo}')
                reporte.resuelto = True
                reporte.save(update_fields=['resuelto'])


@admin.register(Decision)
class DecisionAdmin(admin.ModelAdmin):
    list_display = ['aporte', 'moderador', 'estado_anterior', 'estado_nuevo', 'creado']
    readonly_fields = ['aporte', 'moderador', 'estado_anterior', 'estado_nuevo', 'motivo', 'creado']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


from .models import Colaboracion, RevisionColaboracion


def revisar_colaboracion(item, moderador, estado, motivo):
    """El llamador bloquea la fila dentro de una transacción."""
    if item.estado == estado:
        return
    RevisionColaboracion.objects.create(
        colaboracion=item, moderador=moderador, anterior=item.estado, nuevo=estado, motivo=motivo
    )
    item.estado = estado
    item.save(update_fields=['estado'])


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
                revisar_colaboracion(item, request.user, 'publicado', 'Publicación tras revisión editorial.')

    @admin.action(description='Ocultar información o conversación', permissions=['change'])
    def ocultar(self, request, queryset):
        with transaction.atomic():
            for item in queryset.select_for_update():
                revisar_colaboracion(item, request.user, 'oculto', 'Ocultación tras revisión editorial.')


@admin.register(RevisionColaboracion)
class RevisionColaboracionAdmin(admin.ModelAdmin):
    list_display = ['colaboracion', 'moderador', 'anterior', 'nuevo', 'creado']
    readonly_fields = ['colaboracion', 'moderador', 'anterior', 'nuevo', 'motivo', 'creado']
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
