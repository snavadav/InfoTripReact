from datetime import timedelta
from django.db.models import Avg, OuterRef, Subquery
from django.utils import timezone
from .consultas import publicados


def filtrar_comunidad(queryset, datos):
    aportes = publicados().filter(destino_id=OuterRef('pk')).order_by()
    if datos.get('calificacion_min') is not None:
        promedio = aportes.filter(tipo='resena').values('destino_id').annotate(valor=Avg('calificacion')).values('valor')
        queryset = queryset.annotate(nota_comunidad=Subquery(promedio)).filter(nota_comunidad__gte=datos['calificacion_min'])
    if datos.get('concepto'):
        promedio = aportes.filter(tipo='gasto', concepto=datos['concepto'], fecha_visita__gte=timezone.localdate()-timedelta(days=365)).values('destino_id').annotate(valor=Avg('monto')).values('valor')
        queryset = queryset.annotate(precio_comunidad=Subquery(promedio)).filter(precio_comunidad__isnull=False)
        if datos.get('precio_max') is not None:
            queryset = queryset.filter(precio_comunidad__lte=datos['precio_max'])
    return queryset
