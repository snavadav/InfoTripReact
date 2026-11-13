"""Genera los recordatorios del día y envía por correo los avisos pendientes. Pensado para cada pocos minutos.

Corre fuera de las peticiones web, así que un SMTP lento no retiene el admin. Cada aviso se
intenta hasta Notificacion.MAX_INTENTOS_CORREO veces; los fallos quedan en el registro
infotrip.correo. Varias ejecuciones simultáneas no envían el mismo aviso (skip_locked) ni crean
el mismo recordatorio (clave única).

Para probar: `manage.py enviar_avisos --forzar` crea los recordatorios sin esperar la hora;
`--fecha 2026-12-24` hace como si fuera ese día; `--sin-correo` solo los crea.
"""
import logging
from datetime import date, datetime
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.comunidad.avisos_programados import generar
from apps.comunidad.models import Notificacion
from apps.comunidad.notificar import con_aviso, datos_tipo, hay_bloqueo, quiere_correo
from apps.usuarios.sesion import token_baja_avisos

registro = logging.getLogger('infotrip.correo')


def cuerpo(aviso):
    base = settings.PUBLIC_BASE_URL
    lineas = [aviso.texto, '']
    if aviso.enlace:
        lineas.append(f'{datos_tipo(aviso.tipo)["accion"]}: {base}{con_aviso(aviso.enlace, aviso.pk, ref=True)}')
    lineas.append(f'Todos tus avisos están en {base}/perfil/#notices-title')
    lineas += ['', f'Elige qué avisos te llegan por correo en {base}/perfil/#avisos-preferencias',
               f'¿Ya no quieres estos correos? {base}/baja-avisos/?t={token_baja_avisos(aviso.usuario)}']
    return '\n'.join(lineas)


def sigue_vigente(aviso):
    """Si al enviarlo la persona aún lo quiere por correo y quien lo provocó no la bloqueó ni se dio de baja."""
    if not aviso.usuario.es_activo or not quiere_correo(aviso.usuario, aviso.tipo):
        return False
    return not aviso.actor or (aviso.actor.es_activo and not hay_bloqueo(aviso.actor, aviso.usuario))


class Command(BaseCommand):
    help = 'Genera los recordatorios del día y envía por correo los avisos pendientes.'

    def add_arguments(self, parser):
        parser.add_argument('--lote', type=int, default=50, help='Avisos como máximo por ejecución.')
        parser.add_argument('--forzar', action='store_true',
                            help='Crea los recordatorios aunque no sea la hora (útil para probar).')
        parser.add_argument('--fecha', type=date.fromisoformat, help='Hace como si hoy fuera esta fecha (AAAA-MM-DD).')
        parser.add_argument('--sin-correo', action='store_true', help='Solo crea los recordatorios; no envía.')

    def handle(self, *args, lote, forzar=False, fecha=None, sin_correo=False, **opciones):
        ahora = timezone.localtime()
        if fecha:
            ahora = timezone.make_aware(datetime.combine(fecha, ahora.time()))
        with transaction.atomic():
            creados = generar(ahora, forzar=forzar)
        nuevos = sum(creados.values())
        if nuevos:
            self.stdout.write('Recordatorios nuevos: ' + ', '.join(f'{tipo} {n}' for tipo, n in creados.items() if n))
        if sin_correo:
            return
        enviados = fallidos = 0
        with transaction.atomic():
            pendientes = (Notificacion.objects.select_for_update(skip_locked=True, of=('self',))
                          .filter(correo_pendiente=True).select_related('usuario', 'actor')
                          .order_by('creado', 'pk')[:lote])
            for aviso in pendientes:
                usuario = aviso.usuario
                if not sigue_vigente(aviso):
                    aviso.correo_pendiente = False
                    aviso.save(update_fields=['correo_pendiente'])
                    continue
                try:
                    if send_mail(datos_tipo(aviso.tipo)['asunto'], cuerpo(aviso), settings.DEFAULT_FROM_EMAIL,
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
