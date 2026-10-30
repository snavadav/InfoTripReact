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


TIPOS_DE_LUGAR = [('comer', 'Comer'), ('dormir', 'Dormir'), ('gasolina', 'Gasolina'), ('farmacia', 'Farmacia'),
                  ('cajero', 'Cajero o banco')]


class Lugar(models.Model):
    """Dónde comer, dormir, cargar gasolina, etc. No es un destino: no tiene ficha, misiones ni sello.

    Lo importado de OpenStreetMap se identifica con `osm_id`, porque su licencia (ODbL) exige dar crédito.
    """
    TIPOS = TIPOS_DE_LUGAR
    SUBTIPOS = [
        ('restaurant', 'Restaurante'), ('fast_food', 'Comida rápida'), ('cafe', 'Cafetería'), ('bar', 'Bar'),
        ('pub', 'Bar'), ('hotel', 'Hotel'), ('motel', 'Motel'), ('hostel', 'Hostal'),
        ('guest_house', 'Casa de huéspedes'), ('apartment', 'Departamento'), ('fuel', 'Gasolinera'),
        ('pharmacy', 'Farmacia'), ('atm', 'Cajero'), ('bank', 'Banco'),
    ]
    nombre = models.CharField(max_length=200)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    subtipo = models.CharField(max_length=15, choices=SUBTIPOS)
    municipio = models.ForeignKey(Municipio, null=True, blank=True, on_delete=models.PROTECT, related_name='lugares')
    latitud = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(Decimal('-90')), MaxValueValidator(Decimal('90'))],
    )
    longitud = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(Decimal('-180')), MaxValueValidator(Decimal('180'))],
    )
    direccion = models.CharField(max_length=300, blank=True)
    telefono = models.CharField(max_length=60, blank=True)
    sitio_web = models.URLField(max_length=300, blank=True)
    horario = models.CharField(max_length=200, blank=True)
    es_activo = models.BooleanField(default=True)
    osm_id = models.CharField(max_length=30, null=True, blank=True, unique=True, editable=False)
    # Editado por el equipo: la siguiente importación no debe pisar la corrección.
    protegido = models.BooleanField(default=False, editable=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nombre', 'pk']
        verbose_name_plural = 'lugares'
        indexes = [models.Index(fields=['es_activo', 'tipo', 'latitud', 'longitud'], name='lugar_zona_idx')]
        constraints = [
            models.CheckConstraint(condition=models.Q(latitud__gte=-90, latitud__lte=90), name='lugar_latitud_valida'),
            models.CheckConstraint(
                condition=models.Q(longitud__gte=-180, longitud__lte=180), name='lugar_longitud_valida'
            ),
        ]

    def __str__(self):
        return f'{self.nombre} · {self.get_subtipo_display()}'

    @property
    def distancia_legible(self):
        """Solo tras buscar con cerca_de. En metros de cerca: "0.0 km" no le dice nada a nadie."""
        return f'{round(self.distancia_km * 100) * 10} m' if self.distancia_km < 1 else f'{self.distancia_km:.1f} km'

    @property
    def telefono_marcable(self):
        return ''.join(caracter for caracter in self.telefono if caracter.isdigit() or caracter == '+')
