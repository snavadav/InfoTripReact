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
    # Horario publicado por una fuente oficial. Solo se llena al aprobar una propuesta: siempre con su cita.
    horario = models.CharField(max_length=200, blank=True)
    horario_fuente_url = models.URLField(max_length=500, blank=True, editable=False)
    horario_fecha_consulta = models.DateField(null=True, blank=True, editable=False)
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


# Subtipo de OpenStreetMap → tipo de Lugar.
TIPO_DE_SUBTIPO = {
    'restaurant': 'comer', 'fast_food': 'comer', 'cafe': 'comer', 'bar': 'comer', 'pub': 'comer',
    'hotel': 'dormir', 'motel': 'dormir', 'hostel': 'dormir', 'guest_house': 'dormir', 'apartment': 'dormir',
    'fuel': 'gasolina', 'pharmacy': 'farmacia', 'atm': 'cajero', 'bank': 'cajero',
    # Solo tiendas útiles para quien viaja. Papelerías, ópticas o talleres serían miles de puntos que estorban.
    'convenience': 'comprar', 'supermarket': 'comprar', 'variety_store': 'comprar', 'department_store': 'comprar',
    'mall': 'comprar', 'bakery': 'comprar', 'pastry': 'comprar', 'confectionery': 'comprar', 'alcohol': 'comprar',
    'wine': 'comprar', 'beverages': 'comprar', 'gift': 'comprar', 'craft': 'comprar', 'art': 'comprar',
}
TIPOS_DE_LUGAR = [('comer', 'Comer'), ('dormir', 'Dormir'), ('gasolina', 'Gasolina'), ('farmacia', 'Farmacia'),
                  ('cajero', 'Cajero o banco'), ('comprar', 'Comprar')]


class Lugar(models.Model):
    """Dónde comer, dormir, cargar gasolina, etc. No es un destino: no tiene ficha, misiones ni sello.

    Lo importado se identifica con `osm_id` (OpenStreetMap, ODbL) o `denue_id` (INEGI), porque ambos exigen dar
    crédito. Sin ninguno de los dos, el lugar lo propuso la comunidad.
    """
    TIPOS = TIPOS_DE_LUGAR
    SUBTIPOS = [
        ('restaurant', 'Restaurante'), ('fast_food', 'Comida rápida'), ('cafe', 'Cafetería'), ('bar', 'Bar'),
        ('pub', 'Bar'), ('hotel', 'Hotel'), ('motel', 'Motel'), ('hostel', 'Hostal'),
        ('guest_house', 'Casa de huéspedes'), ('apartment', 'Departamento'), ('fuel', 'Gasolinera'),
        ('pharmacy', 'Farmacia'), ('atm', 'Cajero'), ('bank', 'Banco'),
        ('convenience', 'Tienda de conveniencia'), ('supermarket', 'Supermercado'), ('variety_store', 'Tienda variada'),
        ('department_store', 'Tienda departamental'), ('mall', 'Centro comercial'), ('bakery', 'Panadería'),
        ('pastry', 'Pastelería'), ('confectionery', 'Dulcería'), ('alcohol', 'Licorería'), ('wine', 'Vinos'),
        ('beverages', 'Bebidas'), ('gift', 'Regalos y recuerdos'), ('craft', 'Artesanías y manualidades'),
        ('art', 'Arte y galería'),
    ]
    nombre = models.CharField(max_length=200)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    subtipo = models.CharField(max_length=20, choices=SUBTIPOS)
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
    # Procedencia del DENUE del INEGI; sus términos también exigen citar la fuente.
    denue_id = models.CharField(max_length=20, null=True, blank=True, unique=True, editable=False)
    # Editado por el equipo: la siguiente importación no debe pisar la corrección.
    protegido = models.BooleanField(default=False, editable=False)
    # Ya no aparece en su fuente (OSM o DENUE). No se borra ni se oculta solo: una persona decide en la cola.
    posiblemente_cerrado = models.BooleanField(default=False, editable=False)
    ausente_desde = models.DateField(null=True, blank=True, editable=False)
    # Si el horario viene de una fuente oficial aprobada, la importación de OSM no lo pisa.
    horario_fuente_url = models.URLField(max_length=500, blank=True, editable=False)
    horario_fecha_consulta = models.DateField(null=True, blank=True, editable=False)
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


class ReferenciaCosto(models.Model):
    """Precio publicado por una fuente oficial, con su cita.

    Va aparte de los gastos de viajeros: no entra en la mediana ni cuenta para el mínimo de reportes.
    Solo se registra lo que una fuente publica; nunca se estima un precio.
    """
    CONCEPTOS = [
        ('entrada', 'Entrada'),
        ('comida', 'Comida'),
        ('transporte', 'Transporte'),
        ('alojamiento', 'Alojamiento'),
    ]
    destino = models.ForeignKey(Destino, on_delete=models.CASCADE, related_name='referencias_costo')
    concepto = models.CharField(max_length=15, choices=CONCEPTOS)
    monto = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0'))],
                                help_text='En pesos mexicanos. 0 cuando la fuente indica entrada libre.')
    descripcion = models.CharField(max_length=300, help_text='A qué corresponde el precio, como lo publica la fuente.')
    fuente_nombre = models.CharField(max_length=200)
    fuente_url = models.URLField(max_length=500)
    fecha_consulta = models.DateField(help_text='Día en que se consultó la fuente.')
    fecha_fuente = models.DateField(null=True, blank=True,
                                    help_text='Última modificación o entrada en vigor que indica la fuente, si la da.')

    class Meta:
        ordering = ['destino', 'concepto', 'monto', 'pk']
        verbose_name = 'Referencia oficial de costo'
        verbose_name_plural = 'Referencias oficiales de costo'
        constraints = [
            models.CheckConstraint(condition=models.Q(monto__gte=0), name='referencia_costo_monto_no_negativo'),
            models.UniqueConstraint(fields=['destino', 'concepto', 'descripcion', 'fuente_url'],
                                    name='referencia_costo_unica'),
        ]

    def __str__(self):
        return f'{self.destino} · {self.get_concepto_display()} · ${self.monto}'
