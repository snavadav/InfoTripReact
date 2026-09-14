from datetime import timedelta
from django.db.models import Avg, Count, Min, Max
from django.utils import timezone
from .models import Aporte


def publicados():
    return Aporte.objects.filter(estado='publicado', destino__es_activo=True, autor__es_activo=True)


def resumen(destino):
    aportes = publicados().filter(destino=destino)
    resenas = aportes.filter(tipo='resena').aggregate(promedio=Avg('calificacion'), cantidad=Count('id'))
    gastos = list(aportes.filter(tipo='gasto', fecha_visita__gte=timezone.localdate() - timedelta(days=365))
                  .order_by('concepto').values('concepto').annotate(promedio=Avg('monto'), cantidad=Count('id'), minimo=Min('monto'), maximo=Max('monto')))
    etiquetas = dict(Aporte.CONCEPTOS)
    for gasto in gastos:
        gasto['nombre'] = etiquetas[gasto['concepto']]
    return {'resenas': resenas, 'gastos': gastos}
