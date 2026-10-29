from django.urls import path
from .views import PublicarView, MisAportesView, EditarAporteView, ReportarView
from .viajes import MisViajesView, ViajeView, VincularLugarView
from .practica import ColaboracionesView, ConfirmarDatoView, FavoritosView, FavoritoView
from .avisos import NotificacionesView, NotificacionesLeidasView
urlpatterns = [
    path('notificaciones/', NotificacionesView.as_view(), name='notificaciones'),
    path('notificaciones/leidas/', NotificacionesLeidasView.as_view(), name='notificaciones-leidas'),
    path('mis-viajes/<int:pk>/lugares/', VincularLugarView.as_view(), name='vincular-lugar'),
    path('destinos/<slug:slug>/colaboraciones/', ColaboracionesView.as_view(), name='colaboraciones'),
    path('colaboraciones/<int:pk>/confirmar/', ConfirmarDatoView.as_view(), name='confirmar-dato'),
    path('favoritos/', FavoritosView.as_view(), name='favoritos-api'),
    path('favoritos/<slug:slug>/', FavoritoView.as_view(), name='favorito-api'),
    path('mis-viajes/', MisViajesView.as_view(), name='mis-viajes-api'),
    path('mis-viajes/<int:pk>/', ViajeView.as_view(), name='viaje-api'),
    path('destinos/<slug:slug>/aportes/', PublicarView.as_view(), name='aporte-crear'),
    path('mis-aportes/', MisAportesView.as_view(), name='mis-aportes'),
    path('aportes/<int:pk>/', EditarAporteView.as_view(), name='aporte-editar'),
    path('aportes/<int:pk>/reportar/', ReportarView.as_view(), name='aporte-reportar'),
]
