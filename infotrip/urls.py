"""
InfoTrip — infotrip/urls.py
Enrutador principal del proyecto
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.usuarios.views_frontend import index, login_view, registro_view

urlpatterns = [
    path('admin/', admin.site.urls),

    # API v1
    path('api/v1/auth/', include('apps.usuarios.urls')),

    # Frontend
    path('',          index,         name='index'),
    path('login/',    login_view,    name='login'),
    path('registro/', registro_view, name='registro'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,  document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)