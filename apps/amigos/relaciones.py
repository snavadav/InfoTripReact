"""Consultas sobre la relación entre dos cuentas. Las vistas solo deciden qué mostrar con esto."""
from django.db.models import Q

from apps.usuarios.models import Usuario
from .models import Amistad, Bloqueo


def amistad_entre(uno, otro):
    if not uno or not otro or uno.pk == otro.pk:
        return None
    return Amistad.objects.filter(Q(de=uno, para=otro) | Q(de=otro, para=uno)).first()


def son_amigos(uno, otro):
    amistad = amistad_entre(uno, otro)
    return bool(amistad and amistad.estado == 'aceptada')


def bloqueado(uno, otro):
    """Hay un bloqueo en cualquier dirección: no se ven, no se buscan, no se envían solicitudes."""
    if not uno or not otro:
        return False
    return Bloqueo.objects.filter(Q(de=uno, para=otro) | Q(de=otro, para=uno)).exists()


def amigos_de(usuario):
    """Cuentas activas con amistad aceptada."""
    aceptadas = Amistad.objects.filter(Q(de=usuario) | Q(para=usuario), estado='aceptada')
    ids = {pk for par in aceptadas.values_list('de_id', 'para_id') for pk in par} - {usuario.pk}
    return Usuario.objects.filter(pk__in=ids, es_activo=True).order_by('username', 'nombre', 'pk')


def relacion(visitante, usuario):
    """Qué es `usuario` para `visitante`: yo, amigos, enviada, recibida, bloqueado (lo bloqueaste) o ninguna."""
    if not visitante or not visitante.is_authenticated:
        return 'anonimo'
    if visitante.pk == usuario.pk:
        return 'yo'
    if Bloqueo.objects.filter(de=visitante, para=usuario).exists():
        return 'bloqueado'
    amistad = amistad_entre(visitante, usuario)
    if not amistad or amistad.estado == 'rechazada':
        return 'ninguna'
    if amistad.estado == 'aceptada':
        return 'amigos'
    return 'enviada' if amistad.de_id == visitante.pk else 'recibida'


def puede_ver_detalle(visitante, usuario, rel=None):
    """Matriz de visibilidad: el nombre siempre se ve; el pasaporte, los lugares y los amigos, según esto."""
    rel = rel or relacion(visitante, usuario)
    if rel == 'yo':
        return True
    if usuario.visibilidad == 'publico':
        return True
    if usuario.visibilidad == 'amigos':
        return rel == 'amigos'
    return False
