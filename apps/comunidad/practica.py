"""Información aportada por personas: nunca se rellena un dato desconocido."""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Favorito, Colaboracion
from .selectors import publicas
from .views import AporteThrottle
from apps.destinos.models import Destino


class ColaboracionSerializer(serializers.ModelSerializer):
    autor_nombre = serializers.CharField(source='autor.nombre', read_only=True)

    class Meta:
        model = Colaboracion
        fields = ['id', 'tipo', 'campo', 'texto', 'fuente', 'fecha_dato', 'pregunta', 'estado', 'creado', 'autor_nombre']
        read_only_fields = ['id', 'estado', 'creado', 'autor_nombre']

    def validate(self, attrs):
        tipo = attrs['tipo']
        parent = attrs.get('pregunta')
        if attrs.get('fecha_dato') and attrs['fecha_dato'] > timezone.localdate():
            raise serializers.ValidationError({'fecha_dato': 'La fecha no puede ser futura.'})
        if tipo == 'correccion':
            if not attrs.get('campo') or not attrs.get('fuente') or not attrs.get('fecha_dato'):
                raise serializers.ValidationError('Incluye el dato que actualizas, su fuente y la fecha en que lo consultaste.')
        elif attrs.get('campo'):
            raise serializers.ValidationError({'campo': 'Solo las correcciones llevan un campo.'})
        if tipo == 'respuesta':
            destino = self.context['view'].destino()
            if not parent or parent.tipo != 'pregunta' or parent.destino_id != destino.pk or not publicas().filter(pk=parent.pk).exists():
                raise serializers.ValidationError({'pregunta': 'Selecciona una pregunta publicada de este destino.'})
        elif parent:
            raise serializers.ValidationError({'pregunta': 'Solo las respuestas llevan una pregunta.'})
        return attrs


class ColaboracionesView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = ColaboracionSerializer
    throttle_classes = [AporteThrottle]

    def get_throttles(self):
        return super().get_throttles() if self.request.method == 'POST' else []

    def destino(self):
        return get_object_or_404(Destino, slug=self.kwargs['slug'], es_activo=True)

    def get_queryset(self):
        return publicas().filter(destino=self.destino()).exclude(tipo='respuesta').select_related('autor')

    def perform_create(self, serializer):
        serializer.save(autor=self.request.user, destino=self.destino(), estado='pendiente')


class FavoritoSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source='destino.nombre', read_only=True)
    slug = serializers.CharField(source='destino.slug', read_only=True)
    activo = serializers.BooleanField(source='destino.es_activo', read_only=True)

    class Meta:
        model = Favorito
        fields = ['id', 'destino', 'nombre', 'slug', 'activo', 'creado']


class FavoritosView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FavoritoSerializer

    def get_queryset(self):
        return Favorito.objects.filter(autor=self.request.user).select_related('destino')


class FavoritoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        destino = get_object_or_404(Destino, slug=slug, es_activo=True)
        return Response({'favorito': Favorito.objects.filter(autor=request.user, destino=destino).exists()})

    def put(self, request, slug):
        destino = get_object_or_404(Destino, slug=slug, es_activo=True)
        Favorito.objects.get_or_create(autor=request.user, destino=destino)
        return Response({'favorito': True})

    def delete(self, request, slug):
        Favorito.objects.filter(autor=request.user, destino__slug=slug).delete()
        return Response(status=204)
