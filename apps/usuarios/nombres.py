"""Nombre de usuario: lo que los demás ven de la cuenta en vez del correo (@ana.perez).

Reglas: de 3 a 30 caracteres, solo minúsculas, números, punto y guion bajo, sin empezar ni terminar con punto.
Se compara sin distinguir mayúsculas. Se cambia como máximo una vez cada 30 días.
"""
import re
import secrets
from datetime import timedelta

from django.utils import timezone
from django.utils.text import slugify

from .models import Usuario

# Súbela al cambiar cualquiera de las dos listas: así queda registro de qué reglas tenía cada versión.
VERSION_LISTAS = 1

# Exactos: rutas del sitio, funciones del equipo y palabras que se confundirían con el sistema.
RESERVADOS = frozenset({
    'admin', 'administrador', 'administracion', 'api', 'ayuda', 'axo', 'contacto', 'correo', 'creditos',
    'cuenta', 'destinos', 'equipo', 'escapadas', 'favoritos', 'infotrip', 'legal', 'login', 'logout', 'media',
    'moderacion', 'moderador', 'null', 'oficial', 'pasaporte', 'perfil', 'planeador', 'privacidad', 'registro',
    'root', 'seguridad', 'sistema', 'soporte', 'staff', 'static', 'terminos', 'undefined', 'usuario', 'www',
    'amigos', 'anonimo', 'eliminada', 'viajero', 'viajero.anonimo', 'webmaster', 'postmaster', 'jalisco',
})
# En cualquier parte del nombre: nadie puede hacerse pasar por el sitio o su equipo ("infotrip.oficial").
NO_CONTENER = ('infotrip', 'admin', 'moderad', 'moderacion', 'soporte', 'oficial')

# Filtro básico, no exhaustivo: raíces que se buscan dentro del nombre y palabras que se buscan completas
# (estas últimas son cortas y aparecen dentro de palabras inocentes, como "computadora").
OFENSIVAS_RAIZ = ('pendej', 'chinga', 'culero', 'cabron', 'mamaver', 'verguer', 'putit', 'hitler', 'mierda',
                  'idiota', 'estupid', 'imbecil', 'pinche', 'malparid', 'fuck', 'bitch', 'nigg', 'whore',
                  'retrasad', 'zorra', 'perra')
OFENSIVAS_PALABRA = frozenset({'puto', 'puta', 'putos', 'putas', 'verga', 'joto', 'jotos', 'culo', 'naco', 'naca',
                               'sex', 'sexo', 'porno', 'xxx', 'shit', 'ass', 'kk', 'caca', 'mamon', 'mamona',
                               'marica', 'maricon', 'nazi', 'nazis'})
LEET = str.maketrans('013457@$', 'oieastas')

FORMATO = re.compile(r'^[a-z0-9._]{3,30}$')
DIAS_ENTRE_CAMBIOS = 30


def normalizar(texto):
    return (texto or '').strip().lstrip('@').lower()


def _ofensivo(nombre):
    plano = nombre.translate(LEET)
    sin_separadores = re.sub(r'[._]', '', plano)
    if any(raiz in sin_separadores for raiz in OFENSIVAS_RAIZ):
        return True
    return any(palabra in OFENSIVAS_PALABRA for palabra in re.split(r'[._0-9]+', plano) if palabra)


def problema(nombre):
    """Por qué no se puede usar este nombre, o '' si el formato y las listas lo permiten."""
    if not 3 <= len(nombre) <= 30:
        return 'Usa de 3 a 30 caracteres.'
    if not FORMATO.match(nombre):
        return 'Usa solo letras minúsculas sin acentos, números, punto (.) y guion bajo (_).'
    if nombre[0] == '.' or nombre[-1] == '.':
        return 'No puede empezar ni terminar con punto.'
    if '..' in nombre:
        return 'No uses dos puntos seguidos.'
    if nombre.isdigit():
        return 'Incluye al menos una letra.'
    plano = re.sub(r'[._]', '', nombre)
    if nombre in RESERVADOS or plano in RESERVADOS or any(parte in plano for parte in NO_CONTENER):
        return 'Ese nombre está reservado.'
    if _ofensivo(nombre):
        return 'Elige un nombre respetuoso.'
    return ''


def ocupado(nombre, excepto=None):
    return Usuario.objects.filter(username__iexact=nombre).exclude(pk=getattr(excepto, 'pk', None)).exists()


def sugerir(usuario):
    """Una propuesta libre a partir del nombre ("Ana Pérez" → ana.perez). No se guarda: la persona decide."""
    partes = [slugify(parte).replace('-', '') for parte in (usuario.nombre, usuario.apellido)]
    base = '.'.join(parte for parte in partes if parte)[:24].strip('.') or 'viajera'
    if len(base) < 3 or problema(base):
        base = f'viaje.{base}'[:24].strip('.')
        if problema(base):
            base = 'escapada'
    candidatos = [base] + [f'{base}{numero}' for numero in range(2, 30)]
    candidatos += [f'{base}{secrets.randbelow(9000) + 1000}' for _ in range(10)]
    for candidato in candidatos:
        if not problema(candidato) and not ocupado(candidato, usuario):
            return candidato
    return ''


def puede_cambiar_desde(usuario):
    """Fecha a partir de la cual puede volver a cambiarlo, o None si ya puede."""
    if not usuario.username or not usuario.username_cambiado:
        return None
    siguiente = usuario.username_cambiado + timedelta(days=DIAS_ENTRE_CAMBIOS)
    return siguiente if siguiente > timezone.now() else None
