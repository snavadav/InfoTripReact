from django.conf import settings
from django.test import SimpleTestCase

from infotrip.settings.base import configurar_cache


class CacheTests(SimpleTestCase):
    def test_redis_si_hay_url(self):
        cache = configurar_cache('redis://redis:6379/1')['default']
        self.assertEqual(cache['BACKEND'], 'django.core.cache.backends.redis.RedisCache')
        self.assertEqual(cache['LOCATION'], 'redis://redis:6379/1')

    def test_locmem_como_respaldo(self):
        cache = configurar_cache('')['default']
        self.assertEqual(cache['BACKEND'], 'django.core.cache.backends.locmem.LocMemCache')

    def test_configuracion_activa_coincide_con_redis_url(self):
        self.assertEqual(settings.CACHES, configurar_cache(settings.REDIS_URL))
