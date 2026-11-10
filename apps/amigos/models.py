"""Amigos "ligeros": solicitudes, amistades y bloqueos. Sin muro ni mensajes, a propósito."""
from django.conf import settings
from django.db import models
from django.db.models.functions import Greatest, Least


class Amistad(models.Model):
    """Un solo registro por pareja, sin importar quién envió la solicitud."""
    ESTADOS = [('pendiente', 'Pendiente'), ('aceptada', 'Aceptada'), ('rechazada', 'Rechazada')]
    de = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='solicitudes_enviadas')
    para = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='solicitudes_recibidas')
    estado = models.CharField(max_length=10, choices=ESTADOS, default='pendiente')
    creado = models.DateTimeField(auto_now_add=True)
    respondido = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'amistades'
        ordering = ['-creado', '-pk']
        constraints = [
            models.UniqueConstraint(Least('de', 'para'), Greatest('de', 'para'), name='una_amistad_por_pareja'),
            models.CheckConstraint(condition=~models.Q(de=models.F('para')), name='amistad_sin_autoamistad'),
        ]
        indexes = [models.Index(fields=['para', 'estado'], name='amistad_para_estado_idx')]

    def __str__(self):
        return f'{self.de_id} → {self.para_id} ({self.estado})'

    def otro(self, usuario):
        return self.para if self.de_id == usuario.pk else self.de


class Bloqueo(models.Model):
    """Quien bloquea deja de recibir solicitudes de `para` y desaparece de sus búsquedas y de su vista."""
    de = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bloqueos')
    para = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bloqueado_por')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['de', 'para'], name='un_bloqueo_por_pareja'),
            models.CheckConstraint(condition=~models.Q(de=models.F('para')), name='bloqueo_sin_autobloqueo'),
        ]
