"""
InfoTrip — apps/usuarios/views.py
Vistas de autenticación: registro, login, perfil, logout
"""

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework              import serializers, status, generics
from rest_framework.views        import APIView
from rest_framework.response     import Response
from rest_framework.permissions  import IsAuthenticated, AllowAny
from rest_framework.throttling   import AnonRateThrottle
from rest_framework_simplejwt.exceptions    import TokenError
from rest_framework_simplejwt.tokens        import RefreshToken
from django.db                   import IntegrityError, transaction

from .models      import Usuario
from .sesion      import COOKIE_REFRESH, borrar_cookie_refresh, exigir_csrf
from .serializers import RegistroSerializer, UsuarioPerfilSerializer, CambiarPasswordSerializer


class RegistroThrottle(AnonRateThrottle):
    rate = '10/hour'
    scope = 'registro'


# ─── REGISTRO ─────────────────────────────────────────────────
class RegistroView(generics.CreateAPIView):
    """
    POST /api/v1/auth/registro/
    Crea un usuario sin emitir tokens; debe verificar su correo al iniciar sesión.
    La respuesta es la misma si el correo ya tenía cuenta, para no revelarlo.
    """
    authentication_classes = []
    serializer_class   = RegistroSerializer
    permission_classes = [AllowAny]
    throttle_classes   = [RegistroThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not Usuario.objects.filter(email__iexact=serializer.validated_data['email']).exists():
            try:
                with transaction.atomic():
                    serializer.save()
            except IntegrityError:
                pass  # Registro simultáneo del mismo correo: la cuenta ya existe.

        return Response(
            {
                'mensaje': ('Registro recibido. Inicia sesión con tu correo y contraseña '
                            'para verificar tu cuenta con un código.'),
                'requiere_verificacion': True,
            },
            status=status.HTTP_201_CREATED,
        )


# ─── LOGOUT ───────────────────────────────────────────────────
class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Invalida el refresh token de la cookie de sesión (blacklist) y borra la cookie.
    No pide access token: al abrir una página aún no hay uno en memoria.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=None, responses={
        200: inline_serializer('SesionCerrada', fields={'mensaje': serializers.CharField()}),
    })
    def post(self, request):
        exigir_csrf(request)
        refresh_token = request.COOKIES.get(COOKIE_REFRESH)
        if not refresh_token:
            return Response({'error': 'No hay una sesión activa.'}, status=status.HTTP_400_BAD_REQUEST)
        # Solo se capturan errores del token: cualquier otro fallo debe verse, no convertirse en un 400.
        try:
            RefreshToken(refresh_token).blacklist()
            respuesta = Response({'mensaje': 'Sesión cerrada correctamente.'})
        except TokenError:
            respuesta = Response({'error': 'Token inválido o ya expirado.'}, status=status.HTTP_400_BAD_REQUEST)
        borrar_cookie_refresh(respuesta)
        return respuesta


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

    @extend_schema(request=CambiarPasswordSerializer, responses={200: inline_serializer('ContrasenaCambiada', fields={
        'mensaje': serializers.CharField(),
    })})
    def post(self, request):
        serializer = CambiarPasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Cambiar la contraseña revoca los tokens; la cookie ya no sirve.
        respuesta = Response({'mensaje': 'Contraseña actualizada correctamente.'})
        borrar_cookie_refresh(respuesta)
        return respuesta
