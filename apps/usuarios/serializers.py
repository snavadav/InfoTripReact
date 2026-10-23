"""
InfoTrip — apps/usuarios/serializers.py
Serializers para registro, login y perfil de usuario
"""

from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import Usuario, normalizar_email


class RegistroSerializer(serializers.ModelSerializer):
    """Serializer para registro de nuevo usuario."""

    password  = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label='Confirmar contraseña')

    class Meta:
        model  = Usuario
        fields = ['nombre', 'apellido', 'email', 'password', 'password2', 'ciudad_origen']
        # Sin validador de unicidad: un correo ya registrado no debe revelarse (S3).
        extra_kwargs = {'email': {'validators': []}}

    def validate_email(self, value):
        return normalizar_email(value)

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password': 'Las contraseñas no coinciden.'})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        usuario  = Usuario(**validated_data)
        usuario.set_password(password)
        usuario.save()
        return usuario


class UsuarioPerfilSerializer(serializers.ModelSerializer):
    """Serializer para leer y actualizar perfil de usuario."""

    nombre_completo = serializers.ReadOnlyField()
    bio = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate_foto_perfil(self, value):
        from apps.comunidad.imagenes import imagen_segura
        return imagen_segura(value) if value else value


    class Meta:
        model  = Usuario
        fields = [
            'uuid', 'nombre', 'apellido', 'nombre_completo',
            'email', 'foto_perfil', 'ciudad_origen', 'bio',
            'es_verificado', 'fecha_registro',
        ]
        read_only_fields = ['uuid', 'email', 'es_verificado', 'fecha_registro']


class CambiarPasswordSerializer(serializers.Serializer):
    """Serializer para cambio de contraseña."""

    password_actual   = serializers.CharField(write_only=True)
    password_nuevo    = serializers.CharField(write_only=True, validators=[validate_password])
    password_nuevo2   = serializers.CharField(write_only=True, label='Confirmar nueva contraseña')

    def validate(self, data):
        if data['password_nuevo'] != data['password_nuevo2']:
            raise serializers.ValidationError({'password_nuevo': 'Las contraseñas no coinciden.'})
        return data

    def validate_password_actual(self, value):
        usuario = self.context['request'].user
        if not usuario.check_password(value):
            raise serializers.ValidationError('La contraseña actual es incorrecta.')
        return value

    def save(self):
        usuario = self.context['request'].user
        usuario.set_password(self.validated_data['password_nuevo'])
        usuario.save()
        return usuario