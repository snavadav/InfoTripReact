"""Información aportada por personas: nunca se rellena un dato desconocido."""
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Colaboracion, Confirmacion, Favorito, ReporteColaboracion
from .selectors import confirmaciones_validas, dato_vigente, publicas
from .views import AporteThrottle
from apps.destinos.models import Destino
from apps.metricas.models import registrar


class ColaboracionSerializer(serializers.ModelSerializer):
    autor_nombre = serializers.CharField(source='autor.nombre', read_only=True)

    class Meta:
        model = Colaboracion
        fields = [
            'id',
            'tipo',
            'campo',
            'texto',
            'fuente',
            'fecha_dato',
            'pregunta',
            'estado',
            'creado',
            'autor_nombre',
        ]
        read_only_fields = ['id', 'estado', 'creado', 'autor_nombre']

    def validate(self, attrs):
        tipo = attrs['tipo']
        parent = attrs.get('pregunta')
        if attrs.get('fecha_dato') and attrs['fecha_dato'] > timezone.localdate():
            raise serializers.ValidationError({'fecha_dato': 'La fecha no puede ser futura.'})
        if tipo == 'correccion':
            if not attrs.get('campo') or not attrs.get('fuente') or not attrs.get('fecha_dato'):
                raise serializers.ValidationError(
                    'Incluye el dato que actualizas, su fuente y la fecha en que lo consultaste.'
                )
        elif attrs.get('campo'):
            raise serializers.ValidationError({'campo': 'Solo las correcciones llevan un campo.'})
        if tipo == 'respuesta':
            destino = self.context['view'].destino()
            if (
                not parent
                or parent.tipo != 'pregunta'
                or parent.destino_id != destino.pk
                or not publicas().filter(pk=parent.pk).exists()
            ):
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
        destino = self.destino()
        serializer.save(autor=self.request.user, destino=destino, estado='pendiente')
        registrar('dato_enviado', usuario=self.request.user, destino=destino.slug)


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


class EstadoFavoritoSerializer(serializers.Serializer):
    favorito = serializers.BooleanField()


class FavoritoView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: EstadoFavoritoSerializer})
    def get(self, request, slug):
        destino = get_object_or_404(Destino, slug=slug, es_activo=True)
        return Response({'favorito': Favorito.objects.filter(autor=request.user, destino=destino).exists()})

    @extend_schema(request=None, responses={200: EstadoFavoritoSerializer})
    def put(self, request, slug):
        destino = get_object_or_404(Destino, slug=slug, es_activo=True)
        _, creado = Favorito.objects.get_or_create(autor=request.user, destino=destino)
        if creado:
            registrar('favorito_guardado', usuario=request.user, destino=destino.slug)
        return Response({'favorito': True})

    @extend_schema(responses={204: None})
    def delete(self, request, slug):
        Favorito.objects.filter(autor=request.user, destino__slug=slug).delete()
        return Response(status=204)


class ConfirmarDatoView(APIView):
    """POST: confirma que un dato práctico vigente sigue siendo correcto hoy."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [AporteThrottle]

    @extend_schema(request=None, responses={200: inline_serializer('DatoConfirmado', fields={
        'confirmaciones': serializers.IntegerField(), 'fecha': serializers.DateField(),
    })})
    def post(self, request, pk):
        dato = get_object_or_404(publicas().filter(tipo='correccion'), pk=pk)
        if dato.autor_id == request.user.pk:
            raise serializers.ValidationError('Tu propio dato ya cuenta con la fecha en que lo consultaste.')
        if dato_vigente(dato).pk != dato.pk:
            raise serializers.ValidationError('Hay una versión más reciente de este dato. Confirma esa versión.')
        hoy = timezone.localdate()
        Confirmacion.objects.update_or_create(dato=dato, autor=request.user, defaults={'fecha': hoy})
        registrar('dato_confirmado', usuario=request.user, destino=dato.destino.slug)
        total = confirmaciones_validas().filter(dato=dato).count()
        return Response({'confirmaciones': total, 'fecha': hoy})


class ReporteColaboracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReporteColaboracion
        fields = ['id', 'motivo', 'resuelto', 'creado']
        read_only_fields = ['resuelto', 'creado']


class ReportarColaboracionView(generics.CreateAPIView):
    """POST: reporta un dato práctico, una pregunta o una respuesta publicados por otra persona."""
    permission_classes = [IsAuthenticated]
    serializer_class = ReporteColaboracionSerializer
    throttle_classes = [AporteThrottle]

    def perform_create(self, serializer):
        colaboracion = get_object_or_404(publicas(), pk=self.kwargs['pk'])
        if colaboracion.autor_id == self.request.user.pk:
            raise serializers.ValidationError('No puedes reportar tu propio aporte.')
        try:
            with transaction.atomic():
                serializer.save(autor=self.request.user, colaboracion=colaboracion)
                registrar('reporte_enviado', usuario=self.request.user, destino=colaboracion.destino.slug)
        except IntegrityError:
            raise serializers.ValidationError('Ya reportaste esta información.')
