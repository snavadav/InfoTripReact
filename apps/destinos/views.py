from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import AllowAny

from apps.comunidad.selectors import con_foto_publica
from .filtros import buscar_y_filtrar
from .models import Categoria, Destino, Municipio, Region, Servicio
from .serializers import (
    CategoriaSerializer, DestinoSerializer, FiltrosDestinoSerializer,
    MunicipioSerializer, RegionSerializer, ServicioSerializer,
)


def destinos_publicos(con_fotos=False):
    queryset = Destino.objects.filter(es_activo=True).select_related(
        'municipio__region',
    ).prefetch_related('categorias', 'servicios')
    return con_foto_publica(queryset) if con_fotos else queryset


@extend_schema_view(get=extend_schema(parameters=[FiltrosDestinoSerializer]))
class DestinoListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = DestinoSerializer

    sugerencia = ''

    def get_queryset(self):
        filtros = FiltrosDestinoSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)
        queryset, self.sugerencia = buscar_y_filtrar(destinos_publicos(), filtros.validated_data)
        return queryset

    def list(self, request, *args, **kwargs):
        respuesta = super().list(request, *args, **kwargs)
        # «¿Quisiste decir…?»: el nombre más parecido cuando lo escrito tenía errores o no dio resultados.
        respuesta.data['sugerencia'] = self.sugerencia
        return respuesta


class DestinoDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = DestinoSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return destinos_publicos()


class RegionListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegionSerializer
    queryset = Region.objects.all()


class MunicipioListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = MunicipioSerializer
    queryset = Municipio.objects.select_related('region').all()


class CategoriaListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CategoriaSerializer
    queryset = Categoria.objects.all()


class ServicioListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ServicioSerializer
    queryset = Servicio.objects.all()
