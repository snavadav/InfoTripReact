"""Aprobar o rechazar lo que propone el lector de sitios oficiales. Solo aquí se publica un dato nuevo."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import PropuestaActualizacion


class PropuestaNoAplicable(Exception):
    """La propuesta ya no se puede aplicar (por ejemplo, se borró la referencia que actualizaba)."""


@transaction.atomic
def aprobar(propuesta, usuario):
    """Publica el dato con su fuente y fecha de consulta. Solo propuestas pendientes."""
    propuesta = PropuestaActualizacion.objects.select_for_update().select_related(
        'fuente__referencia', 'fuente__destino', 'fuente__lugar').get(pk=propuesta.pk)
    if propuesta.estado != 'pendiente':
        return False
    fuente = propuesta.fuente
    if propuesta.tipo_dato == 'precio':
        referencia = fuente.referencia
        if referencia is None:
            raise PropuestaNoAplicable('La referencia de costo de esta fuente ya no existe.')
        referencia.monto = Decimal(propuesta.dato_nuevo)
        referencia.fecha_consulta = propuesta.fecha_consulta
        referencia.save(update_fields=['monto', 'fecha_consulta'])
    else:
        objetivo = fuente.objetivo
        objetivo.horario = propuesta.dato_nuevo
        objetivo.horario_fuente_url = propuesta.url
        objetivo.horario_fecha_consulta = propuesta.fecha_consulta
        objetivo.save(update_fields=['horario', 'horario_fuente_url', 'horario_fecha_consulta',
                                     'fecha_actualizacion'])
    _cerrar(propuesta, 'aprobada', usuario)
    return True


def rechazar(propuesta, usuario):
    """Descarta la propuesta. El dato publicado no cambia."""
    if propuesta.estado != 'pendiente':
        return False
    _cerrar(propuesta, 'rechazada', usuario)
    return True


def _cerrar(propuesta, estado, usuario):
    propuesta.estado, propuesta.revisado, propuesta.revisado_por = estado, timezone.now(), usuario
    propuesta.save(update_fields=['estado', 'revisado', 'revisado_por'])
