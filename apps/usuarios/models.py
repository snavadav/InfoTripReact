"""
InfoTrip — apps/usuarios/models.py
Modelo de usuario personalizado basado en AbstractBaseUser
"""

from django.db import models
from django.db.models.functions import Lower
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import uuid


def normalizar_email(email):
    """El correo identifica la cuenta: se compara y se guarda siempre en minúsculas."""
    return (email or '').strip().lower()


class UsuarioManager(BaseUserManager):
    """Manager personalizado para el modelo Usuario."""

    @classmethod
    def normalize_email(cls, email):
        return normalizar_email(email)

    def get_by_natural_key(self, email):
        # Lo usan authenticate() y el login del admin.
        return self.get(email__iexact=normalizar_email(email))

    def create_user(self, email, nombre, apellido, password=None, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio.')
        email = self.normalize_email(email)
        user  = self.model(email=email, nombre=nombre, apellido=apellido, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, nombre, apellido, password=None, **extra_fields):
        extra_fields.setdefault('es_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('es_activo', True)
        return self.create_user(email, nombre, apellido, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """
    Modelo de usuario personalizado para InfoTrip.
    Usa email como identificador principal en lugar de username.
    """

    uuid          = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    nombre        = models.CharField(max_length=100)
    apellido      = models.CharField(max_length=100, blank=True)
    email         = models.EmailField(unique=True)
    foto_perfil   = models.ImageField(upload_to='perfiles/', blank=True, null=True)
    ciudad_origen = models.CharField(max_length=150, blank=True)
    bio           = models.TextField(blank=True)
    es_activo     = models.BooleanField(default=True)
    es_staff      = models.BooleanField(default=False)
    es_verificado = models.BooleanField(default=False)
    # Correos de novedades. Los códigos de acceso y la recuperación de contraseña se envían siempre.
    avisos_correo = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    ultimo_acceso  = models.DateTimeField(null=True, blank=True)

    objects = UsuarioManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['nombre', 'apellido']

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        constraints = [
            models.UniqueConstraint(Lower('email'), name='usuario_email_unico_sin_mayusculas'),
        ]

    def __str__(self):
        return f'{self.nombre} {self.apellido} <{self.email}>'

    def save(self, *args, **kwargs):
        self.email = normalizar_email(self.email)
        super().save(*args, **kwargs)

    @property
    def nombre_completo(self) -> str:
        return f'{self.nombre} {self.apellido}'.strip()

    # Requerido por Django admin
    @property
    def is_staff(self):
        return self.es_staff

    @property
    def is_active(self):
        return self.es_activo
class CodigoAcceso(models.Model):
    """Un único desafío vigente por cuenta; nunca se guarda el código en claro."""
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name='codigo_acceso')
    desafio = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    codigo_hash = models.CharField(max_length=64)
    credencial_hash = models.CharField(max_length=64)
    email = models.EmailField()
    enviado = models.DateTimeField()
    expira = models.DateTimeField()
    intentos = models.PositiveSmallIntegerField(default=0)
    consumido = models.BooleanField(default=False)
