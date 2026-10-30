from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.comunidad.selectors import costos_por_destino
from .models import Destino


class PaginasSitemap(Sitemap):
    def items(self):
        return ['index', 'destinos-listado', 'costos-indice', 'misiones']

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
