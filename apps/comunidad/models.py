import uuid
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
    actividades = models.JSONField(default=list)
    pendientes = models.JSONField(default=list)
    notas = models.TextField(max_length=3000, blank=True)
    lugares = models.ManyToManyField('destinos.Destino', blank=True, related_name='viajes_guardados')
    # Cuándo se invitó al viajero a contar cómo le fue; una sola vez por escapada.
    recordatorio_enviado = models.DateTimeField(null=True, blank=True)
    # Enlace de solo lectura para quien organiza con otras personas; vacío si no se comparte.
    enlace_publico = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    # Invitación al bote; distinta del enlace público porque esta da acceso a los gastos del grupo.
    enlace_bote = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-actualizado', '-pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(personas__gte=1, personas__lte=100), name='viaje_personas_validas'
            ),
            models.CheckConstraint(condition=models.Q(presupuesto__gte=0), name='viaje_presupuesto_valido'),
            models.CheckConstraint(
                condition=models.Q(fecha_fin__gte=models.F('fecha_inicio')), name='viaje_fechas_validas'
            ),
        ]


class Moderable(models.Model):
    """Contenido de la comunidad que un moderador publica u oculta, con historial de cada cambio.

    Las subclases definen `estado` y cómo guardan su historial; la moderación la hace moderacion.moderar().
    """
    # Estados que la moderación no puede cambiar (por ejemplo, un aporte que retiró su autor).
    ESTADOS_SIN_MODERACION = ()
    CAMPOS_AL_MODERAR = ['estado']
    # Cómo se nombra cada tipo en el aviso al autor ("Publicamos tu reseña sobre…").
    NOMBRES_EN_AVISO = {}

    class Meta:
        abstract = True

    def registrar_moderacion(self, **campos):
        raise NotImplementedError

    def aviso_para_autor(self, anterior, estado):
        """Texto del aviso al autor por un cambio de estado, o None si ese cambio no se avisa."""
        tipo = self.NOMBRES_EN_AVISO.get(self.tipo, 'aporte')
        if estado == 'publicado':
            return f'Publicamos tu {tipo} sobre {self.destino.nombre}.'
        if estado == 'oculto':
            momento = 'tras una nueva revisión' if anterior == 'publicado' else 'tras la revisión'
            return f'Ocultamos tu {tipo} sobre {self.destino.nombre} {momento}.'
        return None


class Notificacion(models.Model):
    """Aviso interno para un usuario; se muestra en Mi perfil y, si corresponde, se envía por correo.

    El correo no se envía al moderar: lo envía después el comando `enviar_avisos`.
    """
    MAX_INTENTOS_CORREO = 3
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notificaciones')
    texto = models.CharField(max_length=300)
    enlace = models.CharField(max_length=300, blank=True)
    leida = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)
    correo_pendiente = models.BooleanField(default=False)
    correo_intentos = models.PositiveSmallIntegerField(default=0)
    correo_enviado = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-creado', '-pk']
        indexes = [
            models.Index(fields=['usuario', 'leida'], name='notificacion_usuario_idx'),
            models.Index(fields=['correo_pendiente'], name='notificacion_correo_idx',
                         condition=models.Q(correo_pendiente=True)),
        ]


class RegistroModeracion(models.Model):
    """Historial de solo lectura: quién cambió el estado, de cuál a cuál y por qué."""
    moderador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    estado_anterior = models.CharField(max_length=12)
    estado_nuevo = models.CharField(max_length=12)
    motivo = models.TextField(max_length=1000)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-creado', '-pk']


class Aporte(Moderable):
    TIPOS = [('resena', 'Reseña'), ('foto', 'Fotografía'), ('gasto', 'Gasto')]
    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('publicado', 'Publicado'),
        ('oculto', 'Oculto'),
        ('retirado', 'Retirado por autor'),
    ]
    CONCEPTOS = [
        ('entrada', 'Entrada por persona'),
        ('comida', 'Comida por persona'),
        ('alojamiento', 'Alojamiento por noche'),
        ('transporte', 'Transporte por persona'),
    ]
    destino = models.ForeignKey('destinos.Destino', on_delete=models.PROTECT, related_name='aportes')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='aportes')
    tipo = models.CharField(max_length=10, choices=TIPOS)
    texto = models.TextField(max_length=2000)
    fecha_visita = models.DateField()
    calificacion = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    imagen = models.ImageField(upload_to='comunidad/%Y/%m/', blank=True)
    miniatura = models.ImageField(upload_to='comunidad/miniaturas/%Y/%m/', blank=True, editable=False)
    monto = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal(0))]
    )
    concepto = models.CharField(max_length=15, choices=CONCEPTOS, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default='pendiente')
    # Se publica sin el nombre del autor, por ejemplo los gastos de un bote. La moderación sí lo ve.
    anonimo = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-creado', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['autor', 'destino'],
                condition=models.Q(tipo='resena') & ~models.Q(estado='retirado'),
                name='una_resena_vigente',
            ),
            models.CheckConstraint(
                condition=models.Q(calificacion__isnull=True) | models.Q(calificacion__gte=1, calificacion__lte=5),
                name='aporte_calificacion_rango',
            ),
            models.CheckConstraint(
                condition=models.Q(monto__isnull=True) | models.Q(monto__gte=0), name='aporte_monto_positivo'
            ),
        ]
        indexes = [models.Index(fields=['destino', 'estado', 'tipo'], name='aporte_publico_idx')]

    ESTADOS_SIN_MODERACION = ('retirado',)
    CAMPOS_AL_MODERAR = ['estado', 'actualizado']
    NOMBRES_EN_AVISO = {'resena': 'reseña', 'foto': 'fotografía', 'gasto': 'registro de gasto'}

    def __str__(self):
        return f'{self.get_tipo_display()} · {self.destino} · {self.autor.nombre}'

    def registrar_moderacion(self, **campos):
        return self.decisiones.create(**campos)

    @property
    def nombre_publico(self):
        return 'Viajero anónimo' if self.anonimo else self.autor.nombre


class ReporteBase(models.Model):
    """Alguien avisa de un problema con contenido publicado. Lo resuelve el personal desde el admin."""
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    motivo = models.TextField(max_length=1000)
    resuelto = models.BooleanField(default=False)
    resuelto_en = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class Reporte(ReporteBase):
    aporte = models.ForeignKey(Aporte, on_delete=models.PROTECT, related_name='reportes')

    class Meta:
        ordering = ['-creado']
        constraints = [models.UniqueConstraint(fields=['aporte', 'autor'], name='un_reporte_por_autor')]


class Decision(RegistroModeracion):
    aporte = models.ForeignKey(Aporte, on_delete=models.PROTECT, related_name='decisiones')


class Favorito(models.Model):
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favoritos')
    destino = models.ForeignKey('destinos.Destino', on_delete=models.CASCADE, related_name='favoritos')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado', '-pk']
        constraints = [models.UniqueConstraint(fields=['autor', 'destino'], name='favorito_unico')]


class Colaboracion(Moderable):
    CAMPOS = [
        ('horarios', 'Horarios'),
        ('acceso', 'Cómo acceder'),
        ('estacionamiento', 'Estacionamiento'),
        ('pago', 'Formas de pago'),
        ('restricciones', 'Restricciones'),
        ('accesibilidad', 'Accesibilidad'),
        ('contacto', 'Contacto'),
        ('precios', 'Precios y cargos adicionales'),
    ]
    TIPOS = [('correccion', 'Información práctica / corrección'), ('pregunta', 'Pregunta'), ('respuesta', 'Respuesta')]
    ESTADOS = [('pendiente', 'Pendiente'), ('publicado', 'Publicado'), ('oculto', 'Oculto')]
    destino = models.ForeignKey('destinos.Destino', on_delete=models.PROTECT, related_name='colaboraciones')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=12, choices=TIPOS)
    campo = models.CharField(max_length=20, choices=CAMPOS, blank=True)
    texto = models.TextField(max_length=1500)
    fuente = models.CharField(max_length=300, blank=True)
    fecha_dato = models.DateField(null=True, blank=True)
    pregunta = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='respuestas')
    estado = models.CharField(max_length=12, choices=ESTADOS, default='pendiente')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado', '-pk']
        indexes = [models.Index(fields=['destino', 'tipo', 'estado'], name='colaboracion_publica_idx')]

    def __str__(self):
        return f'{self.get_tipo_display()} · {self.destino} · {self.pk}'

    NOMBRES_EN_AVISO = {'correccion': 'dato práctico', 'pregunta': 'pregunta', 'respuesta': 'respuesta'}

    def registrar_moderacion(self, **campos):
        return self.revisiones.create(**campos)


class ReporteColaboracion(ReporteBase):
    colaboracion = models.ForeignKey(Colaboracion, on_delete=models.PROTECT, related_name='reportes')

    class Meta:
        ordering = ['-creado']
        constraints = [
            models.UniqueConstraint(fields=['colaboracion', 'autor'], name='un_reporte_de_colaboracion_por_autor'),
        ]


class RevisionColaboracion(RegistroModeracion):
    colaboracion = models.ForeignKey(Colaboracion, on_delete=models.PROTECT, related_name='revisiones')


class Confirmacion(models.Model):
    """Una persona confirma que un dato práctico publicado sigue vigente ("¿Sigue vigente?").

    No pasa por moderación porque no añade texto: solo renueva la fecha de vigencia del dato.
    Cada persona confirma una vez por dato; volver a confirmar actualiza la fecha.
    """
    dato = models.ForeignKey(Colaboracion, on_delete=models.CASCADE, related_name='confirmaciones')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='confirmaciones')
    fecha = models.DateField()
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-pk']
        constraints = [models.UniqueConstraint(fields=['dato', 'autor'], name='una_confirmacion_por_persona')]


class Participante(models.Model):
    """Persona que se unió al bote de una escapada. Sin usuario: su cuenta se eliminó, pero sus cuentas siguen."""
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name='participantes')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='botes')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pk']
        constraints = [models.UniqueConstraint(fields=['viaje', 'usuario'], name='un_participante_por_bote')]

    @property
    def nombre(self):
        return self.usuario.nombre if self.usuario else 'Cuenta eliminada'


class GastoReal(models.Model):
    """Lo que alguien del grupo ya pagó, repartido en partes iguales entre `entre`."""
    CONCEPTOS = [*Aporte.CONCEPTOS, ('otros', 'Otros')]
    viaje = models.ForeignKey(Viaje, on_delete=models.CASCADE, related_name='gastos_reales')
    # RESTRICT y no PROTECT: permite borrar el viaje completo, pero no a una persona con gastos.
    pagado_por = models.ForeignKey(Participante, on_delete=models.RESTRICT, related_name='pagados')
    entre = models.ManyToManyField(Participante, related_name='compartidos')
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    descripcion = models.CharField(max_length=120)
    concepto = models.CharField(max_length=15, choices=CONCEPTOS)
    monto = models.DecimalField(max_digits=9, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    fecha = models.DateField()
    noches = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(365)])
    destino = models.ForeignKey('destinos.Destino', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    # El aporte que se envió a revisión, para no publicarlo dos veces.
    aporte = models.OneToOneField(Aporte, null=True, blank=True, on_delete=models.SET_NULL, related_name='gasto_real',
                                  editable=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-pk']
        constraints = [models.CheckConstraint(condition=models.Q(monto__gt=0), name='gasto_real_monto_positivo')]


class VisitaComprobada(models.Model):
    """La persona estaba cerca del destino en esta fecha. No guarda coordenadas, a propósito."""
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='visitas_comprobadas')
    destino = models.ForeignKey('destinos.Destino', on_delete=models.CASCADE, related_name='visitas_comprobadas')
    fecha = models.DateField()
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-pk']
        constraints = [models.UniqueConstraint(fields=['autor', 'destino'], name='una_visita_por_destino')]


class PasaporteCompartido(models.Model):
    """Existe solo mientras la persona comparte su pasaporte; borrarlo invalida el enlace."""
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pasaporte')
    enlace = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    creado = models.DateTimeField(auto_now_add=True)
