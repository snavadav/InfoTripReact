"""Rutas del planeador guardadas para compartirlas por enlace."""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

# Sin cuenta, el enlace dura lo que una temporada de viaje; con cuenta, hasta que la persona la borre.
DIAS_DE_VIDA_ANONIMA = 90


class RutasQuerySet(models.QuerySet):
    def vigentes(self):
        return self.filter(models.Q(caduca__isnull=True) | models.Q(caduca__gt=timezone.now()))

    def caducadas(self):
        return self.filter(caduca__lte=timezone.now())


class RutaCompartida(models.Model):
    """Los parámetros y el resultado de una ruta. Nunca guarda la ubicación de quien la armó."""
    enlace = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
                              related_name='rutas_compartidas')
    titulo = models.CharField(max_length=160)
    # Municipio de salida o, si salió desde la ubicación, el municipio más cercano; nunca coordenadas.
    origen_nombre = models.CharField(max_length=160)
    parametros = models.JSONField()
    plan = models.JSONField()
    creada = models.DateTimeField(auto_now_add=True)
    caduca = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = RutasQuerySet.as_manager()

    class Meta:
        ordering = ['-creada']
        verbose_name = 'ruta compartida'
        verbose_name_plural = 'rutas compartidas'

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        if self._state.adding and self.autor_id is None and self.caduca is None:
            self.caduca = timezone.now() + timedelta(days=DIAS_DE_VIDA_ANONIMA)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('ruta-compartida', args=[self.enlace])

    @property
    def caducada(self):
        return self.caduca is not None and self.caduca <= timezone.now()
