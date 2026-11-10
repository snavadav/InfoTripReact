from django.urls import path

from .views import (
    AceptarView, AmigosView, AmigoView, BloqueosView, BloqueoView, BuscarView, PerfilPublicoView, RechazarView,
    SolicitudesView, SolicitudView,
)

urlpatterns = [
    path('amigos/', AmigosView.as_view(), name='amigos-api'),
    path('amigos/buscar/', BuscarView.as_view(), name='amigos-buscar'),
    path('amigos/solicitudes/', SolicitudesView.as_view(), name='amigos-solicitudes'),
    path('amigos/solicitudes/<int:pk>/', SolicitudView.as_view(), name='amigos-solicitud'),
    path('amigos/solicitudes/<int:pk>/aceptar/', AceptarView.as_view(), name='amigos-aceptar'),
    path('amigos/solicitudes/<int:pk>/rechazar/', RechazarView.as_view(), name='amigos-rechazar'),
    path('amigos/bloqueos/', BloqueosView.as_view(), name='amigos-bloqueos'),
    path('amigos/bloqueos/<str:username>/', BloqueoView.as_view(), name='amigos-bloqueo'),
    path('amigos/<str:username>/', AmigoView.as_view(), name='amigos-amigo'),
    path('personas/<str:username>/', PerfilPublicoView.as_view(), name='persona'),
]
