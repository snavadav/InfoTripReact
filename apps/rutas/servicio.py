"""Arma un problema del optimizador con los destinos de la base y convierte el plan en algo que mostrar."""
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.urls import reverse

from apps.comunidad.selectors import textos_practicos
from apps.destinos.lugares import cerca_de
from apps.destinos.models import Categoria, Destino, Municipio
from .horarios import Horario, leer_horario, leer_precio
from .optimizador import FACTOR_CARRETERA, Dia, Problema, Sitio, distancia_km, genetico, voraz

# Minutos de visita en ritmo normal, por categoría.
DURACION = {'ciudad-y-cultura': 75, 'miradores': 30, 'naturaleza': 120, 'costa': 180, 'arqueologia': 90,
            'pueblos': 150, 'lago': 90}
DURACION_GENERAL = 60
RITMOS = {'tranquilo': 1.3, 'normal': 1.0, 'intenso': 0.75}
# Si no hay horario publicado: al aire libre, con luz de día; lo demás, horario típico de museo.
AL_AIRE_LIBRE = {'miradores', 'naturaleza', 'costa', 'lago', 'pueblos'}
VENTANA_AIRE_LIBRE = (8 * 60, 19 * 60)
VENTANA_GENERAL = (10 * 60, 17 * 60)
# Hasta dónde se buscan sitios en línea recta, según los días del viaje.
RADIO_KM = {1: 80, 2: 150, 3: 200}
MAXIMO_CANDIDATOS = 45
PUNTAJE_INTERES = 1.0
PUNTAJE_OTRO = 0.2
BONO_HORARIO = 0.2
BONO_PRECIO = 0.1
# Con la misma petición sale el mismo plan.
SEMILLA = 2026


def municipios_de_salida():
    """Municipios con destinos públicos y su punto medio, para elegir desde dónde se sale."""
    return (Municipio.objects.annotate(
        n=Count('destinos', filter=Q(destinos__es_activo=True)),
        lat=Avg('destinos__latitud', filter=Q(destinos__es_activo=True)),
        lng=Avg('destinos__longitud', filter=Q(destinos__es_activo=True)),
    ).filter(n__gt=0).order_by('nombre'))


def intereses_disponibles():
    return Categoria.objects.annotate(n=Count('destinos', filter=Q(destinos__es_activo=True))).filter(n__gt=0)


def _ventana_supuesta(slugs):
    abre, cierra = VENTANA_AIRE_LIBRE if slugs & AL_AIRE_LIBRE else VENTANA_GENERAL
    return Horario({dia: [(abre, cierra)] for dia in range(7)})


def candidatos(origen, intereses, dias, ritmo):
    """(sitios, destinos por clave): los más afines y cercanos dentro del radio del viaje."""
    radio = RADIO_KM[dias]
    destinos = []
    for destino in Destino.objects.filter(es_activo=True).select_related('municipio').prefetch_related('categorias'):
        punto = (float(destino.latitud), float(destino.longitud))
        distancia = distancia_km(origen, punto)
        if distancia <= radio:
            destinos.append((destino, punto, distancia))
    textos = textos_practicos([d.pk for d, _, _ in destinos], ['horarios', 'precios'])
    puntuados = []
    for destino, punto, distancia in destinos:
        slugs = {c.slug for c in destino.categorias.all()}
        horario = leer_horario(textos.get((destino.pk, 'horarios')))
        precio = leer_precio(textos.get((destino.pk, 'precios')))
        puntaje = (PUNTAJE_INTERES if slugs & intereses else PUNTAJE_OTRO) + (BONO_HORARIO if horario else 0) + (
            BONO_PRECIO if precio else 0)
        duracion = max(DURACION.get(slug, DURACION_GENERAL) for slug in slugs) if slugs else DURACION_GENERAL
        sitio = Sitio(destino.pk, punto, puntaje, round(duracion * RITMOS[ritmo]),
                      horario or _ventana_supuesta(slugs), precio)
        destino.horario_confirmado = horario is not None
        destino.guiado = bool(horario and horario.guiado)
        destino.slugs = slugs
        # Lo afín y cercano primero; la distancia pesa poco para no dejar fuera lo que vale el viaje.
        puntuados.append((puntaje - distancia / (radio * 4), sitio, destino))
    puntuados.sort(key=lambda fila: (-fila[0], fila[2].pk))
    elegidos = puntuados[:MAXIMO_CANDIDATOS]
    return [s for _, s, _ in elegidos], {d.pk: d for _, _, d in elegidos}


def _hora(minutos):
    return f'{minutos // 60:02d}:{minutos % 60:02d}'


def _lugar(lugar):
    if not lugar:
        return None
    return {'id': lugar.pk, 'nombre': lugar.nombre, 'subtipo': lugar.get_subtipo_display(),
            'url': reverse('lugar-detalle', args=[lugar.pk]), 'distancia': lugar.distancia_legible,
            'latitud': float(lugar.latitud), 'longitud': float(lugar.longitud)}


def _mas_cercano(punto, tipo, radio_km):
    encontrados = cerca_de(punto[0], punto[1], radio_km=radio_km, tipo=tipo, limite=1)
    return encontrados[0] if encontrados else None


def construir_problema(origen, fecha, dias, inicio, fin, intereses, ritmo='normal', personas=1, presupuesto=None,
                       regresar=True):
    """(problema, fechas, destinos por clave). Lo usan el planeador y el experimento."""
    sitios, destinos = candidatos(origen, set(intereses), dias, ritmo)
    fechas = [fecha + timedelta(days=i) for i in range(dias)]
    problema = Problema(origen, [Dia(f.weekday(), inicio, fin) for f in fechas], sitios, personas, presupuesto,
                        regresar)
    return problema, fechas, destinos


def planear(origen, fecha, dias, inicio, fin, intereses, ritmo='normal', personas=1, presupuesto=None,
            regresar=True):
    """El itinerario listo para mostrar. `inicio` y `fin` en minutos desde medianoche."""
    problema, fechas, destinos = construir_problema(origen, fecha, dias, inicio, fin, intereses, ritmo, personas,
                                                    presupuesto, regresar)
    sitios = problema.sitios
    plan = genetico(problema, semilla=SEMILLA)
    simple = voraz(problema)
    sin_precio, supuestos, resultado_dias = set(), set(), []
    for numero, (dia, paradas) in enumerate(zip(fechas, plan.dias)):
        filas = []
        for parada in paradas:
            sitio = sitios[parada.sitio]
            destino = destinos[sitio.clave]
            precio = sitio.precio_para(dia.weekday())
            if precio is None:
                sin_precio.add(destino.pk)
            if not destino.horario_confirmado:
                supuestos.add(destino.pk)
            filas.append({
                'destino': {'id': destino.pk, 'nombre': destino.nombre, 'url': reverse('destino-detalle',
                            args=[destino.slug]), 'municipio': destino.municipio.nombre,
                            'latitud': sitio.punto[0], 'longitud': sitio.punto[1]},
                'llegada': _hora(parada.llegada), 'inicio': _hora(parada.inicio), 'salida': _hora(parada.salida),
                'km': round(parada.km, 1), 'manejo_min': parada.manejo, 'visita_min': sitio.duracion,
                'precio': None if precio is None else str(precio), 'horario_confirmado': destino.horario_confirmado,
                'guiado': destino.guiado,
                'comida': _lugar(_mas_cercano(sitio.punto, 'comer', 3)) if parada.comida_despues else None,
                'comida_despues': parada.comida_despues,
            })
        ultimo = numero == dias - 1
        duerme = filas and (not ultimo or not regresar)
        resultado_dias.append({
            'fecha': dia.isoformat(), 'dia_semana': dia.weekday(), 'paradas': filas,
            'dormir': _lugar(_mas_cercano(sitios[paradas[-1].sitio].punto, 'dormir', 10)) if duerme else None,
        })
    avisos = [f'Tiempos de manejo aproximados: distancia en línea recta × {FACTOR_CARRETERA} por las curvas de la '
              'carretera, sin tráfico. Confirma la ruta en tu aplicación de mapas.']
    if supuestos:
        avisos.append(f'{len(supuestos)} sitio(s) sin horario publicado: supusimos uno habitual. Confírmalo antes '
                      'de ir.')
    if sin_precio:
        avisos.append(f'{len(sin_precio)} sitio(s) sin precio conocido: el total no los incluye.')
    if not plan.visitados:
        avisos.append('No encontramos sitios que quepan en ese horario. Prueba con más horas, otro día o más '
                      'intereses.')
    return {
        'dias': resultado_dias,
        'totales': {'sitios': len(plan.visitados), 'km': round(plan.km), 'manejo_min': plan.manejo,
                    'costo_entradas': str(plan.costo), 'personas': personas,
                    'presupuesto': None if presupuesto is None else str(presupuesto)},
        'avisos': avisos,
        'metodo': {'nombre': 'Algoritmo genético', 'puntaje': round(plan.puntaje, 2),
                   'segundos': round(plan.segundos, 2), 'generaciones': plan.generaciones,
                   'candidatos': len(sitios),
                   'voraz': {'puntaje': round(simple.puntaje, 2), 'sitios': len(simple.visitados)}},
    }
