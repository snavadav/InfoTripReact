from django.conf import settings
from django.db import models


class Evento(models.Model):
    """Una acción en el sitio. Sin dirección IP ni cookies; se borra a los 13 meses (purgar_eventos).

    `usuario` solo se llena en acciones hechas con sesión, para medir retención. Al eliminar una
    cuenta, sus eventos quedan sin usuario.
    """
    # Los envía el navegador sin sesión; son los únicos que acepta POST /api/v1/eventos/.
    DEL_NAVEGADOR = ['registro_iniciado', 'ficha_vista', 'dato_practico_visto', 'enlace_compartido',
                     'visita_por_enlace', 'clic_en_aviso', 'costos_vista', 'misiones_vista']
    DEL_SERVIDOR = ['registro_completado', 'login_completado', 'aporte_enviado', 'aporte_publicado',
                    'dato_enviado', 'dato_confirmado', 'reporte_enviado', 'viaje_guardado', 'favorito_guardado',
                    'bote_creado', 'bote_unido', 'gasto_real_publicado', 'visita_comprobada']

    nombre = models.CharField(max_length=40)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='+')
    destino = models.SlugField(max_length=220, blank=True)
    creado = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-creado', '-pk']
        indexes = [models.Index(fields=['nombre', 'creado'], name='evento_nombre_creado_idx')]

    def __str__(self):
        return f'{self.nombre} · {self.creado:%Y-%m-%d %H:%M}'


def registrar(nombre, usuario=None, destino=''):
    return Evento.objects.create(nombre=nombre, usuario=usuario, destino=destino)
