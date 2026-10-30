"""Moderación de contenido comunitario (aportes y colaboraciones) con una sola regla."""
import logging
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from apps.core.geo import distancia_km
from apps.destinos.models import Destino, Lugar, TIPO_DE_SUBTIPO
from apps.metricas.models import registrar
from .models import Aporte, Favorito, Notificacion, PropuestaLugar, ResenaLugar

registro = logging.getLogger('infotrip.moderacion')
TEXTO_NOVEDAD = 'Hay información nueva sobre'


def moderar(objeto, moderador, estado, motivo, registrar_sin_cambio=False):
    """Cambia el estado de un objeto Moderable, deja constancia en su historial y avisa al autor.

    El llamador bloquea la fila (select_for_update) dentro de una transacción. Un estado en
    ESTADOS_SIN_MODERACION no se cambia, y si el estado no cambia no se registra nada salvo con
    `registrar_sin_cambio` (por ejemplo, al desestimar un reporte). Devuelve True si cambió el estado.
    """
    anterior = objeto.estado
    cambia = anterior != estado
    if cambia and anterior in objeto.ESTADOS_SIN_MODERACION:
        return False
    if not cambia and not registrar_sin_cambio:
        return False
    if cambia:
        objeto.estado = estado
        objeto.save(update_fields=objeto.CAMPOS_AL_MODERAR)
    objeto.registrar_moderacion(moderador=moderador, estado_anterior=anterior, estado_nuevo=estado, motivo=motivo)
    registro.info('%s %s: %s → %s por el moderador %s', type(objeto).__name__, objeto.pk, anterior, estado,
                  moderador.pk)
    if cambia:
        if isinstance(objeto, PropuestaLugar):
            sincronizar_lugar(objeto, estado)
        avisar_al_autor(objeto, anterior, estado)
        if estado == 'publicado' and getattr(objeto, 'tipo', '') in ('correccion', 'resena'):
            avisar_a_quienes_lo_guardaron(objeto)
        if estado == 'publicado' and isinstance(objeto, Aporte):
            registrar('aporte_publicado', usuario=objeto.autor, destino=objeto.destino.slug)
        if estado == 'publicado' and isinstance(objeto, ResenaLugar):
            registrar('resena_lugar_publicada', usuario=objeto.autor, destino=f'lugar-{objeto.lugar_id}')
    return cambia


def municipio_cercano(latitud, longitud):
    """El de lo publicado más próximo a 20 km o menos: orientativo, y el personal puede corregirlo en el admin."""
    margen = 0.2
    candidatos = []
    for modelo in (Lugar, Destino):
        candidatos += modelo.objects.filter(
            es_activo=True, municipio__isnull=False, latitud__range=(latitud - margen, latitud + margen),
            longitud__range=(longitud - margen, longitud + margen),
        ).values_list('latitud', 'longitud', 'municipio_id')
    cercanos = [(distancia_km(latitud, longitud, float(lat), float(lng)), municipio)
                for lat, lng, municipio in candidatos]
    cercanos = [fila for fila in cercanos if fila[0] <= 20]
    return min(cercanos, default=(None, None))[1]


def sincronizar_lugar(propuesta, estado):
    """Aprobar publica el lugar; ocultar la propuesta después lo retira. Nunca crea dos lugares."""
    if propuesta.lugar_id:
        Lugar.objects.filter(pk=propuesta.lugar_id).update(es_activo=estado == 'publicado')
    elif estado == 'publicado':
        propuesta.lugar = Lugar.objects.create(
            nombre=propuesta.nombre, tipo=TIPO_DE_SUBTIPO[propuesta.subtipo], subtipo=propuesta.subtipo,
            latitud=propuesta.latitud, longitud=propuesta.longitud, direccion=propuesta.direccion,
            telefono=propuesta.telefono, sitio_web=propuesta.sitio_web, horario=propuesta.horario,
            municipio_id=municipio_cercano(float(propuesta.latitud), float(propuesta.longitud)), protegido=True,
        )
        propuesta.save(update_fields=['lugar'])
    if estado == 'publicado':
        registrar('lugar_aprobado', usuario=propuesta.autor, destino=f'lugar-{propuesta.lugar_id}')


def avisar_al_autor(objeto, anterior, estado):
    # El motivo no se incluye: puede citar el texto de un reporte de otra persona.
    texto = objeto.aviso_para_autor(anterior, estado)
    if texto:
        enlace = objeto.enlace_publicado() if estado == 'publicado' else ''
        Notificacion.objects.create(usuario=objeto.autor, texto=texto, enlace=enlace, correo_pendiente=True)


def avisar_a_quienes_lo_guardaron(objeto):
    """Novedad en un lugar guardado. Como mucho un aviso por persona y lugar a la semana, para no cansar."""
    destino = objeto.destino
    enlace = reverse('destino-detalle', kwargs={'slug': destino.slug})
    recientes = Notificacion.objects.filter(
        enlace=enlace, texto__startswith=TEXTO_NOVEDAD, creado__gte=timezone.now() - timedelta(days=7),
    ).values('usuario')
    personas = (Favorito.objects.filter(destino=destino, autor__es_activo=True).exclude(autor=objeto.autor)
                .exclude(autor__in=recientes).values_list('autor', flat=True))
    Notificacion.objects.bulk_create([
        Notificacion(usuario_id=persona, texto=f'{TEXTO_NOVEDAD} {destino.nombre}, uno de tus lugares guardados.',
                     enlace=enlace, correo_pendiente=True)
        for persona in personas
    ])
