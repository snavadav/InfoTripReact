"""Avisos al usuario: qué tipos hay, cómo se crean respetando sus preferencias y cuáles puede ver.

Todo aviso nuevo pasa por avisar(). Los recordatorios que dependen de la fecha (escapada próxima, agenda del día,
pagos sin confirmar, cuentas por saldar) los genera avisos_programados.py desde el comando `enviar_avisos`.
"""
from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.amigos.models import Bloqueo
from .models import Notificacion

# Orden en que aparecen en Mi perfil. `correo`: si el tipo puede llegar por correo. `accion`: el texto del
# botón que lleva directo a resolverlo.
TIPOS = {
    'viaje_pronto': {
        'nombre': 'Tu escapada se acerca', 'detalle': 'Hasta 3 días antes, con lo que te falta preparar.',
        'accion': 'Ver escapada', 'asunto': 'Tu escapada se acerca', 'correo': True,
    },
    'viaje_hoy': {
        'nombre': 'La agenda de cada día', 'detalle': 'Por la mañana, durante tu escapada: qué sigue y a qué hora.',
        'accion': 'Ver la agenda', 'asunto': 'Tu agenda de hoy', 'correo': True,
    },
    'pago': {
        'nombre': 'Pagos por confirmar', 'detalle': 'Cuando alguien del bote registra que te pagó.',
        'accion': 'Confirmar pago', 'asunto': 'Confirma un pago del bote', 'correo': True,
    },
    'cuentas': {
        'nombre': 'Cuentas por saldar', 'detalle': 'Al terminar la escapada, si te queda algo por pagar en el bote.',
        'accion': 'Saldar cuentas', 'asunto': 'Te queda algo por saldar en el bote', 'correo': True,
    },
    'bote': {
        'nombre': 'Novedades del bote', 'detalle': 'Si te agregan a un bote, alguien se une o confirma tu pago.',
        'accion': 'Abrir el bote', 'asunto': 'Novedades en tu bote', 'correo': True,
    },
    'amistad': {
        'nombre': 'Amigos', 'detalle': 'Solicitudes de amistad que recibes o que aceptan.',
        'accion': 'Ver solicitudes', 'asunto': 'Novedades de tus amigos en InfoTrip', 'correo': True,
    },
    'aportes': {
        'nombre': 'Revisión de tus aportes', 'detalle': 'Cuando publicamos u ocultamos tu reseña, foto o dato.',
        'accion': 'Ver', 'asunto': 'Novedades de tus aportes', 'correo': True,
    },
    'lugares': {
        'nombre': 'Tus lugares guardados', 'detalle': 'Novedades de un lugar guardado, como mucho una por semana.',
        'accion': 'Ver lugar', 'asunto': 'Novedades de tus lugares guardados', 'correo': True,
    },
    'viaje_resena': {
        'nombre': '¿Cómo te fue?', 'detalle': 'Después de una escapada, para contar tu experiencia.',
        'accion': 'Contar cómo me fue', 'asunto': '¿Cómo te fue en tu escapada?', 'correo': True,
    },
    'pasaporte': {
        'nombre': 'Sellos del pasaporte', 'detalle': 'Cuando ganas un sello. Solo dentro de InfoTrip.',
        'accion': 'Ver pasaporte', 'asunto': 'Ganaste un sello', 'correo': False,
    },
}
# Para elegirlos en la API (y un solo nombre en el esquema: ENUM_NAME_OVERRIDES).
OPCIONES_TIPO = [(tipo, datos['nombre']) for tipo, datos in TIPOS.items()]
GENERAL = {'accion': 'Abrir', 'asunto': 'Novedades en InfoTrip', 'correo': True}
LARGO_TEXTO = Notificacion._meta.get_field('texto').max_length


def datos_tipo(tipo):
    return TIPOS.get(tipo, GENERAL)


def quiere(usuario, tipo):
    return tipo not in (usuario.avisos_silenciados or [])


def quiere_correo(usuario, tipo):
    return bool(usuario.email and usuario.avisos_correo and datos_tipo(tipo)['correo']
                and quiere(usuario, tipo) and tipo not in (usuario.avisos_sin_correo or []))


def hay_bloqueo(uno, otro):
    return bool(uno and otro and Bloqueo.objects.filter(Q(de=uno, para=otro) | Q(de=otro, para=uno)).exists())


def nuevo(usuario, tipo, texto, enlace='', *, actor=None, clave=''):
    """El aviso sin guardar, o None si la persona apagó ese tipo, ya no está activa o hay un bloqueo con `actor`."""
    if tipo not in TIPOS:
        raise ValueError(f'Tipo de aviso desconocido: {tipo}')
    if not usuario or not usuario.es_activo or not quiere(usuario, tipo):
        return None
    if actor and (actor.pk == usuario.pk or not actor.es_activo or hay_bloqueo(actor, usuario)):
        return None
    return Notificacion(usuario=usuario, tipo=tipo, texto=texto[:LARGO_TEXTO], enlace=enlace[:300], actor=actor,
                        clave=clave[:80], correo_pendiente=quiere_correo(usuario, tipo))


def avisar(usuario, tipo, texto, enlace='', *, actor=None, clave=''):
    """Crea el aviso y lo deja listo para el correo si la persona lo quiere así. Con `clave`, no lo repite."""
    aviso = nuevo(usuario, tipo, texto, enlace, actor=actor, clave=clave)
    if aviso is None:
        return None
    if not clave:
        aviso.save()
        return aviso
    if Notificacion.objects.filter(usuario=usuario, clave=aviso.clave).exists():
        return None
    try:
        with transaction.atomic():
            aviso.save()
    except IntegrityError:
        # Otra ejecución del comando lo creó al mismo tiempo.
        return None
    return aviso


def ocultos_para(usuario):
    """Cuentas cuyos avisos no se muestran a `usuario`: hay un bloqueo entre ambas, en cualquier dirección."""
    return {pk for par in Bloqueo.objects.filter(Q(de=usuario) | Q(para=usuario)).values_list('de', 'para')
            for pk in par} - {usuario.pk}


def visibles(usuario):
    """Los avisos de `usuario`, sin los de alguien con quien hay un bloqueo o que se dio de baja."""
    return (Notificacion.objects.filter(usuario=usuario).exclude(actor__in=ocultos_para(usuario))
            .exclude(actor__es_activo=False))


def con_aviso(enlace, pk, ref=False):
    """El enlace con ?aviso=<pk>, que marca el aviso como leído al abrirlo (avisos-nav.js). Respeta el #ancla."""
    ruta, _, ancla = enlace.partition('#')
    extra = f'ref=aviso&aviso={pk}' if ref else f'aviso={pk}'
    return f'{ruta}{"&" if "?" in ruta else "?"}{extra}' + (f'#{ancla}' if ancla else '')
