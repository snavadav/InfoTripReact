"""Datos siempre al día: tareas programadas, fuentes oficiales y las propuestas que una persona aprueba.

Lema: cada dato dice de dónde viene. Nada de lo que llega de una fuente se publica sin aprobación humana.
"""
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.destinos.models import Destino, Lugar, ReferenciaCosto

# Sus términos prohíben extraer datos, o publican reseñas y datos de terceros: nunca son fuente oficial.
# Con punto: el dominio exacto y sus subdominios. Sin punto: cualquier parte del nombre (google.com.mx, maps.google…).
DOMINIOS_PROHIBIDOS = (
    'google', 'goo.gl', 'g.page', 'tripadvisor', 'facebook', 'fb.com', 'fb.me', 'instagram', 'booking',
    'airbnb', 'expedia', 'hotels.com', 'trivago', 'kayak', 'despegar', 'yelp', 'foursquare', 'twitter.com',
    'x.com', 'tiktok', 'whatsapp', 'youtube', 'youtu.be', 'waze', 'bing.com',
)


def dominio_prohibido(url):
    """True si la dirección es de un sitio prohibido o de uno de sus subdominios."""
    host = (urlsplit(url).hostname or '').lower().rstrip('.')
    for prohibido in DOMINIOS_PROHIBIDOS:
        if '.' in prohibido:
            if host == prohibido or host.endswith('.' + prohibido):
                return True
        elif prohibido in host.split('.'):
            return True
    return False


def validar_url_oficial(url):
    if not url.startswith('https://'):
        raise ValidationError('La fuente debe ser una dirección https.')
    if dominio_prohibido(url):
        raise ValidationError('Ese sitio no es una fuente oficial: sus términos prohíben extraer sus datos.')


class EjecucionTarea(models.Model):
    """Cada corrida de una tarea programada: qué, cuándo, cómo terminó y cuántos datos tocó."""
    TAREAS = [('denue', 'Negocios del DENUE (INEGI)'), ('osm', 'Lugares de OpenStreetMap'),
              ('fuentes_oficiales', 'Lector de sitios oficiales')]
    RESULTADOS = [('en_curso', 'En curso'), ('exito', 'Éxito'), ('saltada', 'Saltada'), ('error', 'Error')]
    tarea = models.CharField(max_length=20, choices=TAREAS)
    inicio = models.DateTimeField(auto_now_add=True)
    fin = models.DateTimeField(null=True, blank=True)
    resultado = models.CharField(max_length=10, choices=RESULTADOS, default='en_curso')
    mensaje = models.TextField(blank=True)
    conteos = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-inicio', '-pk']
        verbose_name = 'Ejecución de tarea'
        verbose_name_plural = 'Ejecuciones de tareas'
        indexes = [models.Index(fields=['tarea', 'resultado', 'inicio'], name='ejecucion_tarea_idx')]

    def __str__(self):
        return f'{self.get_tarea_display()} · {self.get_resultado_display()}'


class FuenteOficial(models.Model):
    """Página oficial (museo, INAH, ayuntamiento, Secretaría de Turismo, SIC) que publica un precio o un horario.

    La lista es cerrada: solo el equipo la agrega en el admin. Se respeta robots.txt y se revisa con poca frecuencia.
    """
    TIPOS = [('precio', 'Precio'), ('horario', 'Horario')]
    ESTADOS = [
        ('nueva', 'Sin revisar'), ('sin_cambios', 'Sin cambios'), ('propuesta', 'Propuesta creada'),
        ('sin_dato', 'Cambió, sin dato nuevo'), ('descartada', 'Extracción descartada'),
        ('robots', 'robots.txt no lo permite'), ('error', 'Error al descargar'), ('formato', 'Formato no compatible'),
    ]
    nombre = models.CharField(max_length=200,
                              help_text='Quién publica, como se cita: "Sistema de Información Cultural".')
    url = models.URLField(max_length=500, validators=[validar_url_oficial])
    tipo_dato = models.CharField(max_length=10, choices=TIPOS)
    destino = models.ForeignKey(Destino, null=True, blank=True, on_delete=models.CASCADE,
                                related_name='fuentes_oficiales')
    lugar = models.ForeignKey(Lugar, null=True, blank=True, on_delete=models.CASCADE, related_name='fuentes_oficiales')
    referencia = models.ForeignKey(ReferenciaCosto, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='fuentes_oficiales',
                                   help_text='Precio que se actualiza al aprobar. Solo para el tipo precio.')
    frecuencia_dias = models.PositiveSmallIntegerField(default=7, validators=[MinValueValidator(7)],
                                                       help_text='Cada cuántos días se revisa. Mínimo una semana.')
    activo = models.BooleanField(default=True)
    huella = models.CharField(max_length=64, blank=True, editable=False,
                              help_text='SHA-256 del texto normalizado de la última descarga.')
    ultima_revision = models.DateTimeField(null=True, blank=True, editable=False)
    estado = models.CharField(max_length=12, choices=ESTADOS, default='nueva', editable=False)
    nota = models.CharField(max_length=300, blank=True, editable=False)

    class Meta:
        ordering = ['nombre', 'pk']
        verbose_name = 'Fuente oficial'
        verbose_name_plural = 'Fuentes oficiales'
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(destino__isnull=False, lugar__isnull=True)
                           | models.Q(destino__isnull=True, lugar__isnull=False)),
                name='fuente_oficial_destino_o_lugar'),
            models.CheckConstraint(condition=~models.Q(tipo_dato='horario', referencia__isnull=False),
                                   name='fuente_oficial_horario_sin_referencia'),
            models.UniqueConstraint(fields=['url', 'referencia'], condition=models.Q(referencia__isnull=False),
                                    name='fuente_oficial_unica_por_referencia'),
        ]

    def __str__(self):
        return f'{self.nombre} · {self.objetivo} · {self.get_tipo_dato_display()}'

    @property
    def objetivo(self):
        return self.destino or self.lugar

    def clean(self):
        if bool(self.destino_id) == bool(self.lugar_id):
            raise ValidationError('Elige un destino o un lugar, no ambos.')
        if self.tipo_dato == 'precio' and not self.referencia_id:
            raise ValidationError('Un precio oficial actualiza una referencia de costo: elige cuál.')
        if self.tipo_dato == 'horario' and self.referencia_id:
            raise ValidationError('Un horario no actualiza una referencia de costo.')
        if self.referencia_id and self.referencia.destino_id != self.destino_id:
            raise ValidationError('La referencia de costo es de otro destino.')

    def dato_actual(self):
        if self.tipo_dato == 'horario':
            return self.objetivo.horario
        return f'{self.referencia.monto:.2f}' if self.referencia else ''


class PropuestaActualizacion(models.Model):
    """Dato nuevo que la IA leyó en una fuente oficial, con la cita textual. Solo se publica si alguien aprueba."""
    ESTADOS = [('pendiente', 'Pendiente'), ('aprobada', 'Aprobada'), ('rechazada', 'Rechazada')]
    fuente = models.ForeignKey(FuenteOficial, on_delete=models.CASCADE, related_name='propuestas')
    tipo_dato = models.CharField(max_length=10, choices=FuenteOficial.TIPOS)
    dato_anterior = models.CharField(max_length=200, blank=True)
    dato_nuevo = models.CharField(max_length=200)
    cita = models.TextField(help_text='Texto exacto de la página donde aparece el dato.')
    url = models.URLField(max_length=500)
    fecha_consulta = models.DateField()
    modelo_ia = models.CharField(max_length=60, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default='pendiente')
    creado = models.DateTimeField(auto_now_add=True)
    revisado = models.DateTimeField(null=True, blank=True)
    revisado_por = models.ForeignKey('usuarios.Usuario', null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='+')

    class Meta:
        ordering = ['creado', 'pk']
        verbose_name = 'Propuesta de actualización'
        verbose_name_plural = 'Propuestas de actualización'
        indexes = [models.Index(fields=['estado', 'creado'], name='propuesta_act_estado_idx')]

    def __str__(self):
        return f'{self.fuente.objetivo} · {self.dato_anterior or "—"} → {self.dato_nuevo}'
