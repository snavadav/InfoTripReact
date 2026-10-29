"""Moderación de contenido comunitario (aportes y colaboraciones) con una sola regla."""
from django.urls import reverse
from .models import Notificacion


def moderar(objeto, moderador, estado, motivo, registrar_sin_cambio=False):
    """Cambia el estado de un objeto Moderable, deja constancia en su historial y avisa al autor.

    El llamador bloquea la fila (select_for_update) dentro de una transacción. Un estado en
    ESTADOS_SIN_MODERACION no se cambia, y si el estado no cambia no se registra nada salvo con
    `registrar_sin_cambio` (por ejemplo, al desestimar un reporte). Devuelve True si cambió el estado.
    """
    anterior = objeto.estado
    cambia = anterior != estado
    if cambia and anterior in objeto.ESTADOS_SIN_MODERACION:
        return False
    if not cambia and not registrar_sin_cambio:
        return False
    if cambia:
        objeto.estado = estado
        objeto.save(update_fields=objeto.CAMPOS_AL_MODERAR)
    objeto.registrar_moderacion(moderador=moderador, estado_anterior=anterior, estado_nuevo=estado, motivo=motivo)
    if cambia:
        avisar_al_autor(objeto, anterior, estado)
    return cambia


def avisar_al_autor(objeto, anterior, estado):
    # El motivo no se incluye: puede citar el texto de un reporte de otra persona.
    texto = objeto.aviso_para_autor(anterior, estado)
    if texto:
        enlace = reverse('destino-detalle', kwargs={'slug': objeto.destino.slug}) if estado == 'publicado' else ''
        Notificacion.objects.create(usuario=objeto.autor, texto=texto, enlace=enlace)
