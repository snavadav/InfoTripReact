from django.urls import path

from .compartir import RutaCompartidaView, RutasCompartidasView
from .paradas import ParadasView
from .views import AlternativasView, GuardarEscapadaView, PlanearRutaView

urlpatterns = [
    path('rutas/planear/', PlanearRutaView.as_view(), name='planear-ruta'),
    path('rutas/alternativas/', AlternativasView.as_view(), name='alternativas-ruta'),
    path('rutas/guardar-escapada/', GuardarEscapadaView.as_view(), name='guardar-escapada'),
    path('rutas/paradas/', ParadasView.as_view(), name='paradas-ruta'),
    path('rutas/compartidas/', RutasCompartidasView.as_view(), name='rutas-compartidas'),
    path('rutas/compartidas/<uuid:enlace>/', RutaCompartidaView.as_view(), name='ruta-compartida-api'),
]
