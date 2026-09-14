"""Planes privados y presupuestos introducidos por el viajero, en MXN."""
from decimal import Decimal, ROUND_HALF_UP
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from .models import Viaje


class GastoSerializer(serializers.Serializer):
    concepto = serializers.ChoiceField(choices=['transporte', 'comida', 'entradas', 'alojamiento', 'otros'])
    descripcion = serializers.CharField(max_length=120)
    monto = serializers.DecimalField(max_digits=9, decimal_places=2, min_value=Decimal('0'))
    reparto = serializers.ChoiceField(choices=['individual', 'compartido'])
    cantidad = serializers.IntegerField(min_value=1, max_value=365)


class ViajeSerializer(serializers.ModelSerializer):
    gastos = GastoSerializer(many=True, max_length=100)
    resumen = serializers.SerializerMethodField()

    class Meta:
        model = Viaje
        fields = ['id', 'nombre', 'destino', 'fecha_inicio', 'fecha_fin', 'personas', 'presupuesto', 'gastos', 'resumen', 'actualizado']
        read_only_fields = ['id', 'actualizado']

    def validate(self, attrs):
        start = attrs.get('fecha_inicio', getattr(self.instance, 'fecha_inicio', None))
        end = attrs.get('fecha_fin', getattr(self.instance, 'fecha_fin', None))
        if start and end and end < start:
            raise serializers.ValidationError({'fecha_fin': 'El regreso no puede ser anterior a la salida.'})
        return attrs

    def validate_gastos(self, gastos):
        # JSON guarda importes como texto decimal para evitar redondeos binarios.
        return [{**g, 'monto': str(g['monto'])} for g in gastos]

    def get_resumen(self, obj):
        total = sum((Decimal(g['monto']) * g['cantidad'] * (obj.personas if g['reparto'] == 'individual' else 1) for g in obj.gastos), Decimal('0'))
        money = lambda value: str(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
        return {'total': money(total), 'por_persona': money(total / obj.personas), 'disponible': money(obj.presupuesto - total)}


class MisViajesView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ViajeSerializer

    def get_queryset(self):
        return Viaje.objects.filter(autor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(autor=self.request.user)


class ViajeView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ViajeSerializer
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return Viaje.objects.filter(autor=self.request.user)
