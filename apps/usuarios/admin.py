"""
InfoTrip — apps/usuarios/admin.py
Registro del modelo Usuario en el panel de administración
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display  = ['email', 'nombre', 'apellido', 'es_verificado', 'es_staff', 'fecha_registro']
    list_filter   = ['es_staff', 'es_verificado', 'es_activo']
    search_fields = ['email', 'nombre', 'apellido']
    ordering      = ['-fecha_registro']

    fieldsets = (
        ('Credenciales', {'fields': ('email', 'password')}),
        ('Información', {'fields': ('nombre', 'apellido', 'foto_perfil', 'ciudad_origen', 'bio')}),
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
