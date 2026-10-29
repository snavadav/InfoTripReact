"""Cola de moderación para el personal: lo pendiente primero, empezando por lo más antiguo."""
from django.contrib import admin
from django.shortcuts import render
from django.urls import reverse
from .models import Aporte, Colaboracion, Reporte

POR_SECCION = 10


def seccion(titulo, modelo, filtro, queryset, describir):
    nombre = modelo._meta.model_name
    return {
        'titulo': titulo,
        'total': queryset.count(),
        'lista': reverse(f'admin:comunidad_{nombre}_changelist') + filtro,
        'elementos': [
            {'texto': describir(obj), 'creado': obj.creado,
             'enlace': reverse(f'admin:comunidad_{nombre}_change', args=[obj.pk])}
            for obj in queryset.order_by('creado', 'pk')[:POR_SECCION]
        ],
    }


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
    contexto = {**admin.site.each_context(request), 'title': 'Cola de moderación', 'secciones': secciones}
    return render(request, 'admin/cola_moderacion.html', contexto)
