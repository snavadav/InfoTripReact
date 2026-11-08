from django.urls import path

from .views import PlanearRutaView

urlpatterns = [
    path('rutas/planear/', PlanearRutaView.as_view(), name='planear-ruta'),
]
