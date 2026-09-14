"""
InfoTrip — apps/usuarios/views.py
Vistas de autenticación: registro, login, perfil, logout
"""

from rest_framework              import status, generics
from rest_framework.views        import APIView
from rest_framework.response     import Response
from rest_framework.permissions  import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens        import RefreshToken
from django.utils                import timezone

from .models      import Usuario
from .serializers import RegistroSerializer, UsuarioPerfilSerializer, CambiarPasswordSerializer


# ─── REGISTRO ─────────────────────────────────────────────────
class RegistroView(generics.CreateAPIView):
    """
    POST /api/v1/auth/registro/
    Crea un usuario sin emitir tokens; debe verificar su correo al iniciar sesión.
    """
    authentication_classes = []
    serializer_class   = RegistroSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()

        return Response({
            'mensaje': 'Cuenta creada. Inicia sesión para verificar tu correo con un código.',
            'requiere_verificacion': True,
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