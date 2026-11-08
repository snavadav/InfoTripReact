"""Crea el grupo "Moderación" y, con --agregar, da acceso a una persona del equipo sin hacerla superusuaria.

Quien modera puede revisar la cola, publicar y ocultar contenido, resolver reportes y corregir destinos y lugares.
No puede borrar nada, crear cuentas ni cambiar permisos.
"""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

from apps.usuarios.models import Usuario

GRUPO = 'Moderación'
PERMISOS = {
    'comunidad': {
        'aporte': ('view', 'change'), 'colaboracion': ('view', 'change'), 'resenalugar': ('view', 'change'),
        'propuestalugar': ('view', 'change'), 'reporte': ('view', 'change'), 'reportecolaboracion': ('view', 'change'),
        'reporteresenalugar': ('view', 'change'), 'decision': ('view',), 'revisioncolaboracion': ('view',),
        'revisionresenalugar': ('view',), 'revisionpropuestalugar': ('view',), 'confirmacion': ('view', 'delete'),
        'confirmacionlugar': ('view', 'delete'), 'comentario': ('view', 'change'), 'interesnegocio': ('view', 'change'),
    },
    'destinos': {'destino': ('view', 'change'), 'lugar': ('view', 'change')},
    'metricas': {'evento': ('view',)},
    'curador': {'etiquetalugar': ('view', 'add', 'change')},
}


def grupo_de_moderacion():
    grupo, _ = Group.objects.get_or_create(name=GRUPO)
    codigos = [(app, f'{accion}_{modelo}') for app, modelos in PERMISOS.items()
               for modelo, acciones in modelos.items() for accion in acciones]
    permisos = [Permission.objects.get(content_type__app_label=app, codename=codigo) for app, codigo in codigos]
    grupo.permissions.set(permisos)
    return grupo


class Command(BaseCommand):
    help = 'Crea o actualiza el grupo "Moderación"; con --agregar CORREO, suma a esa persona.'

    def add_arguments(self, parser):
        parser.add_argument('--agregar', metavar='CORREO', help='Correo de una cuenta ya registrada.')

    def handle(self, *args, agregar, **opciones):
        grupo = grupo_de_moderacion()
        self.stdout.write(self.style.SUCCESS(f'Grupo "{GRUPO}" con {grupo.permissions.count()} permisos.'))
        if not agregar:
            return
        usuario = Usuario.objects.filter(email__iexact=agregar, es_activo=True).first()
        if not usuario:
            raise CommandError('No hay una cuenta activa con ese correo. Primero debe registrarse.')
        usuario.es_staff = True
        usuario.save(update_fields=['es_staff'])
        usuario.groups.add(grupo)
        self.stdout.write(self.style.SUCCESS(f'{usuario.nombre} ya puede moderar en /admin/moderacion/.'))
