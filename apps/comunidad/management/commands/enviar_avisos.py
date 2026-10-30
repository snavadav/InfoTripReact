"""Envía por correo los avisos de moderación pendientes. Pensado para ejecutarse cada pocos minutos.

Corre fuera de las peticiones web, así que un SMTP lento no retiene el admin. Cada aviso se
intenta hasta Notificacion.MAX_INTENTOS_CORREO veces; los fallos quedan en el registro
infotrip.correo. Varias ejecuciones simultáneas no envían el mismo aviso (skip_locked).
"""
import logging
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.comunidad.models import Notificacion, Viaje
from apps.usuarios.sesion import token_baja_avisos

registro = logging.getLogger('infotrip.correo')


def cuerpo(aviso):
    base = settings.PUBLIC_BASE_URL
    lineas = [aviso.texto, '']
    if aviso.enlace:
        lineas.append(f'Puedes verlo aquí: {base}{aviso.enlace}?ref=aviso')
    lineas.append(f'Todos tus avisos están en {base}/perfil/')
    lineas += ['', f'¿Ya no quieres estos correos? {base}/baja-avisos/?t={token_baja_avisos(aviso.usuario)}']
    return '\n'.join(lineas)


def generar_recordatorios():
    """Invita a contar cómo le fue a quien terminó una escapada en las últimas dos semanas, una sola vez."""
    hoy = timezone.localdate()
    viajes = (Viaje.objects.filter(fecha_fin__lt=hoy, fecha_fin__gte=hoy - timedelta(days=14),
                                   recordatorio_enviado__isnull=True, autor__es_activo=True)
              .select_related('autor').prefetch_related('lugares'))
    for viaje in viajes:
        lugar = next((destino for destino in viaje.lugares.all() if destino.es_activo), None)
        enlace = reverse('destino-detalle', kwargs={'slug': lugar.slug}) if lugar else reverse('mis-viajes')
        Notificacion.objects.create(
            usuario=viaje.autor, enlace=enlace, correo_pendiente=True,
            texto=f'¿Cómo te fue en «{viaje.nombre}»? Tu reseña o confirmar un dato ayuda al siguiente viajero.',
        )
        viaje.recordatorio_enviado = timezone.now()
        viaje.save(update_fields=['recordatorio_enviado'])


class Command(BaseCommand):
    help = 'Envía por correo los avisos de moderación pendientes.'

    def add_arguments(self, parser):
        parser.add_argument('--lote', type=int, default=50, help='Avisos como máximo por ejecución.')

    def handle(self, *args, lote, **opciones):
        enviados = fallidos = 0
        with transaction.atomic():
            generar_recordatorios()
            pendientes = (Notificacion.objects.select_for_update(skip_locked=True, of=('self',))
                          .filter(correo_pendiente=True).select_related('usuario').order_by('creado', 'pk')[:lote])
            for aviso in pendientes:
                usuario = aviso.usuario
                if not usuario.es_activo or not usuario.email or not usuario.avisos_correo:
                    aviso.correo_pendiente = False
                    aviso.save(update_fields=['correo_pendiente'])
                    continue
                try:
                    if send_mail('Novedades en InfoTrip', cuerpo(aviso), settings.DEFAULT_FROM_EMAIL,
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
