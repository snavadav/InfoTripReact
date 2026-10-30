"""Página para negocios locales: mide el interés, sin cobros. Un "me interesa" no prueba que alguien pagaría."""
from django.shortcuts import render
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.metricas.models import registrar
from .models import InteresNegocio


class InteresThrottle(AnonRateThrottle):
    # Cuenta también los envíos con errores: con pocos, quien se equivoca al escribir se quedaría fuera.
    rate = '10/hour'
    scope = 'interes_negocio'


class InteresNegocioSerializer(serializers.ModelSerializer):
    acepto = serializers.BooleanField(write_only=True)
    # Campo trampa: invisible para las personas; los robots que llenan todo se delatan.
    sitio_web = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = InteresNegocio
        fields = ['negocio', 'contacto', 'correo', 'telefono', 'municipio', 'mensaje', 'acepto', 'sitio_web']

    def validate_acepto(self, valor):
        if not valor:
            raise serializers.ValidationError('Necesitamos tu autorización para guardar tus datos de contacto.')
        return valor


class InteresNegocioView(APIView):
    """POST: registra el interés de un negocio. Sin sesión, para que pueda escribir sin crear una cuenta."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [InteresThrottle]

    @extend_schema(request=InteresNegocioSerializer, responses={201: inline_serializer('InteresRecibido', fields={
        'mensaje': serializers.CharField(),
    })})
    def post(self, request):
        datos = InteresNegocioSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = dict(datos.validated_data)
        campos.pop('acepto')
        # A un robot se le responde igual, para que no sepa que se le detectó.
        if not campos.pop('sitio_web', ''):
            InteresNegocio.objects.create(**campos)
            registrar('interes_negocio')
        return Response({'mensaje': 'Gracias. Te escribiremos para platicar.'}, status=201)


def pagina_negocios(request):
    return render(request, 'comunidad/negocios.html', {
        'seo': {'titulo': 'InfoTrip para negocios locales de Jalisco',
                'descripcion': ('¿Tienes un negocio en una zona turística de Jalisco? Cuéntanos qué te serviría. '
                                'InfoTrip es un proyecto académico y hoy no cobra por nada.')},
    })
