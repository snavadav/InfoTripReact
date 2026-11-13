"""API de amigos: buscar por @username, solicitudes, bloqueos y el perfil que ven los demás.

Nunca se busca ni se muestra el correo. El nombre y el @username siempre se ven; el pasaporte, los lugares
visitados (sin fechas) y los amigos dependen de la visibilidad que elige cada persona.
"""
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.comunidad import notificar
from apps.comunidad.models import VisitaComprobada
from apps.comunidad.pasaporte import sellos_de
from apps.usuarios.models import Usuario
from .models import Amistad, Bloqueo
from .relaciones import amigos_de, amistad_entre, bloqueado, puede_ver_detalle, relacion

MAXIMO_RESULTADOS = 10
DIAS_TRAS_RECHAZO = 30
BUSQUEDA = re.compile(r'^[a-z0-9._]{2,30}$')


class SolicitudThrottle(UserRateThrottle):
    rate = '30/hour'
    scope = 'solicitudes_amistad'


class BusquedaThrottle(UserRateThrottle):
    rate = '60/min'
    scope = 'busqueda_personas'


class BloqueoThrottle(UserRateThrottle):
    rate = '60/hour'
    scope = 'bloqueos'


PERSONA = inline_serializer('Persona', fields={
    'username': serializers.CharField(), 'nombre': serializers.CharField(),
    'relacion': serializers.CharField(required=False), 'solicitud': serializers.IntegerField(required=False),
}, many=True)


def persona(usuario, rel=None, visitante=None):
    """Lo mínimo que se muestra de alguien: nombre y @username. Nunca el correo.

    Con `visitante` y una solicitud pendiente entre ambos, incluye su id para aceptarla o cancelarla.
    """
    datos = {'username': usuario.username, 'nombre': usuario.nombre_completo}
    if rel:
        datos['relacion'] = rel
    if visitante and rel in ('enviada', 'recibida'):
        datos['solicitud'] = amistad_entre(visitante, usuario).pk
    return datos


def avisar(usuario, texto, actor, ancla):
    notificar.avisar(usuario, 'amistad', texto, f'/amigos/#{ancla}', actor=actor)


def cuenta_de(username, visitante=None):
    """La cuenta con ese @username, o 404 si no existe, se dio de baja o bloqueó a quien pregunta."""
    usuario = get_object_or_404(Usuario, username__iexact=(username or '').lstrip('@'), es_activo=True)
    if visitante and Bloqueo.objects.filter(de=usuario, para=visitante).exists():
        raise Http404
    return usuario


def exigir_username(usuario):
    if not usuario.username:
        raise serializers.ValidationError('Primero elige tu nombre de usuario.')


class AmigosView(APIView):
    """GET: tus amigos, las solicitudes recibidas y enviadas y a quién bloqueaste."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: inline_serializer('MisAmigos', fields={
        'username': serializers.CharField(allow_null=True), 'amigos': PERSONA, 'recibidas': PERSONA,
        'enviadas': PERSONA, 'bloqueados': PERSONA,
    })})
    def get(self, request):
        yo = request.user
        pendientes = Amistad.objects.filter(estado='pendiente').select_related('de', 'para')
        return Response({
            'username': yo.username,
            'amigos': [persona(amigo, 'amigos') for amigo in amigos_de(yo) if amigo.username],
            'recibidas': [{**persona(s.de, 'recibida'), 'solicitud': s.pk}
                          for s in pendientes.filter(para=yo, de__es_activo=True)],
            'enviadas': [{**persona(s.para, 'enviada'), 'solicitud': s.pk}
                         for s in pendientes.filter(de=yo, para__es_activo=True)],
            'bloqueados': [persona(b.para, 'bloqueado') for b in Bloqueo.objects.filter(de=yo).select_related('para')
                           if b.para.username],
        })


class BuscarView(APIView):
    """GET ?q=@ana: coincidencia exacta o por prefijo del @username, como máximo 10. Nunca por correo ni nombre."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [BusquedaThrottle]

    @extend_schema(parameters=[OpenApiParameter('q', str)], responses={200: PERSONA})
    def get(self, request):
        texto = (request.query_params.get('q') or '').strip().lstrip('@').lower()
        if not BUSQUEDA.match(texto):
            return Response([])
        yo = request.user
        amigos = set(amigos_de(yo).values_list('pk', flat=True))
        bloqueos = Bloqueo.objects.filter(Q(de=yo) | Q(para=yo)).values_list('de_id', 'para_id')
        excluidos = {pk for par in bloqueos for pk in par} | {yo.pk}
        candidatos = (Usuario.objects.filter(username__istartswith=texto, es_activo=True)
                      .exclude(pk__in=excluidos)
                      # Una cuenta privada solo la encuentran sus amigos.
                      .exclude(Q(visibilidad='privado') & ~Q(pk__in=amigos))
                      .order_by('username')[:50])
        resultados = sorted(candidatos, key=lambda u: (u.username != texto, u.username))[:MAXIMO_RESULTADOS]
        return Response([persona(usuario, relacion(yo, usuario), yo) for usuario in resultados])


class EnviarSolicitudSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=40)


class SolicitudesView(APIView):
    """POST {username}: envía una solicitud. Si esa persona ya te había enviado una, quedan como amigos."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [SolicitudThrottle]

    @extend_schema(request=EnviarSolicitudSerializer, responses={201: PERSONA.child})
    def post(self, request):
        datos = EnviarSolicitudSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        yo = request.user
        exigir_username(yo)
        otro = cuenta_de(datos.validated_data['username'], yo)
        if otro.pk == yo.pk:
            raise serializers.ValidationError('No puedes enviarte una solicitud a ti.')
        if not otro.username:
            raise Http404
        if Bloqueo.objects.filter(de=yo, para=otro).exists():
            raise serializers.ValidationError('Desbloquea a esta persona para enviarle una solicitud.')
        with transaction.atomic():
            amistad = amistad_entre(yo, otro)
            if amistad:
                amistad = Amistad.objects.select_for_update().get(pk=amistad.pk)
            if amistad and amistad.estado == 'aceptada':
                return Response(persona(otro, 'amigos'), status=200)
            if amistad and amistad.estado == 'pendiente':
                if amistad.de_id == yo.pk:
                    return Response(persona(otro, 'enviada', yo), status=200)
                return Response(persona(otro, aceptar(amistad)), status=200)
            if amistad and amistad.de_id == yo.pk and amistad.respondido and \
                    amistad.respondido > timezone.now() - timedelta(days=DIAS_TRAS_RECHAZO):
                raise serializers.ValidationError('No puedes enviar otra solicitud a esta persona por ahora.')
            try:
                with transaction.atomic():
                    if amistad:
                        amistad.de, amistad.para, amistad.estado, amistad.respondido = yo, otro, 'pendiente', None
                        amistad.creado = timezone.now()
                        amistad.save()
                    else:
                        Amistad.objects.create(de=yo, para=otro)
            except IntegrityError:
                # Solicitud cruzada al mismo tiempo: la otra ya creó el registro de la pareja.
                return Response(persona(otro, relacion(yo, otro)), status=200)
            avisar(otro, f'@{yo.username} te envió una solicitud de amistad.', yo, 'recibidas-titulo')
        return Response(persona(otro, 'enviada', yo), status=201)


def aceptar(amistad):
    amistad.estado, amistad.respondido = 'aceptada', timezone.now()
    amistad.save(update_fields=['estado', 'respondido'])
    if amistad.para.username:
        avisar(amistad.de, f'@{amistad.para.username} aceptó tu solicitud de amistad.', amistad.para,
               'mis-amigos-titulo')
    return 'amigos'


def solicitud_recibida(request, pk):
    return get_object_or_404(Amistad.objects.select_for_update().select_related('de', 'para'),
                             pk=pk, para=request.user, estado='pendiente')


class AceptarView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: PERSONA.child})
    def post(self, request, pk):
        with transaction.atomic():
            amistad = solicitud_recibida(request, pk)
            return Response(persona(amistad.de, aceptar(amistad)))


class RechazarView(APIView):
    """POST: quien envió no recibe aviso; podrá volver a intentarlo dentro de 30 días."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: PERSONA.child})
    def post(self, request, pk):
        with transaction.atomic():
            amistad = solicitud_recibida(request, pk)
            amistad.estado, amistad.respondido = 'rechazada', timezone.now()
            amistad.save(update_fields=['estado', 'respondido'])
        return Response(persona(amistad.de, 'ninguna'))


class SolicitudView(APIView):
    """DELETE: cancela una solicitud que enviaste y sigue pendiente."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        get_object_or_404(Amistad, pk=pk, de=request.user, estado='pendiente').delete()
        return Response(status=204)


class AmigoView(APIView):
    """DELETE: deja de ser amigo de esta persona. No se le avisa."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None})
    def delete(self, request, username):
        otro = get_object_or_404(Usuario, username__iexact=username)
        amistad = amistad_entre(request.user, otro)
        if not amistad or amistad.estado != 'aceptada':
            raise Http404
        amistad.delete()
        return Response(status=204)


class BloqueosView(APIView):
    """POST {username}: bloquea. Elimina la amistad o solicitud que hubiera entre ustedes."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [BloqueoThrottle]

    @extend_schema(request=EnviarSolicitudSerializer, responses={201: PERSONA.child})
    def post(self, request):
        datos = EnviarSolicitudSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        yo = request.user
        # Se puede bloquear aunque la otra persona ya te haya bloqueado: así tampoco la ves si ella desbloquea.
        otro = get_object_or_404(Usuario, username__iexact=datos.validated_data['username'].lstrip('@'))
        if otro.pk == yo.pk:
            raise serializers.ValidationError('No puedes bloquearte a ti.')
        with transaction.atomic():
            Bloqueo.objects.get_or_create(de=yo, para=otro)
            Amistad.objects.filter(Q(de=yo, para=otro) | Q(de=otro, para=yo)).delete()
        return Response(persona(otro, 'bloqueado'), status=201)


class BloqueoView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None})
    def delete(self, request, username):
        Bloqueo.objects.filter(de=request.user, para__username__iexact=username).delete()
        return Response(status=204)


class PerfilPublicoView(APIView):
    """GET: el perfil de /u/<username>/. Sin permiso, solo el nombre y lo necesario para enviar la solicitud."""
    permission_classes = [AllowAny]

    @extend_schema(responses={200: inline_serializer('PerfilDePersona', fields={
        'username': serializers.CharField(), 'nombre': serializers.CharField(),
        'relacion': serializers.CharField(), 'solicitud': serializers.IntegerField(allow_null=True),
        'detalle': serializers.BooleanField(),
        'sellos': inline_serializer('SelloSinFecha', fields={
            'slug': serializers.SlugField(), 'nombre': serializers.CharField(), 'sello': serializers.BooleanField(),
        }, many=True, required=False),
        'lugares': inline_serializer('LugarVisitado', fields={
            'slug': serializers.SlugField(), 'nombre': serializers.CharField(),
        }, many=True, required=False),
        'amigos': PERSONA,
    })})
    def get(self, request, username):
        visitante = request.user if request.user.is_authenticated else None
        usuario = cuenta_de(username, visitante)
        rel = relacion(visitante, usuario)
        datos = {'solicitud': None, **persona(usuario, rel, visitante),
                 'detalle': puede_ver_detalle(visitante, usuario, rel)}
        if not datos['detalle']:
            return Response(datos)
        # Sin fechas, igual que el pasaporte compartido: no revela cuándo estuvo la persona en cada lugar.
        datos['sellos'] = [{'slug': s['slug'], 'nombre': s['nombre'], 'sello': s['sello']}
                           for s in sellos_de(usuario) if s['disponible']]
        visitas = VisitaComprobada.objects.filter(autor=usuario, destino__es_activo=True).select_related('destino')
        datos['lugares'] = sorted(({'slug': v.destino.slug, 'nombre': v.destino.nombre} for v in visitas),
                                  key=lambda lugar: lugar['nombre'])
        if usuario.mostrar_amigos or rel == 'yo':
            # Las cuentas privadas no aparecen en la lista de amigos de otros, ni quien bloqueó al visitante.
            amigos = [amigo for amigo in amigos_de(usuario).exclude(visibilidad='privado')
                      if amigo.username and (not visitante or not bloqueado(amigo, visitante))]
            datos['amigos'] = [persona(amigo) for amigo in amigos]
        return Response(datos)
