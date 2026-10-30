from django.urls import path

from . import lugares, views

app_name = 'destinos'

urlpatterns = [
    path('destinos/', views.DestinoListView.as_view(), name='lista'),
    path('destinos/<slug:slug>/', views.DestinoDetailView.as_view(), name='detalle'),
    path('lugares/', lugares.LugaresZonaView.as_view(), name='lugares'),
    path('lugares/cerca/', lugares.LugaresCercaView.as_view(), name='lugares-cerca'),
    path('regiones/', views.RegionListView.as_view(), name='regiones'),
    path('municipios/', views.MunicipioListView.as_view(), name='municipios'),
    path('categorias/', views.CategoriaListView.as_view(), name='categorias'),
    path('servicios/', views.ServicioListView.as_view(), name='servicios'),
]
