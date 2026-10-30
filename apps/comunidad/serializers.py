from django.utils import timezone
from rest_framework import serializers
from .models import Aporte, Reporte
from apps.core.imagenes import imagen_segura, miniatura_de


class AporteSerializer(serializers.ModelSerializer):
    autor_nombre = serializers.CharField(source='autor.nombre', read_only=True)
    destino_nombre = serializers.CharField(source='destino.nombre', read_only=True)
    destino_slug = serializers.CharField(source='destino.slug', read_only=True)
    estado_nombre = serializers.CharField(source='get_estado_display', read_only=True)
    class Meta:
        model = Aporte
        fields = ['id', 'tipo', 'texto', 'fecha_visita', 'calificacion', 'imagen', 'monto', 'concepto',
                  'estado', 'estado_nombre', 'creado', 'autor_nombre', 'destino_nombre', 'destino_slug']
        read_only_fields = ['estado', 'creado']
        validators = []

    def validate_imagen(self, imagen):
        return imagen_segura(imagen) if imagen else imagen

    def validate_fecha_visita(self, fecha):
        if fecha > timezone.localdate():
            raise serializers.ValidationError('La fecha no puede estar en el futuro.')
        return fecha

    def validate(self, datos):
        tipo = datos.get('tipo', self.instance.tipo if self.instance else None)
        if self.instance and tipo != self.instance.tipo:
            raise serializers.ValidationError('No puedes cambiar el tipo de aporte.')
        def valor(campo):
            return datos.get(campo, getattr(self.instance, campo, None))
        if tipo == 'resena' and valor('calificacion') is None:
            raise serializers.ValidationError({'calificacion': 'Selecciona una calificación de 1 a 5.'})
        if tipo == 'foto' and not valor('imagen'):
            raise serializers.ValidationError({'imagen': 'Selecciona una imagen.'})
        if tipo == 'gasto' and (valor('monto') is None or not valor('concepto')):
            raise serializers.ValidationError('Indica monto en MXN y concepto del gasto.')
        for campo, requerido_por in [
            ('calificacion', 'resena'),
            ('imagen', 'foto'),
            ('monto', 'gasto'),
            ('concepto', 'gasto'),
        ]:
            if tipo != requerido_por and datos.get(campo) not in (None, ''):
                raise serializers.ValidationError({campo: 'Este campo no corresponde al tipo de aporte.'})
        if datos.get('imagen'):
            datos['miniatura'] = miniatura_de(datos['imagen'])
        return datos


class ReporteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reporte
        fields = ['id', 'motivo', 'resuelto', 'creado']
        read_only_fields = ['resuelto', 'creado']
