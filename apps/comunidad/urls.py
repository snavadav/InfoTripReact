from django.urls import path
from .views import PublicarView, MisAportesView, EditarAporteView, ReportarView
from .viajes import MisViajesView, ViajeView
urlpatterns = [
    path('mis-viajes/', MisViajesView.as_view(), name='mis-viajes-api'),
    path('mis-viajes/<int:pk>/', ViajeView.as_view(), name='viaje-api'),
    path('destinos/<slug:slug>/aportes/', PublicarView.as_view(), name='aporte-crear'),
    path('mis-aportes/', MisAportesView.as_view(), name='mis-aportes'),
    path('aportes/<int:pk>/', EditarAporteView.as_view(), name='aporte-editar'),
    path('aportes/<int:pk>/reportar/', ReportarView.as_view(), name='aporte-reportar'),
]
