"""Límite global de peticiones a la API.

Si Redis cae, se deja pasar la petición: es preferible perder este límite un momento a tumbar toda
la API. Los límites propios de cada vista (login, verificación…) no usan estas clases.
"""
import logging

from redis.exceptions import RedisError
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

registro = logging.getLogger('infotrip.salud')


class _Tolerante:
    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except (RedisError, OSError) as error:
            registro.error('No se pudo aplicar el límite global de peticiones: %r', error)
            return True


class LimiteAnonimo(_Tolerante, AnonRateThrottle):
    pass


class LimiteUsuario(_Tolerante, UserRateThrottle):
    pass
