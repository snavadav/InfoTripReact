"""Envía al equipo, como mucho una vez al día, un correo con lo que espera en la cola de moderación.

Sin pendientes ni fallos no se envía nada. Lo reciben las cuentas activas del grupo "Moderación" y los
superusuarios. El correo solo lleva totales y el enlace a la cola: ningún texto ni nombre de la comunidad.
Lo llama el servicio `avisos` (docker-compose.yml); a mano, `--forzar` lo envía aunque ya saliera hoy.
"""
import logging
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.comunidad.salud import fallos, pendientes
from apps.usuarios.models import Usuario
from .crear_moderacion import GRUPO

registro = logging.getLogger('infotrip.correo')
# El servicio lo intenta cada hora: antes de esta hora (de México) no sale, para que no llegue de madrugada.
HORA_MINIMA = 8


def destinatarios():
    return list(Usuario.objects.filter(Q(groups__name=GRUPO) | Q(is_superuser=True), es_activo=True)
                .exclude(email='').values_list('email', flat=True).distinct())


def cuerpo(cola, errores):
    lineas = []
    if cola:
        lineas += ['Esperan revisión:', *[f'- {titulo}: {total}' for titulo, total in cola], '',
                   f'Cola de moderación: {settings.PUBLIC_BASE_URL}/admin/moderacion/']
    if errores:
        lineas += ['', 'En las últimas 24 horas:', *[f'- {titulo}: {total}' for titulo, total in errores], '',
                   f'Bitácora de tareas: {settings.PUBLIC_BASE_URL}/admin/datos/ejecuciontarea/']
    return '\n'.join(lineas).strip()


class Command(BaseCommand):
    help = 'Envía al equipo el resumen diario de la cola de moderación, si hay algo pendiente.'

    def add_arguments(self, parser):
        parser.add_argument('--forzar', action='store_true', help='Enviarlo aunque ya se haya enviado hoy.')

    def handle(self, *args, forzar, **opciones):
        cola, errores = pendientes(), fallos(timezone.now() - timedelta(hours=24))
        if not cola and not errores:
            self.stdout.write('Nada pendiente: no se envía resumen.')
            return
        if not forzar and timezone.localtime().hour < HORA_MINIMA:
            self.stdout.write(f'Antes de las {HORA_MINIMA}:00 no se envía el resumen.')
            return
        correos = destinatarios()
        if not correos:
            self.stdout.write('Nadie del equipo tiene correo: no se envía resumen.')
            return
        # `cache.add` es atómico en Redis: aunque el servicio se reinicie varias veces, sale uno por día.
        clave = f'resumen_moderacion:{timezone.localdate():%Y-%m-%d}'
        if not forzar and not cache.add(clave, 1, 24 * 3600):
            self.stdout.write('El resumen de hoy ya se envió.')
            return
        total = sum(cantidad for _, cantidad in cola)
        asunto = f'InfoTrip: {total} por revisar' if cola else 'InfoTrip: fallos en tareas o correos'
        try:
            # Un mensaje por persona: nadie ve el correo de los demás.
            for correo in correos:
                send_mail(asunto, cuerpo(cola, errores), settings.DEFAULT_FROM_EMAIL, [correo], fail_silently=False)
        except (SMTPException, OSError) as error:
            cache.delete(clave)
            registro.error('No se pudo enviar el resumen de moderación: %r', error)
            self.stdout.write('No se pudo enviar el resumen.')
            return
        registro.info('Resumen de moderación enviado a %s personas', len(correos))
        self.stdout.write(f'Resumen enviado a {len(correos)} personas.')
