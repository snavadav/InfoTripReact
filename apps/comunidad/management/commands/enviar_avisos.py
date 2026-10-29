"""Envía por correo los avisos de moderación pendientes. Pensado para ejecutarse cada pocos minutos.

Corre fuera de las peticiones web, así que un SMTP lento no retiene el admin. Cada aviso se
intenta hasta Notificacion.MAX_INTENTOS_CORREO veces; los fallos quedan en el registro
infotrip.correo. Varias ejecuciones simultáneas no envían el mismo aviso (skip_locked).
"""
import logging
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.comunidad.models import Notificacion

registro = logging.getLogger('infotrip.correo')


def cuerpo(aviso):
    lineas = [aviso.texto, '']
    if aviso.enlace:
        lineas.append(f'Puedes verlo aquí: {settings.PUBLIC_BASE_URL}{aviso.enlace}')
    lineas.append(f'Todos tus avisos están en {settings.PUBLIC_BASE_URL}/perfil/')
    return '\n'.join(lineas)


class Command(BaseCommand):
    help = 'Envía por correo los avisos de moderación pendientes.'

    def add_arguments(self, parser):
        parser.add_argument('--lote', type=int, default=50, help='Avisos como máximo por ejecución.')

    def handle(self, *args, lote, **opciones):
        enviados = fallidos = 0
        with transaction.atomic():
            pendientes = (Notificacion.objects.select_for_update(skip_locked=True, of=('self',))
                          .filter(correo_pendiente=True).select_related('usuario').order_by('creado', 'pk')[:lote])
            for aviso in pendientes:
                usuario = aviso.usuario
                if not usuario.es_activo or not usuario.email:
                    aviso.correo_pendiente = False
                    aviso.save(update_fields=['correo_pendiente'])
                    continue
                try:
                    if send_mail('Novedades sobre tu aporte en InfoTrip', cuerpo(aviso), settings.DEFAULT_FROM_EMAIL,
                                 [usuario.email], fail_silently=False) != 1:
                        raise SMTPException('El servidor no aceptó el mensaje.')
                except (SMTPException, OSError) as error:
                    aviso.correo_intentos += 1
                    aviso.correo_pendiente = aviso.correo_intentos < Notificacion.MAX_INTENTOS_CORREO
                    aviso.save(update_fields=['correo_intentos', 'correo_pendiente'])
                    registro.error('No se pudo enviar el aviso %s al usuario %s (intento %s): %r',
                                   aviso.pk, usuario.pk, aviso.correo_intentos, error)
                    fallidos += 1
                    continue
                aviso.correo_pendiente = False
                aviso.correo_enviado = timezone.now()
                aviso.save(update_fields=['correo_pendiente', 'correo_enviado'])
                enviados += 1
        if enviados or fallidos:
            registro.info('Avisos por correo: %s enviados, %s con error', enviados, fallidos)
        self.stdout.write(f'{enviados} enviados, {fallidos} con error.')
