"""Cola de moderación para el personal: lo pendiente primero, empezando por lo más antiguo."""
from django.contrib import admin
from django.shortcuts import render
from django.urls import reverse
from datetime import datetime, timedelta
from django.utils import timezone
from apps.datos.models import PropuestaActualizacion
from apps.destinos.models import Lugar
from .models import (
    Aporte, Colaboracion, Comentario, ConfirmacionLugar, FotoPasaporte, PropuestaLugar, Reporte, ReporteColaboracion,
    ReporteResenaLugar, ResenaLugar,
)

POR_SECCION = 10


def seccion(titulo, modelo, filtro, queryset, describir, fecha='creado', fuente=None):
    """`fuente`, si se da, devuelve la dirección pública de donde viene el dato (enlace "ver fuente")."""
    ruta = f'admin:{modelo._meta.app_label}_{modelo._meta.model_name}'
    return {
        'titulo': titulo,
        'total': queryset.count(),
        'lista': reverse(f'{ruta}_changelist') + filtro,
        'elementos': [
            {'texto': describir(obj), 'creado': getattr(obj, fecha), 'fuente': fuente(obj) if fuente else '',
             'formato': 'd/m/Y H:i' if isinstance(getattr(obj, fecha), datetime) else 'd/m/Y',
             'enlace': reverse(f'{ruta}_change', args=[obj.pk])}
            for obj in queryset.order_by(fecha, 'pk')[:POR_SECCION]
        ],
    }


def cambio_propuesto(propuesta):
    """Dato anterior → dato nuevo, como se lee en la cola."""
    anterior = propuesta.dato_anterior or 'sin dato'
    return f'{propuesta.fuente.objetivo} · {propuesta.get_tipo_dato_display()}: {anterior} → {propuesta.dato_nuevo}'


def lugar_ausente(lugar):
    return f'{lugar.nombre} · {lugar.municipio or "sin municipio"} · ausente desde {lugar.ausente_desde:%d/%m/%Y}'


def cola_moderacion(request):
    secciones = []
    if request.user.has_perm('comunidad.view_aporte'):
        secciones.append(seccion(
            'Aportes pendientes', Aporte, '?estado__exact=pendiente',
            Aporte.objects.filter(estado='pendiente').select_related('destino', 'autor'),
            lambda a: f'{a.get_tipo_display()} · {a.destino.nombre} · {a.autor.nombre}'))
    if request.user.has_perm('comunidad.view_colaboracion'):
        secciones.append(seccion(
            'Colaboraciones pendientes', Colaboracion, '?estado__exact=pendiente',
            Colaboracion.objects.filter(estado='pendiente').select_related('destino', 'autor'),
            lambda c: f'{c.get_tipo_display()} · {c.destino.nombre} · {c.autor.nombre}'))
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
            lambda p: f'{p.nombre} · {p.get_subtipo_display()} · {p.autor.nombre}'))
    if request.user.has_perm('comunidad.view_resenalugar'):
        secciones.append(seccion(
            'Reseñas de lugares pendientes', ResenaLugar, '?estado__exact=pendiente',
            ResenaLugar.objects.filter(estado='pendiente').select_related('lugar', 'autor'),
            lambda r: f'{r.lugar.nombre} · {r.autor.nombre}'))
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
            lambda f: f'{f.destino.nombre} · {f.autor.nombre}'))
    if request.user.has_perm('comunidad.view_comentario'):
        secciones.append(seccion(
            'Comentarios del sitio sin atender', Comentario, '?atendido__exact=0',
            Comentario.objects.filter(atendido=False), lambda c: f'{c.get_tipo_display()} · {c.texto[:70]}'))
    contexto = {**admin.site.each_context(request), 'title': 'Cola de moderación', 'secciones': secciones}
    return render(request, 'admin/cola_moderacion.html', contexto)
