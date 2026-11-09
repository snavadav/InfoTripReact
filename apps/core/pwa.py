"""App instalable (PWA): manifiesto, service worker y página sin conexión.

El service worker vive en apps/core/sw.js y se sirve desde la raíz (/sw.js) para que su alcance sea todo el sitio.
Esta vista le antepone dos constantes: la lista de archivos que guarda al instalarse y la versión de la caché.
La versión es una huella de esos archivos y del propio sw.js: en producción los nombres llevan el hash de
ManifestStaticFilesStorage, así que cada despliegue que cambie un CSS o JS crea cachés nuevas y borra las viejas.
Qué guarda y qué no, y la política de cuadros de OpenStreetMap: docs/app-instalable.md.
"""
import hashlib
import json
from functools import cache
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.csp import CSP
from django.views.decorators.csp import csp_override
from django.views.decorators.http import require_GET

FUENTE_SW = Path(__file__).with_name('sw.js')
# Colores de static/css/style.css: --panel (la barra) y --fondo (la página) del tema claro, el predeterminado.
COLOR_TEMA = '#FFFFFF'
COLOR_FONDO = '#F6F7F8'
ICONOS = [
    {'src': 'images/app/icono-192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
    {'src': 'images/app/icono-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
    {'src': 'images/app/icono-maskable-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
]
# Lo que se guarda al instalar: todo el CSS y JS propios (unos 350 KB), los íconos y el dibujo de la portada.
# Las fotos no: pesan varios MB y se guardan solas, con tope, cuando se ven.
CARPETAS_PRECACHE = ('css/', 'js/', 'images/app/')
ARCHIVOS_PRECACHE = ('images/curvas.svg',)


def archivos_estaticos():
    """Rutas relativas de los estáticos propios que se guardan al instalar, en orden estable."""
    rutas = set(ARCHIVOS_PRECACHE)
    for finder in finders.get_finders():
        for ruta, _almacen in finder.list(ignore_patterns=['*.map']):
            ruta = ruta.replace('\\', '/')
            if ruta.startswith(CARPETAS_PRECACHE):
                rutas.add(ruta)
    return sorted(rutas)


def calcular_configuracion():
    estaticos = archivos_estaticos()
    precache = [reverse('sin-conexion'), *(static(ruta) for ruta in estaticos)]
    huella = hashlib.sha256(FUENTE_SW.read_bytes())
    for ruta, url in zip(estaticos, precache[1:]):
        huella.update(url.encode())
        # Sin ManifestStaticFilesStorage (desarrollo) la URL no cambia al editar: cuenta el contenido.
        archivo = finders.find(ruta)
        if archivo:
            huella.update(Path(archivo).read_bytes())
    return {'version': huella.hexdigest()[:12], 'precache': precache, 'static_url': settings.STATIC_URL}


@cache
def configuracion_fija():
    return calcular_configuracion()


def configuracion():
    # En desarrollo se recalcula en cada petición para ver los cambios sin reiniciar.
    return calcular_configuracion() if settings.DEBUG else configuracion_fija()


@require_GET
def manifiesto(request):
    datos = {
        'id': '/',
        'name': 'InfoTrip — Descubre Jalisco',
        'short_name': 'InfoTrip',
        'description': 'Destinos, lugares y gastos reales de Jalisco contados por otros viajeros.',
        'lang': 'es-MX',
        'dir': 'ltr',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'any',
        'theme_color': COLOR_TEMA,
        'background_color': COLOR_FONDO,
        'categories': ['travel'],
        'icons': [{**icono, 'src': static(icono['src'])} for icono in ICONOS],
    }
    respuesta = JsonResponse(datos, content_type='application/manifest+json',
                             json_dumps_params={'ensure_ascii': False})
    # Un día: cambia poco y los navegadores lo vuelven a pedir al revisar si hay versión nueva de la app.
    respuesta['Cache-Control'] = 'public, max-age=86400'
    return respuesta


# El service worker descarga los cuadros del mapa con fetch(), que la CSP regula con connect-src (no img-src).
@csp_override({
    'default-src': [CSP.NONE],
    'connect-src': [CSP.SELF, 'https://unpkg.com', 'https://tile.openstreetmap.org'],
})
@require_GET
def service_worker(request):
    datos = configuracion()
    cabecera = (
        '// Generado por apps/core/pwa.py en cada petición; el código está en apps/core/sw.js.\n'
        f'const VERSION = {json.dumps(datos["version"])};\n'
        f'const STATIC_URL = {json.dumps(datos["static_url"])};\n'
        f'const PRECACHE = {json.dumps(datos["precache"])};\n\n'
    )
    respuesta = HttpResponse(cabecera + FUENTE_SW.read_text(encoding='utf-8'),
                             content_type='text/javascript; charset=utf-8')
    # Sin caché larga: si el navegador se quedara con un sw.js viejo, no vería los despliegues nuevos.
    respuesta['Cache-Control'] = 'no-cache, max-age=0'
    return respuesta


@require_GET
def sin_conexion(request):
    """La muestra el service worker cuando no hay red y la página pedida no está guardada."""
    return render(request, 'sin_conexion.html', {
        'seo': {'titulo': 'Sin conexión — InfoTrip', 'descripcion': 'Páginas de InfoTrip guardadas en este equipo.'},
    })
