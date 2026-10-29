"""Consultas de contenido comunitario que otros módulos pueden usar.

Es la única puerta de `destinos` hacia `comunidad`: este módulo solo depende de los modelos de
comunidad y conoce los destinos por su clave foránea, así que nunca importa código de `destinos`.
"""
from datetime import timedelta
from django.db.models import Avg, Count, Exists, Max, Min, OuterRef, Prefetch, Subquery
from django.utils import timezone
from .models import Aporte, Colaboracion


def publicados():
    return Aporte.objects.filter(estado='publicado', destino__es_activo=True, autor__es_activo=True)


def publicas():
    return Colaboracion.objects.filter(estado='publicado', autor__es_activo=True, destino__es_activo=True)


def con_foto_publica(destinos):
    """Añade `fotos_publicas` (la foto publicada más reciente) a cada destino."""
    fotos = Aporte.objects.filter(tipo='foto', estado='publicado', autor__es_activo=True).order_by('-creado', '-pk')[:1]
    return destinos.prefetch_related(Prefetch('aportes', queryset=fotos, to_attr='fotos_publicas'))


def correcciones_recientes(dias=90):
    desde = timezone.localdate() - timedelta(days=dias)
    return Colaboracion.objects.filter(
        destino_id=OuterRef('pk'), tipo='correccion', estado='publicado',
        autor__es_activo=True, fecha_dato__gte=desde,
    )


def con_info_reciente(destinos):
    """Anota `tiene_info_reciente`: información práctica consultada en los últimos 90 días."""
    return destinos.annotate(tiene_info_reciente=Exists(correcciones_recientes()))


def filtrar_comunidad(queryset, datos):
    aportes = publicados().filter(destino_id=OuterRef('pk')).order_by()
    if datos.get('calificacion_min') is not None:
        promedio = aportes.filter(tipo='resena').values('destino_id').annotate(valor=Avg('calificacion')).values('valor')
        queryset = queryset.annotate(nota_comunidad=Subquery(promedio)).filter(nota_comunidad__gte=datos['calificacion_min'])
    if datos.get('concepto'):
        promedio = (aportes.filter(tipo='gasto', concepto=datos['concepto'],
                                   fecha_visita__gte=timezone.localdate() - timedelta(days=365))
                    .values('destino_id').annotate(valor=Avg('monto')).values('valor'))
        queryset = queryset.annotate(precio_comunidad=Subquery(promedio)).filter(precio_comunidad__isnull=False)
        if datos.get('precio_max') is not None:
            queryset = queryset.filter(precio_comunidad__lte=datos['precio_max'])
    return queryset


def resumen(destino):
    aportes = publicados().filter(destino=destino)
    resenas = aportes.filter(tipo='resena').aggregate(promedio=Avg('calificacion'), cantidad=Count('id'))
    gastos = list(aportes.filter(tipo='gasto', fecha_visita__gte=timezone.localdate() - timedelta(days=365))
                  .order_by('concepto').values('concepto')
                  .annotate(promedio=Avg('monto'), cantidad=Count('id'), minimo=Min('monto'), maximo=Max('monto')))
    etiquetas = dict(Aporte.CONCEPTOS)
    for gasto in gastos:
        gasto['nombre'] = etiquetas[gasto['concepto']]
    return {'resenas': resenas, 'gastos': gastos}


def ficha_practica(destino):
    """Información aportada por personas: nunca se rellena un dato desconocido."""
    correcciones = list(publicas().filter(destino=destino, tipo='correccion').select_related('autor')
                        .order_by('-fecha_dato', '-creado', '-pk'))
    hoy = timezone.localdate()
    campos = []
    for key, label in Colaboracion.CAMPOS:
        historial = [item for item in correcciones if item.campo == key]
        dato = historial[0] if historial else None
        edad = (hoy - dato.fecha_dato).days if dato else None
        vigencia = ('reciente' if edad <= 30 else 'por_confirmar' if edad <= 90 else 'antigua') if edad is not None else 'desconocida'
        campos.append({'nombre': label, 'dato': dato, 'historial': historial[1:], 'edad_dias': edad, 'vigencia': vigencia})
    return campos


def preguntas_publicas(destino):
    respuestas = publicas().filter(tipo='respuesta').select_related('autor')
    return (publicas().filter(destino=destino, tipo='pregunta').select_related('autor')
            .prefetch_related(Prefetch('respuestas', queryset=respuestas, to_attr='respuestas_publicas')))


def aportes_publicos(destino):
    return publicados().filter(destino=destino).select_related('autor')
