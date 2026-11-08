"""Decisiones humanas sobre los lugares importados: son los ejemplos con los que aprende el curador.

Ninguna etiqueta se genera de forma automática. Cada una la da una persona del equipo, y cada persona etiqueta un
lugar a lo más una vez; así se puede medir también cuánto coinciden dos personas sobre el mismo lugar.
"""
from django.conf import settings
from django.db import models

from apps.destinos.models import Lugar


class EtiquetaLugar(models.Model):
    lugar = models.ForeignKey(Lugar, on_delete=models.CASCADE, related_name='etiquetas')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='etiquetas_lugar')
    # None = "No sé": se guarda para no volver a mostrarlo a esa persona, pero no se usa para entrenar.
    util = models.BooleanField(null=True, verbose_name='¿le sirve a un viajero?')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado', '-pk']
        verbose_name = 'etiqueta de lugar'
        verbose_name_plural = 'etiquetas de lugares'
        constraints = [models.UniqueConstraint(fields=['lugar', 'autor'], name='una_etiqueta_por_persona')]

    def __str__(self):
        respuesta = {True: 'sirve', False: 'no sirve', None: 'no sé'}[self.util]
        return f'{self.lugar.nombre}: {respuesta}'
