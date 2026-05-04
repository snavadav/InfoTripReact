"""
InfoTrip — apps/usuarios/views.py
Vistas de autenticación: registro, login, perfil, logout
"""

from rest_framework              import status, generics
from rest_framework.views        import APIView
from rest_framework.response     import Response
from rest_framework.permissions  import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens        import RefreshToken
from rest_framework_simplejwt.views         import TokenObtainPairView
from rest_framework_simplejwt.serializers   import TokenObtainPairSerializer
from django.utils                import timezone

from .models      import Usuario
from .serializers import RegistroSerializer, UsuarioPerfilSerializer, CambiarPasswordSerializer


# ─── TOKEN PERSONALIZADO ──────────────────────────────────────
class InfoTripTokenSerializer(TokenObtainPairSerializer):
    """Agrega datos del usuario al response del login."""

    def validate(self, attrs):
        data    = super().validate(attrs)
        usuario = self.user

        # Actualizar último acceso
        usuario.ultimo_acceso = timezone.now()
        usuario.save(update_fields=['ultimo_acceso'])

        # Agregar datos del usuario al response
        data['usuario'] = {
            'uuid':          str(usuario.uuid),
            'nombre':        usuario.nombre,
            'apellido':      usuario.apellido,
            'email':         usuario.email,
            'foto_perfil':   usuario.foto_perfil.url if usuario.foto_perfil else None,
            'es_verificado': usuario.es_verificado,
        }
        return data


class LoginView(TokenObtainPairView):
    """
    POST /api/v1/auth/login/
    Retorna access token, refresh token y datos del usuario.
    """
    serializer_class = InfoTripTokenSerializer
    permission_classes = [AllowAny]


# ─── REGISTRO ─────────────────────────────────────────────────
class RegistroView(generics.CreateAPIView):
    """
    POST /api/v1/auth/registro/
    Crea un nuevo usuario y retorna sus tokens.
    """
    serializer_class   = RegistroSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()

        # Generar tokens para el nuevo usuario
        refresh = RefreshToken.for_user(usuario)

        return Response({
            'mensaje': '¡Bienvenido a InfoTrip! Tu cuenta fue creada correctamente.',
            'usuario': {
                'uuid':     str(usuario.uuid),
                'nombre':   usuario.nombre,
                'apellido': usuario.apellido,
                'email':    usuario.email,
            },
            'tokens': {
                'access':  str(refresh.access_token),
                'refresh': str(refresh),
            }
        }, status=status.HTTP_201_CREATED)


# ─── LOGOUT ───────────────────────────────────────────────────
class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Invalida el refresh token (blacklist).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if not refresh_token:
                return Response(
                    {'error': 'Se requiere el refresh token.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'mensaje': 'Sesión cerrada correctamente.'})
        except Exception:
            return Response(
                {'error': 'Token inválido o ya expirado.'},
                status=status.HTTP_400_BAD_REQUEST
            )


# ─── PERFIL ───────────────────────────────────────────────────
class PerfilView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/auth/perfil/  — Ver perfil del usuario autenticado
    PUT  /api/v1/auth/perfil/  — Actualizar perfil completo
    PATCH /api/v1/auth/perfil/ — Actualizar campos específicos
    """
    serializer_class   = UsuarioPerfilSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


# ─── CAMBIAR CONTRASEÑA ───────────────────────────────────────
class CambiarPasswordView(APIView):
    """
    POST /api/v1/auth/cambiar-password/
    Cambia la contraseña del usuario autenticado.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CambiarPasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'mensaje': 'Contraseña actualizada correctamente.'})