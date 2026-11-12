"""
InfoTrip — apps/usuarios/admin.py
Registro del modelo Usuario en el panel de administración
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display  = ['email', 'username', 'nombre', 'apellido', 'es_verificado', 'es_staff', 'fecha_registro']
    list_filter   = ['es_staff', 'es_verificado', 'es_activo']
    search_fields = ['email', 'username', 'nombre', 'apellido']
    ordering      = ['-fecha_registro']
    date_hierarchy = 'fecha_registro'
    actions = ['desactivar']

    fieldsets = (
        ('Credenciales', {'fields': ('email', 'password')}),
        ('Información', {'fields': ('nombre', 'apellido', 'username', 'foto_perfil', 'ciudad_origen', 'bio')}),
        (
            'Permisos',
            {'fields': ('es_activo', 'es_staff', 'es_verificado', 'is_superuser', 'groups', 'user_permissions')},
        ),
        ('Fechas', {'fields': ('fecha_registro', 'ultimo_acceso')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('email', 'nombre', 'apellido', 'password1', 'password2'),
        }),
    )

    readonly_fields = ['fecha_registro', 'ultimo_acceso', 'uuid']

    @admin.action(description='Desactivar las cuentas seleccionadas (no pueden entrar; nada se borra)',
                  permissions=['change'])
    def desactivar(self, request, queryset):
        # Nunca la propia cuenta ni la de un superusuario: dejaría al equipo sin acceso por un clic de más.
        cuentas = list(queryset.filter(es_activo=True, is_superuser=False).exclude(pk=request.user.pk))
        for cuenta in cuentas:
            cuenta.es_activo = False
            cuenta.save(update_fields=['es_activo'])
            self.log_change(request, cuenta, 'Cuenta desactivada desde la lista.')
        omitidas = queryset.count() - len(cuentas)
        aviso = f'{len(cuentas)} cuentas desactivadas.'
        if omitidas:
            aviso += f' {omitidas} se dejaron como estaban (ya inactivas, superusuarios o tu propia cuenta).'
        self.message_user(request, aviso)
