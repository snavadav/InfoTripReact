"""
InfoTrip — apps/usuarios/views.py
Vistas de autenticación: registro, login, perfil, logout
"""

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework              import serializers, status, generics
from rest_framework.views        import APIView
from rest_framework.response     import Response
from rest_framework.permissions  import IsAuthenticated, AllowAny
from rest_framework.throttling   import AnonRateThrottle, UserRateThrottle
from rest_framework_simplejwt.exceptions    import TokenError
from rest_framework_simplejwt.tokens        import RefreshToken
from django.db                   import IntegrityError, transaction
from django.utils                import timezone

from apps.metricas.models import registrar
from . import nombres
from .models      import Usuario
from .sesion      import COOKIE_REFRESH, borrar_cookie_refresh, exigir_csrf
from .verificacion import enviar_codigo, responder_a_correo_existente
from .serializers import RegistroSerializer, UsuarioPerfilSerializer, CambiarPasswordSerializer


class RegistroThrottle(AnonRateThrottle):
    rate = '10/hour'
    scope = 'registro'


# ─── REGISTRO ─────────────────────────────────────────────────
class RegistroView(generics.CreateAPIView):
    """
    POST /api/v1/auth/registro/
    Crea un usuario y le envía el código para verificar su correo y entrar.
    La respuesta es la misma si el correo ya tenía cuenta, para no revelarlo.
    """
    authentication_classes = []
    serializer_class   = RegistroSerializer
    permission_classes = [AllowAny]
    throttle_classes   = [RegistroThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        usuario = None
        if not Usuario.objects.filter(email__iexact=email).exists():
            try:
                with transaction.atomic():
                    usuario = serializer.save()
                    registrar('registro_completado', usuario=usuario)
            except IntegrityError:
                pass  # Registro simultáneo del mismo correo: la cuenta ya existe.
        datos = enviar_codigo(usuario) if usuario else responder_a_correo_existente(email)
        return Response(datos, status=status.HTTP_201_CREATED)


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


# ─── NOMBRE DE USUARIO ────────────────────────────────────────
class DisponibleThrottle(UserRateThrottle):
    """Se consulta mientras la persona escribe: suficiente para eso, poco para recorrer la lista de cuentas."""
    rate = '60/min'
    scope = 'username_disponible'


class CambioUsuarioThrottle(UserRateThrottle):
    rate = '20/hour'
    scope = 'username_cambio'


class NombreUsuarioSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=40)

    def validate_username(self, valor):
        nombre = nombres.normalizar(valor)
        motivo = nombres.problema(nombre)
        if motivo:
            raise serializers.ValidationError(motivo)
        if nombres.ocupado(nombre, self.context['request'].user):
            raise serializers.ValidationError('Ese nombre ya lo usa otra persona.')
        return nombre


def estado_nombre(usuario):
    desde = nombres.puede_cambiar_desde(usuario)
    return {'username': usuario.username, 'sugerencia': '' if usuario.username else nombres.sugerir(usuario),
            'puede_cambiar': desde is None, 'cambiar_desde': desde}


ESTADO_NOMBRE = inline_serializer('EstadoNombreUsuario', fields={
    'username': serializers.CharField(allow_null=True), 'sugerencia': serializers.CharField(),
    'puede_cambiar': serializers.BooleanField(), 'cambiar_desde': serializers.DateTimeField(allow_null=True),
})


class NombreUsuarioView(APIView):
    """GET: tu nombre y, si aún no tienes, una sugerencia que no se guarda. POST: elegirlo o cambiarlo."""
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        return [CambioUsuarioThrottle()] if self.request.method == 'POST' else super().get_throttles()

    @extend_schema(responses={200: ESTADO_NOMBRE})
    def get(self, request):
        return Response(estado_nombre(request.user))

    @extend_schema(request=NombreUsuarioSerializer, responses={200: ESTADO_NOMBRE})
    def post(self, request):
        datos = NombreUsuarioSerializer(data=request.data, context={'request': request})
        datos.is_valid(raise_exception=True)
        nuevo = datos.validated_data['username']
        with transaction.atomic():
            usuario = Usuario.objects.select_for_update().get(pk=request.user.pk)
            if usuario.username == nuevo:
                return Response(estado_nombre(usuario))
            desde = nombres.puede_cambiar_desde(usuario)
            if desde:
                raise serializers.ValidationError({'username': (
                    f'Solo puedes cambiarlo una vez cada {nombres.DIAS_ENTRE_CAMBIOS} días. '
                    f'Podrás hacerlo a partir del {timezone.localtime(desde):%d/%m/%Y}.')})
            usuario.username = nuevo
            usuario.username_cambiado = timezone.now()
            try:
                with transaction.atomic():
                    usuario.save(update_fields=['username', 'username_cambiado'])
            except IntegrityError:
                raise serializers.ValidationError({'username': 'Ese nombre ya lo usa otra persona.'})
        return Response(estado_nombre(usuario))


class DisponibleView(APIView):
    """GET ?username=: si se puede usar, para avisar mientras se escribe. No dice nada más de nadie."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [DisponibleThrottle]

    @extend_schema(responses={200: inline_serializer('NombreDisponible', fields={
        'username': serializers.CharField(), 'disponible': serializers.BooleanField(),
        'motivo': serializers.CharField(),
    })})
    def get(self, request):
        nombre = nombres.normalizar(request.query_params.get('username', ''))[:40]
        motivo = nombres.problema(nombre)
        if not motivo and nombres.ocupado(nombre, request.user):
            motivo = 'Ese nombre ya lo usa otra persona.'
        return Response({'username': nombre, 'disponible': not motivo, 'motivo': motivo})
