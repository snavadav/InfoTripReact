from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class CatalogoBase(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=160, unique=True)

    class Meta:
        abstract = True
        ordering = ['nombre', 'pk']

    def __str__(self):
        return self.nombre


class Region(CatalogoBase):
    class Meta(CatalogoBase.Meta):
        abstract = False
        verbose_name = 'Región'
        verbose_name_plural = 'Regiones'


class Municipio(CatalogoBase):
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name='municipios')


class Categoria(CatalogoBase):
    class Meta(CatalogoBase.Meta):
        abstract = False
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'


class Servicio(CatalogoBase):
    pass


class Destino(models.Model):
    nombre = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    descripcion = models.TextField()
    municipio = models.ForeignKey(Municipio, on_delete=models.PROTECT, related_name='destinos')
    categorias = models.ManyToManyField(Categoria, related_name='destinos', blank=True)
    servicios = models.ManyToManyField(Servicio, related_name='destinos', blank=True)
    direccion = models.CharField(max_length=300, blank=True)
    latitud = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(Decimal('-90')), MaxValueValidator(Decimal('90'))],
    )
    longitud = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(Decimal('-180')), MaxValueValidator(Decimal('180'))],
    )
    es_activo = models.BooleanField(default=True)
    # Procedencia de OpenStreetMap (por ejemplo, node/123). Su licencia exige dar crédito e identificar estos datos.
    osm_id = models.CharField(max_length=30, null=True, blank=True, unique=True, editable=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nombre', 'pk']
        indexes = [models.Index(fields=['es_activo', 'nombre'], name='destino_activo_nombre_idx')]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(latitud__gte=-90, latitud__lte=90), name='destino_latitud_valida'
            ),
            models.CheckConstraint(
                condition=models.Q(longitud__gte=-180, longitud__lte=180), name='destino_longitud_valida'
            ),
        ]

    def __str__(self):
        return self.nombre
