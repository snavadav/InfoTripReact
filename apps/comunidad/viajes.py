"""Planes privados y presupuestos introducidos por el viajero, en MXN."""
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Viaje
from apps.destinos.models import Destino


def pesos(valor):
    return str(valor.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


class GastoSerializer(serializers.Serializer):
    concepto = serializers.ChoiceField(choices=['transporte', 'comida', 'entradas', 'alojamiento', 'otros'])
    descripcion = serializers.CharField(max_length=120)
    monto = serializers.DecimalField(max_digits=9, decimal_places=2, min_value=Decimal('0'))
    reparto = serializers.ChoiceField(choices=['individual', 'compartido'])
    cantidad = serializers.IntegerField(min_value=1, max_value=365)


class ActividadSerializer(serializers.Serializer):
    dia = serializers.IntegerField(min_value=1, max_value=366)
    hora = serializers.RegexField(r'^([01][0-9]|2[0-3]):[0-5][0-9]$', allow_blank=True)
    titulo = serializers.CharField(max_length=150)
    notas = serializers.CharField(max_length=500, allow_blank=True)


class PendienteSerializer(serializers.Serializer):
    texto = serializers.CharField(max_length=200)
    hecho = serializers.BooleanField()


class ViajeSerializer(serializers.ModelSerializer):
    gastos = GastoSerializer(many=True, max_length=100)
    resumen = serializers.SerializerMethodField()
    actividades = ActividadSerializer(many=True, max_length=150, required=False)
    pendientes = PendienteSerializer(many=True, max_length=100, required=False)
    lugares = serializers.PrimaryKeyRelatedField(many=True, queryset=Destino.objects.all(), required=False)
    lugares_detalle = serializers.SerializerMethodField()

    def validate_lugares(self, values):
        existentes = set(self.instance.lugares.values_list('pk', flat=True)) if self.instance else set()
        if any(not d.es_activo and d.pk not in existentes for d in values):
            raise serializers.ValidationError('Uno de los destinos ya no está disponible.')
        return values

    def get_lugares_detalle(self, obj) -> list[dict]:
        return [{'id': d.pk, 'nombre': d.nombre, 'slug': d.slug, 'activo': d.es_activo} for d in obj.lugares.all()]


    class Meta:
        model = Viaje
        fields = [
            'id',
            'nombre',
            'destino',
            'fecha_inicio',
            'fecha_fin',
            'personas',
            'presupuesto',
            'gastos',
            'actividades',
            'pendientes',
            'notas',
            'lugares',
            'lugares_detalle',
            'resumen',
            'actualizado',
        ]
        read_only_fields = ['id', 'actualizado']

    def validate(self, attrs):
        start = attrs.get('fecha_inicio', getattr(self.instance, 'fecha_inicio', None))
        end = attrs.get('fecha_fin', getattr(self.instance, 'fecha_fin', None))
        if start and end and end < start:
            raise serializers.ValidationError({'fecha_fin': 'El regreso no puede ser anterior a la salida.'})
        actividades = attrs.get('actividades', getattr(self.instance, 'actividades', []))
        if start and end and any(a['dia'] > (end - start).days + 1 for a in actividades):
            raise serializers.ValidationError(
                {'actividades': 'Cada actividad debe estar dentro de los días del viaje.'}
            )
        if len(attrs.get('lugares', [])) > 100:
            raise serializers.ValidationError({'lugares': 'Puedes vincular hasta 100 lugares.'})
        if 'actividades' in attrs:
            attrs['actividades'] = sorted(attrs['actividades'], key=lambda a: (a['dia'], a['hora'] or '99:99'))
        return attrs

    def validate_gastos(self, gastos):
        # JSON guarda importes como texto decimal para evitar redondeos binarios.
        return [{**g, 'monto': str(g['monto'])} for g in gastos]

    def get_resumen(self, obj) -> dict[str, str]:
        total = sum((Decimal(g['monto']) * g['cantidad'] * (obj.personas if g['reparto'] == 'individual' else 1)
                     for g in obj.gastos), Decimal('0'))
        return {
            'total': pesos(total),
            'por_persona': pesos(total / obj.personas),
            'disponible': pesos(obj.presupuesto - total),
        }


class MisViajesView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ViajeSerializer

    def get_queryset(self):
        return Viaje.objects.filter(autor=self.request.user).prefetch_related('lugares')

    def perform_create(self, serializer):
        serializer.save(autor=self.request.user)


class ViajeView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ViajeSerializer
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return Viaje.objects.filter(autor=self.request.user).prefetch_related('lugares')


class VincularLugarView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer('LugarAVincular', fields={'slug': serializers.SlugField(max_length=220)}),
        responses={200: inline_serializer('LugarVinculado', fields={'detail': serializers.CharField()})},
    )
    def post(self, request, pk):
        slug = serializers.SlugField(max_length=220).run_validation(request.data.get('slug'))
        with transaction.atomic():
            viaje = get_object_or_404(Viaje.objects.select_for_update(), pk=pk, autor=request.user)
            destino = get_object_or_404(Destino, slug=slug, es_activo=True)
            if viaje.lugares.count() >= 100 and not viaje.lugares.filter(pk=destino.pk).exists():
                raise serializers.ValidationError('Puedes vincular hasta 100 lugares.')
            viaje.lugares.add(destino)
            viaje.save(update_fields=['actualizado'])
        return Response({'detail': 'Lugar agregado a la escapada.'})
