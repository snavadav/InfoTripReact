"""
InfoTrip — infotrip/urls.py
Enrutador principal del proyecto
"""

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.shortcuts import render
from django.views.generic import TemplateView
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerSplitView
from apps.comunidad.bote import unirse_al_bote
from apps.comunidad.cola import cola_moderacion
from apps.comunidad.viajes import viaje_publico
from apps.core.views import robots, salud
from apps.destinos.sitemaps import CostosSitemap, DestinosSitemap, PaginasSitemap
from apps.usuarios.views_frontend import baja_avisos, login_view, registro_view
from apps.destinos.frontend import costos_destino, costos_indice, creditos, inicio, listado, detalle, misiones
from apps.metricas.views import EventosView, panel as panel_metricas


def vista_legal(plantilla):
    # La plantilla lee el contacto en cada petición, para que `override_settings` y el entorno apliquen.
    def vista(request):
        return render(request, plantilla, {'contacto': settings.CONTACTO_PRIVACIDAD})
    return vista


urlpatterns = [
    path('health/', salud, name='salud'),
    path('robots.txt', robots, name='robots'),
    path('sitemap.xml', sitemap,
         {'sitemaps': {'paginas': PaginasSitemap, 'destinos': DestinosSitemap, 'costos': CostosSitemap}},
         name='django.contrib.sitemaps.views.sitemap'),
    path('favoritos/', TemplateView.as_view(template_name='comunidad/favoritos.html'), name='favoritos'),
    path('mis-viajes/', TemplateView.as_view(template_name='comunidad/viajes.html'), name='mis-viajes'),
    path('mis-viajes/<int:pk>/bote/', TemplateView.as_view(template_name='comunidad/bote.html'), name='bote-pagina'),
    path('botes/<uuid:enlace>/', unirse_al_bote, name='bote-invitacion'),
    # Antes de admin.site.urls para que el admin no la tome como una app.
    path('admin/moderacion/', admin.site.admin_view(cola_moderacion), name='cola-moderacion'),
    path('admin/metricas/', admin.site.admin_view(panel_metricas), name='panel-metricas'),
    path('admin/', admin.site.urls),

    # Documentación de la API. La vista "split" no usa scripts en línea, que la CSP bloquearía.
    path('api/v1/esquema/', SpectacularAPIView.as_view(), name='esquema-api'),
    path('api/v1/docs/', SpectacularSwaggerSplitView.as_view(url_name='esquema-api'), name='docs-api'),

    # API v1
    path('api/v1/eventos/', EventosView.as_view(), name='eventos'),
    path('api/v1/', include('apps.comunidad.urls')),
    path('perfil/', TemplateView.as_view(template_name='comunidad/perfil.html'), name='perfil'),
    path('recuperar/', TemplateView.as_view(template_name='comunidad/recuperar.html'), name='recuperar'),
    path('privacidad/', vista_legal('legal/privacidad.html'), name='privacidad'),
    path('terminos/', vista_legal('legal/terminos.html'), name='terminos'),
    path('creditos/', creditos, name='creditos'),
    path('escapadas/<uuid:enlace>/', viaje_publico, name='viaje-publico'),
    path('baja-avisos/', baja_avisos, name='baja-avisos'),
    path('api/v1/auth/', include('apps.usuarios.urls')),
    path('api/v1/', include('apps.destinos.urls')),

    # Frontend
    path('destinos/', listado, name='destinos-listado'),
    path('destinos/<slug:slug>/', detalle, name='destino-detalle'),
    path('destinos/<slug:slug>/costos/', costos_destino, name='destino-costos'),
    path('costos/', costos_indice, name='costos-indice'),
    path('misiones/', misiones, name='misiones'),
    path('',          inicio,         name='index'),
    path('login/',    login_view,    name='login'),
    path('registro/', registro_view, name='registro'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,  document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
