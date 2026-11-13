"""Recordatorios que dependen de la fecha. Los genera `enviar_avisos` en cada ejecución (cada 5 minutos).

Cada uno lleva una clave estable, así que correr el comando dos veces, o dos a la vez, no los duplica.
Los de escapada, pagos y cuentas solo se crean de día, para que el correo no llegue de madrugada;
--forzar ignora la hora.
"""
from datetime import timedelta

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from .bote import a_pesos, calcular_saldos
from .models import PagoEntreParticipantes, Viaje
from .notificar import avisar
from .viajes import pesos

DIAS_ANTES = 3
DIAS_PAGO_SIN_CONFIRMAR = 3
DIAS_PAGO_OLVIDADO = 60
DIAS_CUENTAS = 7
DIAS_RESENA = 14
HORAS_DE_DIA = range(8, 21)
HORAS_AGENDA = range(7, 13)
DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre']
AGENDA_VISIBLE = 3


def fecha_larga(fecha):
    return f'{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]}'


def enlace_viaje(viaje):
    return f'/mis-viajes/?abrir={viaje.pk}'


def enlace_bote(viaje, ancla=''):
    return f'/mis-viajes/{viaje.pk}/bote/' + (f'#{ancla}' if ancla else '')


def lista_corta(textos, maximo=2):
    resto = len(textos) - maximo
    return ', '.join(textos[:maximo]) + (f' y {resto} más' if resto > 0 else '')


def viajes_pronto(hoy):
    """«Tu escapada se acerca»: una vez por escapada y fecha, a quien organiza y a quienes están en su bote."""
    creados = 0
    viajes = (Viaje.objects.filter(fecha_inicio__gt=hoy, fecha_inicio__lte=hoy + timedelta(days=DIAS_ANTES),
                                   autor__es_activo=True)
              .select_related('autor').prefetch_related('participantes__usuario'))
    for viaje in viajes:
        faltan = (viaje.fecha_inicio - hoy).days
        cuando = f'empieza mañana, {fecha_larga(viaje.fecha_inicio)}' if faltan == 1 else \
            f'empieza en {faltan} días, el {fecha_larga(viaje.fecha_inicio)}'
        clave = f'viaje_pronto:{viaje.pk}:{viaje.fecha_inicio.isoformat()}'
        # Los pendientes son notas de quien organiza: solo se le mencionan a esa persona.
        pendientes = [p['texto'] for p in viaje.pendientes if isinstance(p, dict) and not p.get('hecho')]
        extra = (f' Te falta: {lista_corta(pendientes)}.' if pendientes
                 else ' Revisa tu agenda y tu presupuesto antes de salir.')
        creados += bool(avisar(viaje.autor, 'viaje_pronto', f'«{viaje.nombre}» {cuando}.{extra}',
                               enlace_viaje(viaje), clave=clave))
        for participante in viaje.participantes.all():
            if participante.usuario and participante.usuario_id != viaje.autor_id:
                creados += bool(avisar(
                    participante.usuario, 'viaje_pronto',
                    f'«{viaje.nombre}», la escapada de tu bote, {cuando}. Anota ahí lo que vayan gastando.',
                    enlace_bote(viaje), actor=viaje.autor, clave=clave))
    return creados


def actividades_del_dia(viaje, dia):
    return [a for a in viaje.actividades if isinstance(a, dict) and a.get('dia') == dia and a.get('titulo')]


def agenda_de_hoy(hoy):
    """«Hoy en tu escapada»: la alternativa web a «dirígete a tu próximo destino». Una vez al día, por la mañana."""
    creados = 0
    viajes = Viaje.objects.filter(fecha_inicio__lte=hoy, fecha_fin__gte=hoy, autor__es_activo=True) \
        .select_related('autor')
    for viaje in viajes:
        dia = (hoy - viaje.fecha_inicio).days + 1
        actividades = actividades_del_dia(viaje, dia)
        if not actividades:
            continue
        total = (viaje.fecha_fin - viaje.fecha_inicio).days + 1
        partes = [f"{a['hora']} {a['titulo']}" if a.get('hora') else a['titulo'] for a in actividades]
        cabeza = f'Hoy en «{viaje.nombre}»' + (f' (día {dia} de {total})' if total > 1 else '')
        texto = f'{cabeza}: primero, {lista_corta(partes, AGENDA_VISIBLE)}.'
        creados += bool(avisar(viaje.autor, 'viaje_hoy', texto, enlace_viaje(viaje),
                               clave=f'viaje_hoy:{viaje.pk}:{hoy.isoformat()}'))
    return creados


def cuentas_por_saldar(hoy):
    """Al terminar la escapada, a quien aún le toca pagar en el bote. Sin nombres: el bote dice a quién."""
    creados = 0
    viajes = (Viaje.objects.filter(fecha_fin__lt=hoy, fecha_fin__gte=hoy - timedelta(days=DIAS_CUENTAS))
              .annotate(n_gastos=Count('gastos_reales')).filter(n_gastos__gt=0))
    for viaje in viajes:
        participantes = list(viaje.participantes.select_related('usuario'))
        gastos = [(g.pagado_por_id, g.monto, [p.pk for p in g.entre.all()], g.pk)
                  for g in viaje.gastos_reales.prefetch_related('entre')]
        # También los pagos sin confirmar: quien ya registró que pagó no necesita el recordatorio.
        pagos = [(p.de_id, p.para_id, p.monto) for p in viaje.pagos_entre.all()]
        saldos = calcular_saldos([p.pk for p in participantes], gastos, pagos)
        for participante in participantes:
            debe = -saldos[participante.pk]
            if participante.usuario and debe >= 100:
                creados += bool(avisar(
                    participante.usuario, 'cuentas',
                    f'«{viaje.nombre}» terminó y te quedan ${a_pesos(debe)} por pagar en el bote. '
                    'Ahí ves a quién y registras el pago con un toque.',
                    enlace_bote(viaje, 'cuentas'), clave=f'cuentas:{viaje.pk}'))
    return creados


def pagos_sin_confirmar(ahora):
    """Un recordatorio a quien recibió un pago que lleva días sin confirmar; nunca vuelve a repetirse."""
    creados = 0
    pagos = (PagoEntreParticipantes.objects
             .filter(confirmado=False, creado__lte=ahora - timedelta(days=DIAS_PAGO_SIN_CONFIRMAR),
                     creado__gte=ahora - timedelta(days=DIAS_PAGO_OLVIDADO), para__usuario__isnull=False)
             .select_related('viaje', 'para__usuario', 'de__usuario'))
    for pago in pagos:
        creados += bool(avisar(
            pago.para.usuario, 'pago',
            f'Tienes un pago de ${pesos(pago.monto)} sin confirmar en el bote de {pago.viaje.nombre}. '
            'Si ya te llegó, confírmalo para que las cuentas cuadren.',
            enlace_bote(pago.viaje, 'cuentas'), actor=pago.de.usuario, clave=f'pago_recordatorio:{pago.pk}'))
    return creados


def resenas_tras_viaje(hoy):
    """Invita a contar cómo le fue a quien terminó una escapada en las últimas dos semanas, una sola vez."""
    creados = 0
    viajes = (Viaje.objects.filter(fecha_fin__lt=hoy, fecha_fin__gte=hoy - timedelta(days=DIAS_RESENA),
                                   recordatorio_enviado__isnull=True, autor__es_activo=True)
              .select_related('autor').prefetch_related('lugares'))
    for viaje in viajes:
        lugar = next((destino for destino in viaje.lugares.all() if destino.es_activo), None)
        enlace = reverse('destino-detalle', kwargs={'slug': lugar.slug}) if lugar else reverse('mis-viajes')
        creados += bool(avisar(
            viaje.autor, 'viaje_resena',
            f'¿Cómo te fue en «{viaje.nombre}»? Tu reseña o confirmar un dato ayuda al siguiente viajero.',
            enlace, clave=f'viaje_resena:{viaje.pk}'))
        viaje.recordatorio_enviado = timezone.now()
        viaje.save(update_fields=['recordatorio_enviado'])
    return creados


def generar(ahora=None, forzar=False):
    """Crea los recordatorios que tocan ahora. Devuelve {tipo: avisos nuevos}."""
    ahora = timezone.localtime(ahora)
    hoy = ahora.date()
    creados = {'viaje_resena': resenas_tras_viaje(hoy)}
    if forzar or ahora.hour in HORAS_DE_DIA:
        creados['pago'] = pagos_sin_confirmar(ahora)
        creados['viaje_pronto'] = viajes_pronto(hoy)
        creados['cuentas'] = cuentas_por_saldar(hoy)
    if forzar or ahora.hour in HORAS_AGENDA:
        creados['viaje_hoy'] = agenda_de_hoy(hoy)
    return creados
