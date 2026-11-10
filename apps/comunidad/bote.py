"""Bote de la escapada: quienes viajan juntos anotan lo que gastaron y se calcula quién le debe a quién.

Solo lo ven las personas que se unieron con la invitación. Al terminar, quien organiza puede publicar los
gastos como aportes sin nombre, que alimentan "¿Cuánto cuesta ir a…?" tras pasar por moderación.
"""
import uuid
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.metricas.models import registrar
from apps.amigos.relaciones import amigos_de
from apps.destinos.models import Lugar
from .models import Aporte, GastoReal, Notificacion, PagoEntreParticipantes, Participante, Viaje
from .views import AporteThrottle
from .viajes import pesos

LIMITE_PARTICIPANTES = 50
LIMITE_GASTOS = 300
# Unos 15 km alrededor de cada lugar de la escapada para buscar dónde se pagó.
RADIO_GRADOS = Decimal('0.15')
# Texto fijo: la descripción del gasto puede nombrar a alguien del grupo y aquí se publica sin nombres.
TEXTO_PUBLICADO = 'Gasto real registrado en una escapada en grupo.'


class GastoBoteThrottle(UserRateThrottle):
    rate = '200/hour'
    scope = 'gastos_bote'


def a_centavos(monto):
    return int((monto * 100).to_integral_value(rounding=ROUND_HALF_UP))


def a_pesos(centavos):
    return pesos(Decimal(centavos) / 100)


def repartir(centavos, personas, inicio=0):
    """Partes iguales que suman exacto. Los centavos que sobran van a los primeros a partir de `inicio`."""
    base, sobrante = divmod(centavos, personas)
    return [base + (1 if (indice - inicio) % personas < sobrante else 0) for indice in range(personas)]


def calcular_cuentas(participantes, gastos, pagos=()):
    """{participante: {pago, le_tocaba, enviados, recibidos, diferencia}} en centavos.

    `gastos`: (pagado_por, monto, entre[, id del gasto]). Con el id, el centavo que sobra rota entre las personas
    de un gasto a otro; sin rotar, lo pagaba siempre quien tiene el primer id, casi siempre quien organiza.
    `pagos`: (de, para, monto) ya confirmados por quien recibe. Diferencia positiva: le deben; negativa: debe.
    """
    cuentas = {persona: {'pago': 0, 'le_tocaba': 0, 'enviados': 0, 'recibidos': 0} for persona in participantes}
    for pagado_por, monto, entre, *gasto in gastos:
        centavos = a_centavos(monto)
        cuentas[pagado_por]['pago'] += centavos
        inicio = gasto[0] % len(entre) if gasto else 0
        for participante, parte in zip(sorted(entre), repartir(centavos, len(entre), inicio)):
            cuentas[participante]['le_tocaba'] += parte
    for de, para, monto in pagos:
        centavos = a_centavos(monto)
        cuentas[de]['enviados'] += centavos
        cuentas[para]['recibidos'] += centavos
    for cuenta in cuentas.values():
        cuenta['diferencia'] = cuenta['pago'] - cuenta['le_tocaba'] + cuenta['enviados'] - cuenta['recibidos']
    return cuentas


def calcular_saldos(participantes, gastos, pagos=()):
    """{participante: centavos}. Positivo: le deben; negativo: debe. Siempre suman cero."""
    return {persona: cuenta['diferencia'] for persona, cuenta in calcular_cuentas(participantes, gastos, pagos).items()}


def calcular_transferencias(saldos):
    """Pocos pagos para saldar: cada vez, quien más debe le paga a quien más le deben."""
    deudores = sorted(([-saldo, clave] for clave, saldo in saldos.items() if saldo < 0), key=lambda f: (-f[0], f[1]))
    acreedores = sorted(([saldo, clave] for clave, saldo in saldos.items() if saldo > 0), key=lambda f: (-f[0], f[1]))
    pagos = []
    while deudores and acreedores:
        monto = min(deudores[0][0], acreedores[0][0])
        pagos.append((deudores[0][1], acreedores[0][1], monto))
        deudores[0][0] -= monto
        acreedores[0][0] -= monto
        if not deudores[0][0]:
            deudores.pop(0)
        if not acreedores[0][0]:
            acreedores.pop(0)
    return pagos


def monto_de_aporte(gasto):
    """Los aportes son por persona o, el alojamiento, por noche: así se comparan con los de otros viajeros."""
    divisor = gasto.noches if gasto.concepto == 'alojamiento' else gasto.entre.count()
    return (gasto.monto / divisor).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


class GastoRealSerializer(serializers.ModelSerializer):
    entre = serializers.PrimaryKeyRelatedField(many=True, allow_empty=False, queryset=Participante.objects.all())
    descripcion = serializers.CharField(max_length=120, required=False, allow_blank=True)
    lugar = serializers.PrimaryKeyRelatedField(queryset=Lugar.objects.all(), required=False, allow_null=True)
    lugar_nombre = serializers.SerializerMethodField()
    puede_editar = serializers.SerializerMethodField()
    publicado = serializers.SerializerMethodField()

    class Meta:
        model = GastoReal
        fields = ['id', 'descripcion', 'concepto', 'monto', 'fecha', 'destino', 'lugar', 'lugar_nombre', 'noches',
                  'pagado_por', 'entre', 'puede_editar', 'publicado']

    def get_lugar_nombre(self, gasto) -> str:
        return gasto.lugar.nombre if gasto.lugar else ''

    def get_puede_editar(self, gasto) -> bool:
        usuario = self.context['request'].user
        return gasto.registrado_por_id == usuario.pk or self.context['viaje'].autor_id == usuario.pk

    def get_publicado(self, gasto) -> bool:
        return gasto.aporte_id is not None

    def validate(self, attrs):
        viaje = self.context['viaje']
        def valor(campo):
            return attrs.get(campo, getattr(self.instance, campo, None))
        if 'pagado_por' in attrs and attrs['pagado_por'].viaje_id != viaje.pk:
            raise serializers.ValidationError({'pagado_por': 'Selecciona a alguien de este bote.'})
        if any(persona.viaje_id != viaje.pk for persona in attrs.get('entre', [])):
            raise serializers.ValidationError({'entre': 'Selecciona solo a personas de este bote.'})
        if attrs.get('fecha') and attrs['fecha'] > timezone.localdate():
            raise serializers.ValidationError({'fecha': 'Anota solo lo que ya se gastó.'})
        if attrs.get('destino') and not viaje.lugares.filter(pk=attrs['destino'].pk, es_activo=True).exists():
            raise serializers.ValidationError({'destino': 'Selecciona un lugar de esta escapada.'})
        if attrs.get('lugar') and not attrs['lugar'].es_activo:
            raise serializers.ValidationError({'lugar': 'Ese establecimiento ya no está en el catálogo.'})
        if valor('concepto') != 'alojamiento' and (valor('noches') or 1) > 1:
            raise serializers.ValidationError({'noches': 'Las noches solo aplican al alojamiento.'})
        if 'descripcion' in attrs or not self.instance:
            # Sin descripción basta el establecimiento: "Pagué 450 en la fonda".
            lugar = valor('lugar')
            descripcion = (attrs.get('descripcion') or '').strip() or (lugar.nombre[:120] if lugar else '')
            if not descripcion:
                raise serializers.ValidationError({'descripcion': 'Escribe en qué se gastó o elige dónde.'})
            attrs['descripcion'] = descripcion
        return attrs


class PagoSerializer(serializers.ModelSerializer):
    """Para registrar "Ya pagué": quien paga es siempre la persona que lo anota."""
    fecha = serializers.DateField(required=False)

    class Meta:
        model = PagoEntreParticipantes
        fields = ['para', 'monto', 'fecha']

    def validate(self, attrs):
        if attrs['para'].viaje_id != self.context['viaje'].pk:
            raise serializers.ValidationError({'para': 'Selecciona a alguien de este bote.'})
        if attrs['para'].pk == self.context['yo'].pk:
            raise serializers.ValidationError({'para': 'No puedes pagarte a ti.'})
        if attrs.get('fecha') and attrs['fecha'] > timezone.localdate():
            raise serializers.ValidationError({'fecha': 'Anota solo lo que ya pagaste.'})
        return attrs


class EstadoBoteSerializer(serializers.Serializer):
    """Describe la respuesta en el esquema de la API."""
    id = serializers.IntegerField()
    nombre = serializers.CharField()
    destino = serializers.CharField()
    es_organizador = serializers.BooleanField()
    enlace_invitacion = serializers.UUIDField(allow_null=True)
    total = serializers.CharField()
    yo = serializers.IntegerField()
    a_mano = serializers.BooleanField()
    participantes = inline_serializer('ParticipanteDeBote', fields={
        'id': serializers.IntegerField(), 'nombre': serializers.CharField(),
        'username': serializers.CharField(allow_null=True), 'es_yo': serializers.BooleanField(),
        'es_organizador': serializers.BooleanField(), 'pago': serializers.CharField(),
        'le_tocaba': serializers.CharField(), 'enviados': serializers.CharField(),
        'recibidos': serializers.CharField(), 'saldo': serializers.CharField(),
        'puede_salir': serializers.BooleanField(),
    }, many=True)
    gastos = GastoRealSerializer(many=True)
    transferencias = inline_serializer('TransferenciaDeBote', fields={
        'de': serializers.CharField(), 'a': serializers.CharField(), 'de_id': serializers.IntegerField(),
        'a_id': serializers.IntegerField(), 'monto': serializers.CharField(),
        'pendiente': serializers.IntegerField(allow_null=True),
    }, many=True)
    pagos = inline_serializer('PagoDeBote', fields={
        'id': serializers.IntegerField(), 'de': serializers.CharField(), 'a': serializers.CharField(),
        'de_id': serializers.IntegerField(), 'a_id': serializers.IntegerField(), 'monto': serializers.CharField(),
        'fecha': serializers.DateField(), 'confirmado': serializers.BooleanField(),
        'puede_confirmar': serializers.BooleanField(), 'puede_cancelar': serializers.BooleanField(),
    }, many=True)
    lugares = inline_serializer('LugarDeBote', fields={
        'id': serializers.IntegerField(), 'nombre': serializers.CharField(),
    }, many=True)
    amigos_invitables = inline_serializer('AmigoInvitable', fields={
        'username': serializers.CharField(), 'nombre': serializers.CharField(),
    }, many=True)


def nombres_visibles(participantes):
    """{id: nombre} sin repetidos: dos "Ana" se distinguen por la inicial del apellido y, si no basta, por número."""
    repetidos = Counter(p.nombre for p in participantes)
    nombres = {p.pk: f'{p.nombre} {p.usuario.apellido[:1]}.' if repetidos[p.nombre] > 1 and p.usuario
               and p.usuario.apellido else p.nombre for p in participantes}
    repetidos, vistos = Counter(nombres.values()), Counter()
    for p in participantes:
        nombre = nombres[p.pk]
        if repetidos[nombre] > 1:
            vistos[nombre] += 1
            nombres[p.pk] = f'{nombre} ({vistos[nombre]})'
    return nombres


def amigos_invitables(viaje, usuario):
    """Amigos aceptados de quien organiza que aún no están en el bote."""
    dentro = viaje.participantes.exclude(usuario=None).values_list('usuario_id', flat=True)
    return amigos_de(usuario).exclude(pk__in=dentro).exclude(username=None)


def estado_del_bote(viaje, request):
    participantes = list(viaje.participantes.select_related('usuario')
                         .annotate(gastos_pagados=Count('pagados', distinct=True),
                                   gastos_compartidos=Count('compartidos', distinct=True),
                                   pagos_enviados_n=Count('pagos_enviados', distinct=True),
                                   pagos_recibidos_n=Count('pagos_recibidos', distinct=True)))
    gastos = list(viaje.gastos_reales.select_related('lugar').prefetch_related('entre').order_by('-fecha', '-pk'))
    pagos = list(viaje.pagos_entre.all())
    cuentas = calcular_cuentas([p.pk for p in participantes],
                               [(g.pagado_por_id, g.monto, [p.pk for p in g.entre.all()], g.pk) for g in gastos],
                               [(pago.de_id, pago.para_id, pago.monto) for pago in pagos if pago.confirmado])
    saldos = {persona: cuenta['diferencia'] for persona, cuenta in cuentas.items()}
    nombres = nombres_visibles(participantes)
    yo = next(p for p in participantes if p.usuario_id == request.user.pk)
    pendientes = {(pago.de_id, pago.para_id): pago.pk for pago in pagos if not pago.confirmado}
    contexto = {'request': request, 'viaje': viaje}
    es_organizador = viaje.autor_id == request.user.pk
    return {
        'id': viaje.pk, 'nombre': viaje.nombre, 'destino': viaje.destino, 'es_organizador': es_organizador,
        'enlace_invitacion': viaje.enlace_bote if es_organizador else None,
        'total': pesos(sum((g.monto for g in gastos), Decimal('0'))),
        'yo': yo.pk,
        # Exacto, en centavos: con un centavo pendiente todavía no quedaron a mano.
        'a_mano': all(saldo == 0 for saldo in saldos.values()),
        'participantes': [{
            'id': p.pk, 'nombre': nombres[p.pk], 'username': p.usuario.username if p.usuario else None,
            'es_yo': p.pk == yo.pk, 'es_organizador': p.usuario_id == viaje.autor_id,
            **{campo: a_pesos(cuentas[p.pk][campo]) for campo in ('pago', 'le_tocaba', 'enviados', 'recibidos')},
            'saldo': a_pesos(saldos[p.pk]),
            # Con gastos o pagos no puede salir: las cuentas dejarían de cuadrar.
            'puede_salir': (p.usuario_id != viaje.autor_id and not p.gastos_pagados and not p.gastos_compartidos
                            and not p.pagos_enviados_n and not p.pagos_recibidos_n
                            and request.user.pk in (p.usuario_id, viaje.autor_id)),
        } for p in participantes],
        'gastos': GastoRealSerializer(gastos, many=True, context=contexto).data,
        'transferencias': [{'de': nombres[de], 'a': nombres[a], 'de_id': de, 'a_id': a, 'monto': a_pesos(monto),
                            'pendiente': pendientes.get((de, a))}
                           for de, a, monto in calcular_transferencias(saldos)],
        'pagos': [{
            'id': pago.pk, 'de': nombres[pago.de_id], 'a': nombres[pago.para_id], 'de_id': pago.de_id,
            'a_id': pago.para_id, 'monto': pesos(pago.monto), 'fecha': pago.fecha, 'confirmado': pago.confirmado,
            'puede_confirmar': not pago.confirmado and pago.para_id == yo.pk,
            'puede_cancelar': not pago.confirmado and pago.de_id == yo.pk,
        } for pago in pagos],
        'lugares': [{'id': lugar.pk, 'nombre': lugar.nombre} for lugar in viaje.lugares.all() if lugar.es_activo],
        'amigos_invitables': [{'username': amigo.username, 'nombre': amigo.nombre_completo}
                              for amigo in amigos_invitables(viaje, request.user)] if es_organizador else [],
    }


def bote_de(request, pk):
    """El viaje si la persona participa en su bote; para cualquier otra, no existe."""
    return get_object_or_404(Viaje, pk=pk, participantes__usuario=request.user)


class BoteView(APIView):
    """GET: estado del bote. POST: quien organiza lo abre y obtiene la invitación. DELETE: deja de invitar."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: EstadoBoteSerializer})
    def get(self, request, pk):
        return Response(estado_del_bote(bote_de(request, pk), request))

    @extend_schema(request=None, responses={200: EstadoBoteSerializer})
    def post(self, request, pk):
        with transaction.atomic():
            viaje = get_object_or_404(Viaje.objects.select_for_update(), pk=pk, autor=request.user)
            _, creado = Participante.objects.get_or_create(viaje=viaje, usuario=request.user)
            if not viaje.enlace_bote:
                viaje.enlace_bote = uuid.uuid4()
                viaje.save(update_fields=['enlace_bote'])
            if creado:
                registrar('bote_creado', usuario=request.user)
        return Response(estado_del_bote(viaje, request))

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        Viaje.objects.filter(pk=pk, autor=request.user).update(enlace_bote=None)
        return Response(status=204)


class UnirseBoteView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AporteThrottle]

    @extend_schema(request=None, responses={200: inline_serializer('BoteUnido', fields={
        'viaje': serializers.IntegerField(),
    })})
    def post(self, request, enlace):
        with transaction.atomic():
            viaje = get_object_or_404(Viaje.objects.select_for_update(), enlace_bote=enlace, autor__es_activo=True)
            if viaje.participantes.filter(usuario=request.user).exists():
                return Response({'viaje': viaje.pk})
            if viaje.participantes.count() >= LIMITE_PARTICIPANTES:
                raise serializers.ValidationError(f'Este bote ya tiene {LIMITE_PARTICIPANTES} personas.')
            Participante.objects.create(viaje=viaje, usuario=request.user)
            Notificacion.objects.create(usuario=viaje.autor, enlace=f'/mis-viajes/{viaje.pk}/bote/',
                                        texto=f'{request.user.nombre} se unió al bote de {viaje.nombre}.'[:300])
            registrar('bote_unido', usuario=request.user)
        return Response({'viaje': viaje.pk})


class MisBotesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: inline_serializer('BoteResumido', fields={
        'id': serializers.IntegerField(), 'nombre': serializers.CharField(), 'destino': serializers.CharField(),
        'personas': serializers.IntegerField(), 'es_organizador': serializers.BooleanField(),
    }, many=True)})
    def get(self, request):
        # Con pk__in: filtrar por la misma relación que se cuenta contaría solo a quien pregunta.
        mios = Participante.objects.filter(usuario=request.user).values('viaje')
        viajes = Viaje.objects.filter(pk__in=mios).annotate(personas_bote=Count('participantes'))[:100]
        return Response([{'id': viaje.pk, 'nombre': viaje.nombre, 'destino': viaje.destino,
                          'personas': viaje.personas_bote, 'es_organizador': viaje.autor_id == request.user.pk}
                         for viaje in viajes])


class GastosBoteView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [GastoBoteThrottle]

    @extend_schema(request=GastoRealSerializer, responses={201: GastoRealSerializer})
    def post(self, request, pk):
        viaje = bote_de(request, pk)
        if viaje.gastos_reales.count() >= LIMITE_GASTOS:
            raise serializers.ValidationError(f'Un bote admite hasta {LIMITE_GASTOS} gastos.')
        datos = GastoRealSerializer(data=request.data, context={'request': request, 'viaje': viaje})
        datos.is_valid(raise_exception=True)
        datos.save(viaje=viaje, registrado_por=request.user)
        return Response(datos.data, status=201)


class GastoBoteView(APIView):
    """PATCH y DELETE: quien lo anotó o quien organiza. Lo ya publicado se retira aparte, desde Mi perfil."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [GastoBoteThrottle]

    def editable(self, request, pk, gasto):
        viaje = bote_de(request, pk)
        registro = get_object_or_404(viaje.gastos_reales, pk=gasto)
        if request.user.pk not in (registro.registrado_por_id, viaje.autor_id):
            raise PermissionDenied('Solo quien anotó el gasto o quien organiza puede cambiarlo.')
        return viaje, registro

    @extend_schema(request=GastoRealSerializer, responses={200: GastoRealSerializer})
    def patch(self, request, pk, gasto):
        viaje, registro = self.editable(request, pk, gasto)
        datos = GastoRealSerializer(registro, data=request.data, partial=True,
                                    context={'request': request, 'viaje': viaje})
        datos.is_valid(raise_exception=True)
        datos.save()
        return Response(datos.data)

    @extend_schema(responses={204: None})
    def delete(self, request, pk, gasto):
        self.editable(request, pk, gasto)[1].delete()
        return Response(status=204)


class ParticipanteBoteView(APIView):
    """DELETE: salir del bote o, si organizas, quitar a alguien. Con gastos no se puede: las cuentas no cuadrarían."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None})
    def delete(self, request, pk, participante):
        viaje = bote_de(request, pk)
        persona = get_object_or_404(viaje.participantes, pk=participante)
        if request.user.pk not in (persona.usuario_id, viaje.autor_id):
            raise PermissionDenied('Solo quien organiza puede quitar a otra persona.')
        if persona.usuario_id == viaje.autor_id:
            raise serializers.ValidationError('Quien organiza no puede salir del bote.')
        if persona.pagados.exists() or persona.compartidos.exists():
            raise serializers.ValidationError('Primero quita a esta persona de los gastos en los que aparece.')
        if persona.pagos_enviados.exists() or persona.pagos_recibidos.exists():
            raise serializers.ValidationError('Esta persona ya tiene pagos registrados en el bote.')
        persona.delete()
        return Response(status=204)


class PublicarBoteView(APIView):
    """POST: envía a revisión los gastos aún sin publicar, sin nombres. Repetirlo no los duplica."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [AporteThrottle]

    @extend_schema(request=None, responses={200: inline_serializer('BotePublicado', fields={
        'publicados': serializers.IntegerField(), 'omitidos': serializers.IntegerField(),
    })})
    def post(self, request, pk):
        publicados = omitidos = 0
        with transaction.atomic():
            viaje = get_object_or_404(Viaje.objects.select_for_update(), pk=pk, autor=request.user)
            for gasto in viaje.gastos_reales.filter(aporte=None).select_related('destino'):
                # Sin un lugar del catálogo no hay dónde mostrarlo; "otros" no es comparable entre viajeros.
                if gasto.concepto == 'otros' or not gasto.destino or not gasto.destino.es_activo:
                    omitidos += 1
                    continue
                gasto.aporte = Aporte.objects.create(
                    destino=gasto.destino, autor=request.user, tipo='gasto', texto=TEXTO_PUBLICADO,
                    fecha_visita=gasto.fecha, monto=monto_de_aporte(gasto), concepto=gasto.concepto, anonimo=True,
                )
                gasto.save(update_fields=['aporte'])
                registrar('gasto_real_publicado', usuario=request.user, destino=gasto.destino.slug)
                publicados += 1
        return Response({'publicados': publicados, 'omitidos': omitidos})


def quien(usuario):
    return f'@{usuario.username}' if usuario.username else usuario.nombre


def mi_participacion(viaje, request):
    return get_object_or_404(viaje.participantes, usuario=request.user)


class PagoBoteThrottle(UserRateThrottle):
    rate = '60/hour'
    scope = 'pagos_bote'


class PagosBoteView(APIView):
    """POST: "Ya pagué". Quien recibe lo confirma y solo entonces cuenta en los saldos."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [PagoBoteThrottle]

    @extend_schema(request=PagoSerializer, responses={201: EstadoBoteSerializer})
    def post(self, request, pk):
        viaje = bote_de(request, pk)
        yo = mi_participacion(viaje, request)
        if viaje.pagos_entre.count() >= LIMITE_GASTOS:
            raise serializers.ValidationError(f'Un bote admite hasta {LIMITE_GASTOS} pagos.')
        datos = PagoSerializer(data=request.data, context={'viaje': viaje, 'yo': yo})
        datos.is_valid(raise_exception=True)
        pago = datos.save(viaje=viaje, de=yo, fecha=datos.validated_data.get('fecha') or timezone.localdate())
        if pago.para.usuario:
            Notificacion.objects.create(
                usuario=pago.para.usuario, enlace=f'/mis-viajes/{viaje.pk}/bote/#cuentas',
                texto=f'{quien(request.user)} registró que te pagó ${pesos(pago.monto)} en el bote de '
                      f'{viaje.nombre}. Confírmalo cuando lo recibas.'[:300])
        registrar('pago_bote_registrado', usuario=request.user)
        return Response(estado_del_bote(viaje, request), status=201)


class PagoBoteView(APIView):
    """DELETE: quien lo registró lo cancela mientras no esté confirmado."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: EstadoBoteSerializer})
    def delete(self, request, pk, pago):
        viaje = bote_de(request, pk)
        registro = get_object_or_404(viaje.pagos_entre, pk=pago, de__usuario=request.user)
        if registro.confirmado:
            raise serializers.ValidationError('Este pago ya se confirmó: quien lo recibió ya lo cuenta.')
        registro.delete()
        return Response(estado_del_bote(viaje, request))


class ConfirmarPagoView(APIView):
    """POST: quien recibe confirma que le llegó el dinero."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: EstadoBoteSerializer})
    def post(self, request, pk, pago):
        viaje = bote_de(request, pk)
        with transaction.atomic():
            # of=('self',): en PostgreSQL no se puede bloquear el lado nulo del LEFT JOIN a de__usuario
            # (las cuentas eliminadas dejan usuario=None); basta con bloquear el pago.
            registro = get_object_or_404(
                viaje.pagos_entre.select_for_update(of=('self',)).select_related('de__usuario'),
                pk=pago, para__usuario=request.user)
            if not registro.confirmado:
                registro.confirmado = True
                registro.save(update_fields=['confirmado'])
                if registro.de.usuario:
                    Notificacion.objects.create(
                        usuario=registro.de.usuario, enlace=f'/mis-viajes/{viaje.pk}/bote/#cuentas',
                        texto=f'{quien(request.user)} confirmó que recibió tu pago de ${pesos(registro.monto)} '
                              f'en el bote de {viaje.nombre}.'[:300])
        estado = estado_del_bote(viaje, request)
        if estado['a_mano']:
            registrar('bote_a_mano', usuario=request.user)
        return Response(estado)


class InvitarAmigosSerializer(serializers.Serializer):
    usernames = serializers.ListField(child=serializers.CharField(max_length=40), allow_empty=False,
                                      max_length=LIMITE_PARTICIPANTES)


class InvitarAmigosView(APIView):
    """POST {usernames}: quien organiza agrega al bote a amigos aceptados. Funciona con cualquier escapada."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [AporteThrottle]

    @extend_schema(request=InvitarAmigosSerializer, responses={200: EstadoBoteSerializer})
    def post(self, request, pk):
        datos = InvitarAmigosSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        pedidos = {nombre.strip().lstrip('@').lower() for nombre in datos.validated_data['usernames']}
        with transaction.atomic():
            viaje = get_object_or_404(Viaje.objects.select_for_update(), pk=pk, autor=request.user)
            Participante.objects.get_or_create(viaje=viaje, usuario=request.user)
            amigos = list(amigos_invitables(viaje, request.user).filter(username__in=pedidos))
            if len(amigos) != len(pedidos - {quien_ya.usuario.username for quien_ya in
                                               viaje.participantes.select_related('usuario') if quien_ya.usuario}):
                raise serializers.ValidationError({'usernames': 'Solo puedes agregar a tus amigos.'})
            if viaje.participantes.count() + len(amigos) > LIMITE_PARTICIPANTES:
                raise serializers.ValidationError(f'Un bote admite hasta {LIMITE_PARTICIPANTES} personas.')
            for amigo in amigos:
                Participante.objects.create(viaje=viaje, usuario=amigo)
                Notificacion.objects.create(
                    usuario=amigo, enlace=f'/mis-viajes/{viaje.pk}/bote/',
                    texto=f'{quien(request.user)} te agregó al bote de {viaje.nombre}. '
                          'Si no vas, puedes salirte desde el bote.'[:300])
            if amigos:
                registrar('bote_amigos_invitados', usuario=request.user)
        return Response(estado_del_bote(viaje, request))


class LugaresBoteView(APIView):
    """GET ?q=: establecimientos del catálogo por nombre para el "Dónde" de un gasto, cerca de la escapada."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: inline_serializer('EstablecimientoDeBote', fields={
        'id': serializers.IntegerField(), 'nombre': serializers.CharField(), 'tipo': serializers.CharField(),
        'municipio': serializers.CharField(),
    }, many=True)})
    def get(self, request, pk):
        viaje = bote_de(request, pk)
        texto = (request.query_params.get('q') or '').strip()[:60]
        if len(texto) < 2:
            return Response([])
        lugares = Lugar.objects.filter(es_activo=True, nombre__icontains=texto).select_related('municipio')
        cerca = Q()
        for destino in viaje.lugares.filter(es_activo=True):
            cerca |= Q(latitud__range=(destino.latitud - RADIO_GRADOS, destino.latitud + RADIO_GRADOS),
                       longitud__range=(destino.longitud - RADIO_GRADOS, destino.longitud + RADIO_GRADOS))
        if cerca:
            lugares = lugares.filter(cerca)
        return Response([{'id': lugar.pk, 'nombre': lugar.nombre, 'tipo': lugar.get_subtipo_display(),
                          'municipio': lugar.municipio.nombre if lugar.municipio else ''}
                         for lugar in lugares.order_by('nombre', 'pk')[:10]])


def unirse_al_bote(request, enlace):
    """Invitación: muestra solo el nombre de la escapada y de quien invita, nunca importes."""
    viaje = get_object_or_404(Viaje.objects.select_related('autor'), enlace_bote=enlace, autor__es_activo=True)
    return render(request, 'comunidad/bote_unirse.html', {'viaje': viaje})
