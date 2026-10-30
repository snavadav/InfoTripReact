from decimal import Decimal
from rest_framework import serializers

from .models import Categoria, Destino, Municipio, Region, Servicio


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id', 'nombre', 'slug']


class MunicipioSerializer(serializers.ModelSerializer):
    region = RegionSerializer(read_only=True)

    class Meta:
        model = Municipio
        fields = ['id', 'nombre', 'slug', 'region']


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ['id', 'nombre', 'slug']


class ServicioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Servicio
        fields = ['id', 'nombre', 'slug']


class DestinoSerializer(serializers.ModelSerializer):
    municipio = MunicipioSerializer(read_only=True)
    categorias = CategoriaSerializer(many=True, read_only=True)
    servicios = ServicioSerializer(many=True, read_only=True)
    atribucion = serializers.SerializerMethodField()

    def get_atribucion(self, destino) -> str | None:
        return '© colaboradores de OpenStreetMap, ODbL' if destino.osm_id else None

    class Meta:
        model = Destino
        fields = [
            'id', 'nombre', 'slug', 'descripcion', 'municipio', 'categorias',
            'servicios', 'direccion', 'latitud', 'longitud', 'fecha_actualizacion', 'atribucion',
        ]


class FiltrosDestinoSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=200)
    categoria = serializers.SlugField(required=False, max_length=160)
    municipio = serializers.SlugField(required=False, max_length=160)
    region = serializers.SlugField(required=False, max_length=160)
    servicio = serializers.SlugField(required=False, max_length=160)

    calificacion_min = serializers.DecimalField(
        required=False, min_value=Decimal(1), max_value=Decimal(5), max_digits=2, decimal_places=1
    )
    precio_max = serializers.DecimalField(
        required=False, min_value=Decimal(0), max_value=Decimal(9999999), max_digits=9, decimal_places=2
    )
    concepto = serializers.ChoiceField(required=False, choices=['entrada', 'comida', 'alojamiento', 'transporte'])
    datos_recientes = serializers.BooleanField(required=False)
    orden = serializers.ChoiceField(required=False, choices=['recientes'])

    def validate(self, datos):
        if datos.get('precio_max') is not None and not datos.get('concepto'):
            raise serializers.ValidationError({'concepto': 'Selecciona el concepto del gasto.'})
        return datos
