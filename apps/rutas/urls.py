from django.urls import path

from .paradas import ParadasView
from .views import PlanearRutaView

urlpatterns = [
    path('rutas/planear/', PlanearRutaView.as_view(), name='planear-ruta'),
    path('rutas/paradas/', ParadasView.as_view(), name='paradas-ruta'),
]
