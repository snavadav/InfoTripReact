from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Destino


class PaginasSitemap(Sitemap):
    def items(self):
        return ['index', 'destinos-listado']

    def location(self, item):
        return reverse(item)


class DestinosSitemap(Sitemap):
    def items(self):
        return Destino.objects.filter(es_activo=True).order_by('pk')

    def location(self, destino):
        return reverse('destino-detalle', kwargs={'slug': destino.slug})

    def lastmod(self, destino):
        return destino.fecha_actualizacion
