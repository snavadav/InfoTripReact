"""Monitoreo de errores con Sentry (o GlitchTip) sin enviar datos personales.

`send_default_pii=False` ya quita IP, cookies, cabeceras sensibles, usuario y parámetros de SQL. Esto quita además:
- las variables locales de cada línea del error (pueden tener correos, coordenadas o el texto de una reseña);
- la cadena de consulta de la URL (`?t=` de la baja de avisos identifica a una cuenta) y el cuerpo de la petición;
- cualquier correo que aparezca en el texto del error, en los registros o en las migas de pan
  (por ejemplo, PostgreSQL pone el valor repetido en el mensaje de un IntegrityError).
"""
import re

import sentry_sdk

CORREO = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
OCULTO = '[oculto]'


def _tapar_correos(valor):
    if isinstance(valor, str):
        return CORREO.sub(OCULTO, valor)
    if isinstance(valor, dict):
        return {clave: _tapar_correos(dato) for clave, dato in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_tapar_correos(dato) for dato in valor]
    return valor


def limpiar_evento(evento, _pista=None):
    """`before_send` y `before_send_transaction`: devuelve el evento sin datos personales."""
    peticion = evento.get('request')
    if isinstance(peticion, dict):
        for clave in ('query_string', 'data', 'cookies', 'env'):
            peticion.pop(clave, None)
        if isinstance(peticion.get('url'), str):
            peticion['url'] = peticion['url'].split('?', 1)[0]
    evento.pop('user', None)
    return _tapar_correos(evento)


def opciones(dsn):
    return {
        'dsn': dsn,
        'send_default_pii': False,
        'include_local_variables': False,
        # Sin el cuerpo de las peticiones: una ubicación enviada para comprobar una visita nunca debe guardarse.
        'max_request_body_size': 'never',
        'traces_sample_rate': 0,
        'before_send': limpiar_evento,
        'before_send_transaction': limpiar_evento,
    }


def iniciar(dsn, **extra):
    """Inicializa Sentry solo si hay DSN. `extra` permite a las pruebas cambiar el transporte."""
    if dsn:
        sentry_sdk.init(**opciones(dsn), **extra)
