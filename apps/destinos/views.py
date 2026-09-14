from django.db.models import Q, Prefetch
from rest_framework import generics
from rest_framework.permissions import AllowAny

from .models import Categoria, Destino, Municipio, Region, Servicio
from .serializers import (
    CategoriaSerializer, DestinoSerializer, FiltrosDestinoSerializer,
    MunicipioSerializer, RegionSerializer, ServicioSerializer,
)


def destinos_publicos(con_fotos=False):
    queryset = Destino.objects.filter(es_activo=True).select_related(
        'municipio__region',
    ).prefetch_related('categorias', 'servicios')
    if con_fotos:
        from apps.comunidad.models import Aporte
        fotos = Aporte.objects.filter(tipo='foto', estado='publicado', autor__es_activo=True).order_by('-creado', '-pk')[:1]
        queryset = queryset.prefetch_related(Prefetch('aportes', queryset=fotos, to_attr='fotos_publicas'))
    return queryset


class DestinoListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = DestinoSerializer

    def get_queryset(self):
        filtros = FiltrosDestinoSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)
        datos = filtros.validated_data
        queryset = destinos_publicos()
        if datos.get('q'):
            texto = datos['q']
            queryset = queryset.filter(
                Q(nombre__icontains=texto) | Q(descripcion__icontains=texto)
                | Q(municipio__nombre__icontains=texto)
            )
        campos = {
            'categoria': 'categorias__slug', 'municipio': 'municipio__slug',
            'region': 'municipio__region__slug', 'servicio': 'servicios__slug',
        }
        for parametro, campo in campos.items():
            if parametro in datos:
                queryset = queryset.filter(**{campo: datos[parametro]})
        from apps.comunidad.filtros import filtrar_comunidad
        return filtrar_comunidad(queryset, datos).distinct()


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
