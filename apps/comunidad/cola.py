"""Cola de moderación para el personal: lo pendiente primero, empezando por lo más antiguo."""
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from datetime import datetime, timedelta
from django.utils import timezone
from apps.datos.models import PropuestaActualizacion
from apps.destinos.models import Lugar
from .models import (
    Aporte, Colaboracion, Comentario, ConfirmacionLugar, FotoPasaporte, PropuestaLugar, Reporte, ReporteColaboracion,
    ReporteResenaLugar, ResenaLugar,
)
from .moderacion import MOTIVOS, moderar

POR_SECCION = 10
# Lo que se puede publicar u ocultar sin salir de la cola. El resto (reportes, fuentes oficiales…) tiene
# acciones propias en su lista.
MODERABLES = {modelo._meta.model_name: modelo
              for modelo in (Aporte, Colaboracion, ResenaLugar, PropuestaLugar, FotoPasaporte)}


def seccion(titulo, modelo, filtro, queryset, describir, fecha='creado', fuente=None, usuario=None, detalle=None,
            imagen=None):
    """`fuente`, si se da, devuelve la dirección pública de donde viene el dato (enlace "ver fuente").

    Con `usuario` y permiso de cambio sobre un modelo de MODERABLES, cada fila lleva los botones Publicar y
    Ocultar. `detalle` e `imagen` devuelven el texto completo y la foto, para decidir sin abrir otra página.
    """
    nombre = modelo._meta.model_name
    ruta = f'admin:{modelo._meta.app_label}_{nombre}'
    decidible = bool(usuario and nombre in MODERABLES and usuario.has_perm(f'comunidad.change_{nombre}'))
    return {
        'titulo': titulo,
        'total': queryset.count(),
        'lista': reverse(f'{ruta}_changelist') + filtro,
        'elementos': [
            {'texto': describir(obj), 'creado': getattr(obj, fecha), 'fuente': fuente(obj) if fuente else '',
             'formato': 'd/m/Y H:i' if isinstance(getattr(obj, fecha), datetime) else 'd/m/Y',
             'enlace': reverse(f'{ruta}_change', args=[obj.pk]), 'pk': obj.pk,
             'tipo': nombre if decidible else '', 'detalle': detalle(obj) if detalle else '',
             'imagen': imagen(obj) if imagen else ''}
            for obj in queryset.order_by(fecha, 'pk')[:POR_SECCION]
        ],
    }


def detalle_de_aporte(aporte):
    partes = [aporte.texto]
    if aporte.tipo == 'resena':
        partes.insert(0, f'{aporte.calificacion} / 5')
    if aporte.tipo == 'gasto':
        partes.insert(0, f'${aporte.monto} MXN · {aporte.get_concepto_display()}')
    return ' · '.join(partes)


def foto_de_aporte(aporte):
    if aporte.tipo != 'foto' or not aporte.imagen:
        return ''
    return (aporte.miniatura or aporte.imagen).url


def detalle_de_colaboracion(colaboracion):
    campo = f'{colaboracion.get_campo_display()}: ' if colaboracion.campo else ''
    fuente = f' (fuente: {colaboracion.fuente})' if colaboracion.fuente else ''
    return f'{campo}{colaboracion.texto}{fuente}'


def detalle_de_propuesta(propuesta):
    return ' · '.join(filter(None, [propuesta.direccion, propuesta.horario, propuesta.telefono, propuesta.nota]))


def decidir(request):
    """Publica u oculta un elemento desde la cola. Mismo permiso y misma regla (`moderar`) que las listas."""
    modelo = MODERABLES.get(request.POST.get('tipo', ''))
    estado = {'publicar': 'publicado', 'ocultar': 'oculto'}.get(request.POST.get('accion', ''))
    if modelo is None or estado is None or not request.POST.get('pk', '').isdigit():
        messages.error(request, 'No entendimos esa acción. Inténtalo desde la lista.')
        return
    if not request.user.has_perm(f'comunidad.change_{modelo._meta.model_name}'):
        raise PermissionDenied
    motivo_publico = dict(MOTIVOS).get(request.POST.get('motivo', ''), '')
    if estado == 'oculto' and not motivo_publico:
        messages.error(request, 'Elige un motivo para ocultar: es lo que verá quien lo envió.')
        return
    with transaction.atomic():
        objeto = modelo.objects.select_for_update().filter(pk=request.POST['pk']).first()
        if objeto is None:
            messages.warning(request, 'Ese elemento ya no existe.')
            return
        motivo = ('Publicación desde la cola de moderación.' if estado == 'publicado'
                  else f'Ocultado desde la cola de moderación: {motivo_publico}.')
        cambio = moderar(objeto, request.user, estado, motivo, motivo_publico=motivo_publico)
    if cambio:
        messages.success(request, f'{"Publicado" if estado == "publicado" else "Ocultado"}: {objeto}.')
    else:
        messages.warning(request, f'Sin cambios: {objeto} ya estaba decidido.')


def cambio_propuesto(propuesta):
    """Dato anterior → dato nuevo, como se lee en la cola."""
    anterior = propuesta.dato_anterior or 'sin dato'
    return f'{propuesta.fuente.objetivo} · {propuesta.get_tipo_dato_display()}: {anterior} → {propuesta.dato_nuevo}'


def lugar_ausente(lugar):
    return f'{lugar.nombre} · {lugar.municipio or "sin municipio"} · ausente desde {lugar.ausente_desde:%d/%m/%Y}'


def cola_moderacion(request):
    if request.method == 'POST':
        decidir(request)
        return redirect('cola-moderacion')
    secciones = []
    if request.user.has_perm('comunidad.view_aporte'):
        secciones.append(seccion(
            'Aportes pendientes', Aporte, '?estado__exact=pendiente',
            Aporte.objects.filter(estado='pendiente').select_related('destino', 'autor'),
            lambda a: f'{a.get_tipo_display()} · {a.destino.nombre} · {a.autor.nombre}',
            usuario=request.user, detalle=detalle_de_aporte, imagen=foto_de_aporte))
    if request.user.has_perm('comunidad.view_colaboracion'):
        secciones.append(seccion(
            'Colaboraciones pendientes', Colaboracion, '?estado__exact=pendiente',
            Colaboracion.objects.filter(estado='pendiente').select_related('destino', 'autor'),
            lambda c: f'{c.get_tipo_display()} · {c.destino.nombre} · {c.autor.nombre}',
            usuario=request.user, detalle=detalle_de_colaboracion))
    if request.user.has_perm('comunidad.view_reporte'):
        secciones.append(seccion(
            'Reportes abiertos', Reporte, '?resuelto__exact=0',
            Reporte.objects.filter(resuelto=False).select_related('aporte__destino'),
            lambda r: f'Reporte sobre {r.aporte.get_tipo_display().lower()} · {r.aporte.destino.nombre}'))
    if request.user.has_perm('comunidad.view_reportecolaboracion'):
        secciones.append(seccion(
            'Reportes de información abiertos', ReporteColaboracion, '?resuelto__exact=0',
            ReporteColaboracion.objects.filter(resuelto=False).select_related('colaboracion__destino'),
            lambda r: f'Reporte sobre {r.colaboracion.get_tipo_display().lower()} · {r.colaboracion.destino.nombre}'))
    if request.user.has_perm('comunidad.view_propuestalugar'):
        secciones.append(seccion(
            'Lugares propuestos', PropuestaLugar, '?estado__exact=pendiente',
            PropuestaLugar.objects.filter(estado='pendiente').select_related('autor'),
            lambda p: f'{p.nombre} · {p.get_subtipo_display()} · {p.autor.nombre}',
            usuario=request.user, detalle=detalle_de_propuesta))
    if request.user.has_perm('comunidad.view_resenalugar'):
        secciones.append(seccion(
            'Reseñas de lugares pendientes', ResenaLugar, '?estado__exact=pendiente',
            ResenaLugar.objects.filter(estado='pendiente').select_related('lugar', 'autor'),
            lambda r: f'{r.lugar.nombre} · {r.autor.nombre}',
            usuario=request.user, detalle=lambda r: f'{r.calificacion} / 5 · {r.texto}'))
    if request.user.has_perm('comunidad.view_reporteresenalugar'):
        secciones.append(seccion(
            'Reportes de reseñas de lugares abiertos', ReporteResenaLugar, '?resuelto__exact=0',
            ReporteResenaLugar.objects.filter(resuelto=False).select_related('resena__lugar'),
            lambda r: f'Reporte sobre una reseña · {r.resena.lugar.nombre}'))
    if request.user.has_perm('comunidad.view_confirmacionlugar'):
        secciones.append(seccion(
            'Lugares que alguien dice que cerraron (últimos 90 días)', ConfirmacionLugar, '?abierto__exact=0',
            ConfirmacionLugar.objects.filter(abierto=False, fecha__gte=timezone.localdate() - timedelta(days=90),
                                             lugar__es_activo=True).select_related('lugar'),
            lambda c: c.lugar.nombre))
    if request.user.has_perm('datos.view_propuestaactualizacion'):
        secciones.append(seccion(
            'Actualizaciones de fuentes oficiales', PropuestaActualizacion, '?estado__exact=pendiente',
            PropuestaActualizacion.objects.filter(estado='pendiente')
            .select_related('fuente__destino', 'fuente__lugar'),
            cambio_propuesto, fuente=lambda propuesta: propuesta.url))
    if request.user.has_perm('destinos.view_lugar'):
        secciones.append(seccion(
            'Lugares que ya no aparecen en su fuente (OpenStreetMap o DENUE)', Lugar,
            '?posiblemente_cerrado__exact=1&es_activo__exact=1',
            Lugar.objects.filter(posiblemente_cerrado=True, es_activo=True).select_related('municipio'),
            lugar_ausente, fecha='ausente_desde'))
    if request.user.has_perm('comunidad.view_fotopasaporte'):
        secciones.append(seccion(
            'Fotos de pasaporte por revisar', FotoPasaporte, '?estado__exact=pendiente&mostrar__exact=1',
            FotoPasaporte.objects.filter(estado='pendiente', mostrar=True).select_related('destino', 'autor'),
            lambda f: f'{f.destino.nombre} · {f.autor.nombre}', usuario=request.user,
            imagen=lambda f: reverse('admin:comunidad_fotopasaporte_imagen', args=[f.pk])))
    if request.user.has_perm('comunidad.view_comentario'):
        secciones.append(seccion(
            'Comentarios del sitio sin atender', Comentario, '?atendido__exact=0',
            Comentario.objects.filter(atendido=False), lambda c: f'{c.get_tipo_display()} · {c.texto[:70]}'))
    contexto = {**admin.site.each_context(request), 'title': 'Cola de moderación', 'secciones': secciones,
                'motivos': MOTIVOS}
    return render(request, 'admin/cola_moderacion.html', contexto)
