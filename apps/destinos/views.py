from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view, inline_serializer
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.comunidad.selectors import con_foto_publica
from .busqueda import autocompletar
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


class SugerenciasThrottle(AnonRateThrottle):
    # El cliente espera a que se deje de escribir antes de pedir; esto solo frena abusos.
    rate = '120/min'
    scope = 'sugerencias'


class SugerenciasView(APIView):
    """GET: propuestas para el campo de búsqueda mientras se escribe (autocompletado)."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [SugerenciasThrottle]

    @extend_schema(
        parameters=[OpenApiParameter('q', str, description='Lo escrito hasta ahora (2 letras o más).')],
        responses={200: inline_serializer('Sugerencias', fields={
            'resultados': inline_serializer('Sugerencia', fields={
                'tipo': serializers.ChoiceField(choices=['coleccion', 'categoria', 'municipio', 'destino', 'lugar']),
                'nombre': serializers.CharField(), 'detalle': serializers.CharField(), 'url': serializers.CharField(),
            }, many=True),
            'sugerencia': serializers.CharField(),
        })},
    )
    def get(self, request):
        texto = request.query_params.get('q', '')[:100]
        return Response(autocompletar(texto))
