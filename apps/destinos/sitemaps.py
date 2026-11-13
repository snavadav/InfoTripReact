from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import reverse

from apps.comunidad.selectors import costos_por_destino
from . import cache_catalogo
from .models import Destino

CABECERAS_GUARDADAS = ('Content-Type', 'X-Robots-Tag', 'Last-Modified')


def sitemap_en_cache(request, sitemaps):
    """El sitemap de Django, guardado hasta que cambia el catálogo: recorre todos los destinos y sus costos."""
    def generar():
        respuesta = sitemap(request, sitemaps=sitemaps)
        respuesta.render()
        return respuesta.status_code, respuesta.content, {
            nombre: respuesta[nombre] for nombre in CABECERAS_GUARDADAS if respuesta.has_header(nombre)}
    if request.GET:  # ?p=… de un índice paginado: poco frecuente, no se guarda.
        estado, contenido, cabeceras = generar()
    else:
        # Las direcciones son absolutas: van con el dominio y el esquema de la petición.
        estado, contenido, cabeceras = cache_catalogo.guardado(
            f'sitemap:{request.scheme}:{request.get_host()}', generar)
    respuesta = HttpResponse(contenido, status=estado)
    for nombre, valor in cabeceras.items():
        respuesta[nombre] = valor
    return respuesta


class PaginasSitemap(Sitemap):
    def items(self):
        return ['index', 'destinos-listado', 'planeador', 'costos-indice', 'misiones', 'pasaporte', 'negocios']

    def location(self, item):
        return reverse(item)


class DestinosSitemap(Sitemap):
    def items(self):
        return Destino.objects.filter(es_activo=True).order_by('pk')

    def location(self, destino):
        return reverse('destino-detalle', kwargs={'slug': destino.slug})

    def lastmod(self, destino):
        return destino.fecha_actualizacion


class CostosSitemap(Sitemap):
    """Solo páginas con cifras: las vacías llevan noindex."""
    def items(self):
        return Destino.objects.filter(es_activo=True, pk__in=costos_por_destino()).order_by('pk')

    def location(self, destino):
        return reverse('destino-costos', kwargs={'slug': destino.slug})
