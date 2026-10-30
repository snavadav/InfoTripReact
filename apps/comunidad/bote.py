"""Bote de la escapada: quienes viajan juntos anotan lo que gastaron y se calcula quién le debe a quién.

Solo lo ven las personas que se unieron con la invitación. Al terminar, quien organiza puede publicar los
gastos como aportes sin nombre, que alimentan "¿Cuánto cuesta ir a…?" tras pasar por moderación.
"""
import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Count
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
from .models import Aporte, GastoReal, Notificacion, Participante, Viaje
from .views import AporteThrottle
from .viajes import pesos

LIMITE_PARTICIPANTES = 50
LIMITE_GASTOS = 300
# Texto fijo: la descripción del gasto puede nombrar a alguien del grupo y aquí se publica sin nombres.
TEXTO_PUBLICADO = 'Gasto real registrado en una escapada en grupo.'


class GastoBoteThrottle(UserRateThrottle):
    rate = '200/hour'
    scope = 'gastos_bote'


def a_centavos(monto):
    return int((monto * 100).to_integral_value(rounding=ROUND_HALF_UP))


def a_pesos(centavos):
    return pesos(Decimal(centavos) / 100)


def repartir(centavos, personas):
    """Partes iguales que suman exacto: los centavos que sobran van a los primeros."""
    base, sobrante = divmod(centavos, personas)
    return [base + (1 if indice < sobrante else 0) for indice in range(personas)]


def calcular_saldos(participantes, gastos):
    """{participante: centavos}. Positivo: le deben; negativo: debe. Siempre suman cero."""
    saldos = dict.fromkeys(participantes, 0)
    for pagado_por, monto, entre in gastos:
        centavos = a_centavos(monto)
        saldos[pagado_por] += centavos
        for participante, parte in zip(sorted(entre), repartir(centavos, len(entre))):
            saldos[participante] -= parte
    return saldos


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
    puede_editar = serializers.SerializerMethodField()
    publicado = serializers.SerializerMethodField()

    class Meta:
        model = GastoReal
        fields = ['id', 'descripcion', 'concepto', 'monto', 'fecha', 'destino', 'noches', 'pagado_por', 'entre',
                  'puede_editar', 'publicado']

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
        if valor('concepto') != 'alojamiento' and (valor('noches') or 1) > 1:
            raise serializers.ValidationError({'noches': 'Las noches solo aplican al alojamiento.'})
        return attrs


class EstadoBoteSerializer(serializers.Serializer):
    """Describe la respuesta en el esquema de la API."""
    id = serializers.IntegerField()
    nombre = serializers.CharField()
    destino = serializers.CharField()
    es_organizador = serializers.BooleanField()
    enlace_invitacion = serializers.UUIDField(allow_null=True)
    total = serializers.CharField()
    participantes = inline_serializer('ParticipanteDeBote', fields={
        'id': serializers.IntegerField(), 'nombre': serializers.CharField(), 'es_yo': serializers.BooleanField(),
        'es_organizador': serializers.BooleanField(), 'saldo': serializers.CharField(),
    }, many=True)
    gastos = GastoRealSerializer(many=True)
    transferencias = inline_serializer('TransferenciaDeBote', fields={
        'de': serializers.CharField(), 'a': serializers.CharField(), 'monto': serializers.CharField(),
    }, many=True)
    lugares = inline_serializer('LugarDeBote', fields={
        'id': serializers.IntegerField(), 'nombre': serializers.CharField(),
    }, many=True)


def estado_del_bote(viaje, request):
    participantes = list(viaje.participantes.select_related('usuario'))
    gastos = list(viaje.gastos_reales.prefetch_related('entre').order_by('-fecha', '-pk'))
    saldos = calcular_saldos([p.pk for p in participantes],
                             [(g.pagado_por_id, g.monto, [p.pk for p in g.entre.all()]) for g in gastos])
    nombres = {p.pk: p.nombre for p in participantes}
    contexto = {'request': request, 'viaje': viaje}
    es_organizador = viaje.autor_id == request.user.pk
    return {
        'id': viaje.pk, 'nombre': viaje.nombre, 'destino': viaje.destino, 'es_organizador': es_organizador,
        'enlace_invitacion': viaje.enlace_bote if es_organizador else None,
        'total': pesos(sum((g.monto for g in gastos), Decimal('0'))),
        'participantes': [{
            'id': p.pk, 'nombre': p.nombre, 'es_yo': p.usuario_id == request.user.pk,
            'es_organizador': p.usuario_id == viaje.autor_id, 'saldo': a_pesos(saldos[p.pk]),
        } for p in participantes],
        'gastos': GastoRealSerializer(gastos, many=True, context=contexto).data,
        'transferencias': [{'de': nombres[de], 'a': nombres[a], 'monto': a_pesos(monto)}
                           for de, a, monto in calcular_transferencias(saldos)],
        'lugares': [{'id': lugar.pk, 'nombre': lugar.nombre} for lugar in viaje.lugares.all() if lugar.es_activo],
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


def unirse_al_bote(request, enlace):
    """Invitación: muestra solo el nombre de la escapada y de quien invita, nunca importes."""
    viaje = get_object_or_404(Viaje.objects.select_related('autor'), enlace_bote=enlace, autor__es_activo=True)
    return render(request, 'comunidad/bote_unirse.html', {'viaje': viaje})
