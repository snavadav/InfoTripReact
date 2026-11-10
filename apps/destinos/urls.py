from django.urls import path

from . import direcciones, lugares, views

app_name = 'destinos'

urlpatterns = [
    path('destinos/', views.DestinoListView.as_view(), name='lista'),
    path('sugerencias/', views.SugerenciasView.as_view(), name='sugerencias'),
    path('destinos/<slug:slug>/', views.DestinoDetailView.as_view(), name='detalle'),
    path('lugares/', lugares.LugaresZonaView.as_view(), name='lugares'),
    path('lugares/cerca/', lugares.LugaresCercaView.as_view(), name='lugares-cerca'),
    path('direcciones/sugerir/', direcciones.SugerirView.as_view(), name='direcciones-sugerir'),
    path('direcciones/buscar/', direcciones.BuscarView.as_view(), name='direcciones-buscar'),
    path('direcciones/inversa/', direcciones.InversaView.as_view(), name='direcciones-inversa'),
    path('regiones/', views.RegionListView.as_view(), name='regiones'),
    path('municipios/', views.MunicipioListView.as_view(), name='municipios'),
    path('categorias/', views.CategoriaListView.as_view(), name='categorias'),
    path('servicios/', views.ServicioListView.as_view(), name='servicios'),
]
