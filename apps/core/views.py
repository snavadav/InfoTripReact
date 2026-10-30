"""Endpoint de salud para Docker, balanceadores y monitoreo: GET /health/."""
import logging
from django.core.cache import cache
from django.db import connection
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

registro = logging.getLogger('infotrip.salud')


@never_cache
@require_GET
def salud(request):
    """200 si la base de datos y la caché responden; 503 con el componente que falla si no."""
    componentes = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        componentes['base_de_datos'] = 'ok'
    except Exception as error:  # Cualquier fallo de conexión cuenta como no disponible.
        registro.error('Base de datos no disponible: %r', error)
        componentes['base_de_datos'] = 'error'
    try:
        cache.set('salud', 'ok', 10)
        componentes['cache'] = 'ok' if cache.get('salud') == 'ok' else 'error'
    except Exception as error:
        registro.error('Caché no disponible: %r', error)
        componentes['cache'] = 'error'
    sano = all(valor == 'ok' for valor in componentes.values())
    return JsonResponse({'estado': 'ok' if sano else 'error', **componentes}, status=200 if sano else 503)


@require_GET
def robots(request):
    privadas = ['/admin/', '/api/', '/perfil/', '/favoritos/', '/mis-viajes/', '/login/', '/registro/', '/recuperar/']
    lineas = ['User-agent: *', *[f'Disallow: {ruta}' for ruta in privadas],
              f'Sitemap: {settings.PUBLIC_BASE_URL}/sitemap.xml']
    return HttpResponse('\n'.join(lineas) + '\n', content_type='text/plain')
