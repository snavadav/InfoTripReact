"""Pasaporte de Pueblos Mágicos: un sello por cada visita comprobada, con una tarjeta para compartir."""
from django.shortcuts import get_object_or_404, render
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.destinos.models import Destino
from .models import PasaporteCompartido, VisitaComprobada
from .selectors import PUEBLOS_MAGICOS, SLUGS_PUEBLOS


def sellos_de(usuario=None):
    """Los 12 pueblos. `disponible`: ya tiene ficha publicada y por tanto se puede ganar su sello."""
    publicados = set(Destino.objects.filter(es_activo=True, slug__in=SLUGS_PUEBLOS).values_list('slug', flat=True))
    visitados = set()
    if usuario:
        visitados = set(VisitaComprobada.objects.filter(autor=usuario, destino__slug__in=publicados)
                        .values_list('destino__slug', flat=True))
    return [{'slug': slug, 'nombre': nombre, 'disponible': slug in publicados, 'sello': slug in visitados}
            for slug, nombre in PUEBLOS_MAGICOS]


class MiPasaporteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: inline_serializer('MiPasaporte', fields={
        'sellos': inline_serializer('SelloDePasaporte', fields={
            'slug': serializers.SlugField(), 'nombre': serializers.CharField(),
            'disponible': serializers.BooleanField(), 'sello': serializers.BooleanField(),
        }, many=True),
        'total': serializers.IntegerField(), 'de': serializers.IntegerField(),
        'enlace': serializers.UUIDField(allow_null=True),
    })})
    def get(self, request):
        sellos = sellos_de(request.user)
        compartido = PasaporteCompartido.objects.filter(usuario=request.user).first()
        return Response({'sellos': sellos, 'total': sum(sello['sello'] for sello in sellos), 'de': len(sellos),
                         'enlace': compartido.enlace if compartido else None})


class CompartirPasaporteView(APIView):
    """POST crea el enlace público de la tarjeta; DELETE lo retira."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: inline_serializer('EnlaceDePasaporte', fields={
        'enlace': serializers.UUIDField(),
    })})
    def post(self, request):
        compartido, _ = PasaporteCompartido.objects.get_or_create(usuario=request.user)
        return Response({'enlace': compartido.enlace})

    @extend_schema(responses={204: None})
    def delete(self, request):
        PasaporteCompartido.objects.filter(usuario=request.user).delete()
        return Response(status=204)


def pasaporte(request):
    return render(request, 'comunidad/pasaporte.html', {
        'sellos': sellos_de(),
        'seo': {'titulo': 'Pasaporte de Pueblos Mágicos de Jalisco — InfoTrip',
                'descripcion': 'Visita los 12 Pueblos Mágicos de Jalisco y junta un sello por cada uno.'},
    })


def pasaporte_publico(request, enlace):
    """Tarjeta para compartir: nombre y sellos, sin fechas, para no revelar cuándo estuvo la persona en cada lugar."""
    compartido = get_object_or_404(PasaporteCompartido.objects.select_related('usuario'), enlace=enlace,
                                   usuario__es_activo=True)
    sellos = sellos_de(compartido.usuario)
    return render(request, 'comunidad/pasaporte_publico.html', {
        'nombre': compartido.usuario.nombre, 'sellos': sellos, 'de': len(sellos),
        'total': sum(sello['sello'] for sello in sellos),
    })
