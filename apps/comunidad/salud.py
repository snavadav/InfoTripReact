"""Estado de la operación para el equipo: qué espera en la cola y qué falló.

Lo usan el resumen diario por correo (`resumen_moderacion`), el panel de métricas y el bloque de salud del
inicio del admin. Solo cuenta: nunca devuelve texto ni nombres de la comunidad.
"""
from datetime import timedelta

from django.utils import timezone

from apps.datos.models import EjecucionTarea, PropuestaActualizacion
from .models import (
    Aporte, Colaboracion, Comentario, FotoPasaporte, Notificacion, PropuestaLugar, Reporte, ReporteColaboracion,
    ReporteResenaLugar, ResenaLugar,
)


def _en_cola():
    """(título, consulta, campo de fecha) de lo que espera una decisión, en el orden de la cola."""
    return [
        ('Aportes pendientes', Aporte.objects.filter(estado='pendiente')),
        ('Colaboraciones pendientes', Colaboracion.objects.filter(estado='pendiente')),
        ('Reseñas de lugares pendientes', ResenaLugar.objects.filter(estado='pendiente')),
        ('Lugares propuestos', PropuestaLugar.objects.filter(estado='pendiente')),
        ('Fotos de pasaporte por revisar', FotoPasaporte.objects.filter(estado='pendiente', mostrar=True)),
        ('Reportes abiertos', Reporte.objects.filter(resuelto=False)),
        ('Reportes de información abiertos', ReporteColaboracion.objects.filter(resuelto=False)),
        ('Reportes de reseñas de lugares abiertos', ReporteResenaLugar.objects.filter(resuelto=False)),
        ('Actualizaciones de fuentes oficiales', PropuestaActualizacion.objects.filter(estado='pendiente')),
        ('Comentarios del sitio sin atender', Comentario.objects.filter(atendido=False)),
    ]


def pendientes():
    """[(título, total)] de lo que espera una decisión. Solo lo que tiene algo."""
    return [(titulo, total) for titulo, consulta in _en_cola() if (total := consulta.count())]


def total_en_cola():
    return sum(total for _, total in pendientes())


def dias_del_mas_antiguo():
    """Días que lleva esperando lo más viejo de la cola; None si está vacía."""
    fechas = [consulta.order_by('creado').values_list('creado', flat=True).first() for _, consulta in _en_cola()]
    fechas = [fecha for fecha in fechas if fecha]
    return (timezone.now() - min(fechas)).days if fechas else None


def correos_fallidos(desde):
    return Notificacion.objects.filter(correo_intentos__gte=Notificacion.MAX_INTENTOS_CORREO,
                                       correo_enviado__isnull=True, creado__gte=desde)


def fallos(desde):
    """[(título, total)] de lo que falló desde `desde`: tareas programadas y correos que ya no se reintentan."""
    filas = [
        ('Tareas programadas con error', EjecucionTarea.objects.filter(resultado='error', inicio__gte=desde)),
        ('Avisos por correo que no se pudieron enviar', correos_fallidos(desde)),
    ]
    return [(titulo, total) for titulo, consulta in filas if (total := consulta.count())]


def ultima_corrida_de_cada_tarea():
    """La corrida más reciente de cada tarea programada; una tarea que nunca corrió aparece sin corrida."""
    filas = []
    for clave, nombre in EjecucionTarea.TAREAS:
        filas.append({'nombre': nombre, 'corrida': EjecucionTarea.objects.filter(tarea=clave).first()})
    return filas


def resumen():
    """Todo lo que muestra el bloque de salud del inicio del admin."""
    semana = timezone.now() - timedelta(days=7)
    return {
        'en_cola': total_en_cola(), 'dias_mas_antiguo': dias_del_mas_antiguo(),
        'correos_fallidos': correos_fallidos(semana).count(), 'tareas': ultima_corrida_de_cada_tarea(),
    }
