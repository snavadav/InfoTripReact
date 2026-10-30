"""Consultas de contenido comunitario que otros módulos pueden usar.

Es la única puerta de `destinos` hacia `comunidad`: este módulo solo depende de los modelos de
comunidad y conoce los destinos por su clave foránea, así que nunca importa código de `destinos`.
"""
from datetime import date, timedelta
from statistics import median
from django.db.models import Avg, Count, DateField, Exists, Max, Min, OuterRef, Prefetch, Q, Subquery, Value
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from .models import Aporte, Colaboracion, Confirmacion, VisitaComprobada


def publicados():
    return Aporte.objects.filter(estado='publicado', destino__es_activo=True, autor__es_activo=True)


def publicas():
    return Colaboracion.objects.filter(estado='publicado', autor__es_activo=True, destino__es_activo=True)


def con_foto_publica(destinos):
    """Añade `fotos_publicas` (la foto publicada más reciente) a cada destino."""
    fotos = Aporte.objects.filter(tipo='foto', estado='publicado', autor__es_activo=True).order_by('-creado', '-pk')[:1]
    return destinos.prefetch_related(Prefetch('aportes', queryset=fotos, to_attr='fotos_publicas'))


def confirmaciones_validas():
    return Confirmacion.objects.filter(autor__es_activo=True)


def correcciones_recientes(dias=90):
    """Datos prácticos consultados o confirmados como vigentes en los últimos `dias`."""
    desde = timezone.localdate() - timedelta(days=dias)
    confirmado = Exists(confirmaciones_validas().filter(dato_id=OuterRef('pk'), fecha__gte=desde))
    return Colaboracion.objects.filter(
        Q(fecha_dato__gte=desde) | confirmado,
        destino_id=OuterRef('pk'), tipo='correccion', estado='publicado', autor__es_activo=True,
    )


SIN_FECHA = date(1900, 1, 1)


def por_informacion_reciente(destinos):
    """Ordena por la fecha más reciente en que se consultó o confirmó un dato práctico del destino.

    Los destinos sin datos prácticos quedan al final, por nombre.
    """
    datos = Colaboracion.objects.filter(
        destino_id=OuterRef('pk'), tipo='correccion', estado='publicado', autor__es_activo=True,
    ).order_by().values('destino_id').annotate(m=Max('fecha_dato')).values('m')
    confirmaciones = confirmaciones_validas().filter(
        dato__destino_id=OuterRef('pk'), dato__tipo='correccion', dato__estado='publicado', dato__autor__es_activo=True,
    ).order_by().values('dato__destino_id').annotate(m=Max('fecha')).values('m')
    sin_fecha = Value(SIN_FECHA, output_field=DateField())
    return destinos.annotate(
        info_actualizada=Greatest(Coalesce(Subquery(datos), sin_fecha), Coalesce(Subquery(confirmaciones), sin_fecha)),
    ).order_by('-info_actualizada', 'nombre', 'pk')


def con_info_reciente(destinos):
    """Anota `tiene_info_reciente`: información práctica consultada o confirmada en los últimos 90 días."""
    return destinos.annotate(tiene_info_reciente=Exists(correcciones_recientes()))


def filtrar_comunidad(queryset, datos):
    aportes = publicados().filter(destino_id=OuterRef('pk')).order_by()
    if datos.get('calificacion_min') is not None:
        promedio = (
            aportes.filter(tipo='resena').values('destino_id').annotate(valor=Avg('calificacion')).values('valor')
        )
        queryset = queryset.annotate(nota_comunidad=Subquery(promedio)).filter(
            nota_comunidad__gte=datos['calificacion_min']
        )
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


# Con menos reportes, una cifra sería la opinión de una o dos personas.
MINIMO_REPORTES = 3
CONCEPTOS_DEL_DIA = ('entrada', 'comida', 'transporte')


def _gastos_recientes():
    return publicados().filter(tipo='gasto', fecha_visita__gte=timezone.localdate() - timedelta(days=365))


def _resumir_costos(filas):
    """`filas`: (concepto, monto, fecha_visita). Bajo el mínimo de reportes no expone ninguna cifra."""
    por_concepto = {}
    for concepto, monto, fecha in filas:
        por_concepto.setdefault(concepto, []).append((monto, fecha))
    conceptos = []
    for clave, nombre in Aporte.CONCEPTOS:
        reportes = por_concepto.get(clave, [])
        suficiente = len(reportes) >= MINIMO_REPORTES
        montos = [monto for monto, _ in reportes]
        conceptos.append({
            'clave': clave, 'nombre': nombre, 'cantidad': len(reportes), 'suficiente': suficiente,
            'mediana': median(montos) if suficiente else None,
            'minimo': min(montos) if suficiente else None,
            'maximo': max(montos) if suficiente else None,
            'ultima_fecha': max(fecha for _, fecha in reportes) if suficiente else None,
        })
    del_dia = [fila for fila in conceptos if fila['suficiente'] and fila['clave'] in CONCEPTOS_DEL_DIA]
    return {
        'conceptos': conceptos,
        'hay_datos': any(fila['suficiente'] for fila in conceptos),
        # Con un solo concepto no es un día: "solo comida" parecería más barato que "comida y transporte".
        'dia': {'total': sum(fila['mediana'] for fila in del_dia),
                'incluye': [fila['clave'] for fila in del_dia]} if len(del_dia) >= 2 else None,
        'alojamiento': next((f for f in conceptos if f['clave'] == 'alojamiento' and f['suficiente']), None),
    }


def costos_de_destino(destino):
    return _resumir_costos(
        _gastos_recientes().filter(destino=destino).values_list('concepto', 'monto', 'fecha_visita'))


def costos_por_destino():
    """{destino_id: costos} de los destinos con datos suficientes, en una sola consulta."""
    por_destino = {}
    for destino_id, *fila in _gastos_recientes().values_list('destino_id', 'concepto', 'monto', 'fecha_visita'):
        por_destino.setdefault(destino_id, []).append(fila)
    resumenes = {destino_id: _resumir_costos(filas) for destino_id, filas in por_destino.items()}
    return {destino_id: costos for destino_id, costos in resumenes.items() if costos['hay_datos']}


def vigencia_por_edad(edad):
    if edad is None:
        return 'desconocida'
    return 'reciente' if edad <= 30 else 'por_confirmar' if edad <= 90 else 'antigua'


def ficha_practica(destino):
    """Información aportada por personas: nunca se rellena un dato desconocido."""
    confirmaciones = confirmaciones_validas().filter(dato_id=OuterRef('pk')).order_by()
    correcciones = list(
        dato_vigente_primero(publicas().filter(destino=destino, tipo='correccion').select_related('autor'))
        .annotate(
            ultima_confirmacion=Subquery(confirmaciones.order_by('-fecha').values('fecha')[:1]),
            num_confirmaciones=Subquery(confirmaciones.values('dato_id').annotate(n=Count('pk')).values('n')),
        )
    )
    hoy = timezone.localdate()
    campos = []
    for key, label in Colaboracion.CAMPOS:
        historial = [item for item in correcciones if item.campo == key]
        dato = historial[0] if historial else None
        # La vigencia cuenta desde la consulta original o desde la última confirmación, lo más reciente.
        vigente_desde = max(filter(None, [dato.fecha_dato, dato.ultima_confirmacion])) if dato else None
        edad = (hoy - vigente_desde).days if dato else None
        vigencia = vigencia_por_edad(edad)
        campos.append(
            {'nombre': label, 'dato': dato, 'historial': historial[1:], 'edad_dias': edad, 'vigencia': vigencia,
             'vigente_desde': vigente_desde}
        )
    return campos


def dato_vigente_primero(correcciones):
    """Orden de las versiones de un dato práctico: la primera de cada campo es la vigente."""
    return correcciones.order_by('-fecha_dato', '-creado', '-pk')


def dato_vigente(correccion):
    """La versión publicada que hoy se muestra para el mismo destino y campo."""
    return dato_vigente_primero(
        publicas().filter(destino_id=correccion.destino_id, tipo='correccion', campo=correccion.campo)
    ).first()


def preguntas_publicas(destino):
    respuestas = publicas().filter(tipo='respuesta').select_related('autor')
    return (publicas().filter(destino=destino, tipo='pregunta').select_related('autor')
            .prefetch_related(Prefetch('respuestas', queryset=respuestas, to_attr='respuestas_publicas')))


def aportes_publicos(destino):
    """Anota `visita_comprobada`: quien lo escribió confirmó su ubicación cerca de este destino."""
    visitas = VisitaComprobada.objects.filter(autor_id=OuterRef('autor_id'), destino_id=OuterRef('destino_id'))
    return publicados().filter(destino=destino).select_related('autor').annotate(visita_comprobada=Exists(visitas))


def misiones_por_destino(destino_ids):
    """{destino_id: {'faltan': [...], 'confirmar': [...]}}: qué datos prácticos nadie ha contado o conviene revisar."""
    vigentes = {}
    for pk, destino_id, campo, fecha in dato_vigente_primero(
        publicas().filter(destino_id__in=destino_ids, tipo='correccion')
    ).values_list('pk', 'destino_id', 'campo', 'fecha_dato'):
        vigentes.setdefault((destino_id, campo), (pk, fecha))
    confirmadas = dict(
        confirmaciones_validas().filter(dato_id__in=[pk for pk, _ in vigentes.values()]).order_by()
        .values('dato_id').annotate(ultima=Max('fecha')).values_list('dato_id', 'ultima')
    )
    hoy = timezone.localdate()
    misiones = {destino_id: {'faltan': [], 'confirmar': []} for destino_id in destino_ids}
    for destino_id, mision in misiones.items():
        for clave, nombre in Colaboracion.CAMPOS:
            vigente = vigentes.get((destino_id, clave))
            if not vigente:
                mision['faltan'].append({'clave': clave, 'nombre': nombre})
                continue
            pk, fecha = vigente
            edad = (hoy - max(filter(None, [fecha, confirmadas.get(pk)]))).days
            if vigencia_por_edad(edad) != 'reciente':
                mision['confirmar'].append({'clave': clave, 'nombre': nombre, 'edad_dias': edad})
    return misiones


# Con menos datos, el título no reconocería un aporte sostenido.
MINIMO_CRONISTA = 3


def cronistas():
    """Por municipio, quien más datos prácticos publicó en el último año. Solo cuenta lo que pasó por moderación."""
    filas = (
        publicas().filter(tipo='correccion', creado__gte=timezone.now() - timedelta(days=365)).order_by()
        .values('destino__municipio__nombre', 'autor_id', 'autor__nombre').annotate(datos=Count('pk'))
        .filter(datos__gte=MINIMO_CRONISTA).order_by('destino__municipio__nombre', '-datos', 'autor_id')
    )
    elegidos = {}
    for fila in filas:
        elegidos.setdefault(fila['destino__municipio__nombre'], {
            'municipio': fila['destino__municipio__nombre'], 'nombre': fila['autor__nombre'], 'datos': fila['datos'],
        })
    return list(elegidos.values())
