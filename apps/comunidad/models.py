from decimal import Decimal
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Viaje(models.Model):
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='viajes')
    nombre = models.CharField(max_length=120)
    destino = models.CharField(max_length=200)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    personas = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(100)])
    presupuesto = models.DecimalField(max_digits=11, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    gastos = models.JSONField(default=list)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-actualizado', '-pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(personas__gte=1, personas__lte=100), name='viaje_personas_validas'),
            models.CheckConstraint(condition=models.Q(presupuesto__gte=0), name='viaje_presupuesto_valido'),
            models.CheckConstraint(condition=models.Q(fecha_fin__gte=models.F('fecha_inicio')), name='viaje_fechas_validas'),
        ]


class Aporte(models.Model):
    TIPOS = [('resena', 'Reseña'), ('foto', 'Fotografía'), ('gasto', 'Gasto')]
    ESTADOS = [('pendiente', 'Pendiente'), ('publicado', 'Publicado'), ('oculto', 'Oculto'), ('retirado', 'Retirado por autor')]
    CONCEPTOS = [('entrada', 'Entrada por persona'), ('comida', 'Comida por persona'), ('alojamiento', 'Alojamiento por noche'), ('transporte', 'Transporte por persona')]
    destino = models.ForeignKey('destinos.Destino', on_delete=models.PROTECT, related_name='aportes')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='aportes')
    tipo = models.CharField(max_length=10, choices=TIPOS)
    texto = models.TextField(max_length=2000)
    fecha_visita = models.DateField()
    calificacion = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    imagen = models.ImageField(upload_to='comunidad/%Y/%m/', blank=True)
    monto = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal(0))])
    concepto = models.CharField(max_length=15, choices=CONCEPTOS, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default='pendiente')
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-creado', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['autor', 'destino'], condition=models.Q(tipo='resena') & ~models.Q(estado='retirado'), name='una_resena_vigente'),
            models.CheckConstraint(condition=models.Q(calificacion__isnull=True) | models.Q(calificacion__gte=1, calificacion__lte=5), name='aporte_calificacion_rango'),
            models.CheckConstraint(condition=models.Q(monto__isnull=True) | models.Q(monto__gte=0), name='aporte_monto_positivo'),
        ]
        indexes = [models.Index(fields=['destino', 'estado', 'tipo'], name='aporte_publico_idx')]

    def __str__(self):
        return f'{self.get_tipo_display()} · {self.destino} · {self.autor.nombre}'


class Reporte(models.Model):
    aporte = models.ForeignKey(Aporte, on_delete=models.PROTECT, related_name='reportes')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    motivo = models.TextField(max_length=1000)
    resuelto = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-creado']
        constraints = [models.UniqueConstraint(fields=['aporte', 'autor'], name='un_reporte_por_autor')]


class Decision(models.Model):
    aporte = models.ForeignKey(Aporte, on_delete=models.PROTECT, related_name='decisiones')
    moderador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    estado_anterior = models.CharField(max_length=12)
    estado_nuevo = models.CharField(max_length=12)
    motivo = models.TextField(max_length=1000)
    creado = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-creado']
