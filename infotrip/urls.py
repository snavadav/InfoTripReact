"""
InfoTrip — infotrip/urls.py
Enrutador principal del proyecto
"""

from django.contrib import admin
from django.views.generic import TemplateView
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerSplitView
from apps.comunidad.cola import cola_moderacion
from apps.core.views import salud
from apps.usuarios.views_frontend import login_view, registro_view
from apps.destinos.frontend import inicio, listado, detalle

urlpatterns = [
    path('health/', salud, name='salud'),
    path('favoritos/', TemplateView.as_view(template_name='comunidad/favoritos.html'), name='favoritos'),
    path('mis-viajes/', TemplateView.as_view(template_name='comunidad/viajes.html'), name='mis-viajes'),
    # Antes de admin.site.urls para que el admin no la tome como una app.
    path('admin/moderacion/', admin.site.admin_view(cola_moderacion), name='cola-moderacion'),
    path('admin/', admin.site.urls),

    # Documentación de la API. La vista "split" no usa scripts en línea, que la CSP bloquearía.
    path('api/v1/esquema/', SpectacularAPIView.as_view(), name='esquema-api'),
    path('api/v1/docs/', SpectacularSwaggerSplitView.as_view(url_name='esquema-api'), name='docs-api'),

    # API v1
    path('api/v1/', include('apps.comunidad.urls')),
    path('perfil/', TemplateView.as_view(template_name='comunidad/perfil.html'), name='perfil'),
    path('recuperar/', TemplateView.as_view(template_name='comunidad/recuperar.html'), name='recuperar'),
    path('api/v1/auth/', include('apps.usuarios.urls')),
    path('api/v1/', include('apps.destinos.urls')),

    # Frontend
    path('destinos/', listado, name='destinos-listado'),
    path('destinos/<slug:slug>/', detalle, name='destino-detalle'),
    path('',          inicio,         name='index'),
    path('login/',    login_view,    name='login'),
    path('registro/', registro_view, name='registro'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,  document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
