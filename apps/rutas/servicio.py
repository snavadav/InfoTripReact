"""Arma un problema del optimizador con los destinos de la base y convierte el plan en algo que mostrar."""
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.urls import reverse

from apps.comunidad.selectors import textos_practicos
from apps.destinos.lugares import cerca_de
from apps.destinos.models import Categoria, Destino, Municipio
from .horarios import Horario, leer_horario, leer_precio
from .optimizador import (
    FACTOR_CARRETERA, Dia, Problema, Sitio, distancia_km, genetico, km_por_carretera, minutos_de_manejo, voraz,
)

# Minutos de visita en ritmo normal, por categoría.
DURACION = {'ciudad-y-cultura': 75, 'miradores': 30, 'naturaleza': 120, 'costa': 180, 'arqueologia': 90,
            'pueblos': 150, 'lago': 90}
DURACION_GENERAL = 60
RITMOS = {'tranquilo': 1.3, 'normal': 1.0, 'intenso': 0.75}
# Si no hay horario publicado: al aire libre, con luz de día; lo demás, horario típico de museo.
AL_AIRE_LIBRE = {'miradores', 'naturaleza', 'costa', 'lago', 'pueblos'}
VENTANA_AIRE_LIBRE = (8 * 60, 19 * 60)
VENTANA_GENERAL = (10 * 60, 17 * 60)
# Sin destino: hasta dónde se buscan sitios en línea recta desde la salida, según los días del viaje.
RADIO_KM = {1: 80, 2: 150, 3: 200}
# Con destino, los sitios se buscan en un corredor: entra uno si el desvío para pasar por él,
# d(salida, sitio) + d(sitio, destino) − d(salida, destino), en línea recta, cabe en este margen. Es una elipse
# con la salida y el destino como focos; crece con los días porque con más tiempo uno se puede alejar más del
# camino. 30 km es lo que se desvía alguien que sale por una hora de la carretera (ida y vuelta, con curvas).
MARGEN_CORREDOR_KM = {1: 30, 2: 60, 3: 90}
# Quedarse en el destino: del día 2 en adelante se sale a pasear y se vuelve a dormir ahí. 50 km en línea recta
# son alrededor de una hora de manejo por carretera: un paseo de ida y vuelta que deja el día para visitar. Lo que
# solo queda en el corredor (más lejos del destino) se visita únicamente el día 1, de camino.
RADIO_BASE_KM = 50
# Los sitios a esta distancia del destino suman BONO_DESTINO: la ruta llega a él y lo recorre, no solo pasa.
RADIO_ZONA_DESTINO_KM = 20
BONO_DESTINO = 0.3
# Tipos de viaje. 'circulo' es el de siempre: sin destino, en un círculo alrededor de la salida.
MODOS = {'circulo': 'Sin destino', 'ida_vuelta': 'Ida y vuelta', 'ida': 'Solo ida', 'base': 'Quedarme en el destino'}
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


def resolver_destino(valor):
    """A dónde va la persona: 'destino:<slug>' (un destino público) o 'municipio:<slug>'. None si no existe.

    Devuelve nombre, punto y, si es un destino, su clave: ese sitio se vuelve parada obligatoria.
    """
    tipo, _, slug = (valor or '').partition(':')
    if tipo == 'destino':
        destino = Destino.objects.filter(es_activo=True, slug=slug).first()
        if destino:
            return {'tipo': 'destino', 'slug': slug, 'nombre': destino.nombre, 'clave': destino.pk,
                    'punto': (float(destino.latitud), float(destino.longitud)),
                    'url': reverse('destino-detalle', args=[slug])}
    elif tipo == 'municipio':
        municipio = municipios_de_salida().filter(slug=slug).first()
        if municipio:
            return {'tipo': 'municipio', 'slug': slug, 'nombre': municipio.nombre, 'clave': None,
                    'punto': (float(municipio.lat), float(municipio.lng)),
                    'url': f"{reverse('destinos-listado')}?municipio={slug}"}
    return None


def lejania(origen, punto, dias, modo='circulo', destino=None):
    """Qué tan apartado del viaje queda un sitio: 0 en el camino, 1 en el límite, None si queda fuera."""
    if modo == 'circulo' or destino is None:
        radio = RADIO_KM[dias]
        distancia = distancia_km(origen, punto)
        return distancia / radio if distancia <= radio else None
    margen = MARGEN_CORREDOR_KM[1 if modo == 'base' else dias]
    desvio = distancia_km(origen, punto) + distancia_km(punto, destino) - distancia_km(origen, destino)
    valores = [desvio / margen] if desvio <= margen else []
    if modo == 'base':
        alrededor = distancia_km(destino, punto)
        if alrededor <= RADIO_BASE_KM:
            valores.append(alrededor / RADIO_BASE_KM)
    return min(valores) if valores else None


def candidatos(origen, intereses, dias, ritmo, modo='circulo', destino=None):
    """(sitios, destinos por clave): los más afines y cercanos dentro del círculo o del corredor del viaje.

    `destino` es lo que devuelve resolver_destino. Si es un destino concreto, entra siempre como obligatorio.
    """
    punto_destino = destino['punto'] if destino else None
    obligatorio = destino['clave'] if destino and modo != 'circulo' else None
    destinos = []
    for d in Destino.objects.filter(es_activo=True).select_related('municipio').prefetch_related('categorias'):
        punto = (float(d.latitud), float(d.longitud))
        valor = lejania(origen, punto, dias, modo, punto_destino)
        if valor is not None or d.pk == obligatorio:
            destinos.append((d, punto, valor or 0))
    textos = textos_practicos([d.pk for d, _, _ in destinos], ['horarios', 'precios'])
    puntuados = []
    for d, punto, valor in destinos:
        slugs = {c.slug for c in d.categorias.all()}
        horario = leer_horario(textos.get((d.pk, 'horarios')))
        precio = leer_precio(textos.get((d.pk, 'precios')))
        puntaje = (PUNTAJE_INTERES if slugs & intereses else PUNTAJE_OTRO) + (BONO_HORARIO if horario else 0) + (
            BONO_PRECIO if precio else 0)
        if punto_destino and modo != 'circulo' and distancia_km(punto_destino, punto) <= RADIO_ZONA_DESTINO_KM:
            puntaje += BONO_DESTINO
        duracion = max(DURACION.get(slug, DURACION_GENERAL) for slug in slugs) if slugs else DURACION_GENERAL
        sitio = Sitio(d.pk, punto, puntaje, round(duracion * RITMOS[ritmo]), horario or _ventana_supuesta(slugs),
                      precio, obligatorio=d.pk == obligatorio)
        if modo == 'base' and distancia_km(punto_destino, punto) > RADIO_BASE_KM:
            # Solo queda en el camino de ida: desde el día 2 se pasea alrededor del destino, no de vuelta a casa.
            sitio.dia = 0
        d.horario_confirmado = horario is not None
        d.guiado = bool(horario and horario.guiado)
        d.slugs = slugs
        # Lo afín y cercano primero; la distancia pesa poco para no dejar fuera lo que vale el viaje.
        orden = float('inf') if sitio.obligatorio else puntaje - valor / 4
        puntuados.append((orden, sitio, d))
    puntuados.sort(key=lambda fila: (-fila[0], fila[2].pk))
    elegidos = puntuados[:MAXIMO_CANDIDATOS]
    return [s for _, s, _ in elegidos], {d.pk: d for _, _, d in elegidos}


def advertencia_tiempo(origen, origen_nombre, destino, dias, inicio, fin, modo):
    """Aviso, antes de calcular, si el puro trayecto directo no cabe en el horario. No impide calcular."""
    if not destino or modo == 'circulo':
        return None
    directo = minutos_de_manejo(km_por_carretera(origen, destino['punto']))
    por_dia = fin - inicio
    if modo == 'ida_vuelta':
        necesario, disponible, como = 2 * directo, por_dia * dias, 'ida y vuelta'
    elif modo == 'base':
        # El primer día hay que llegar a dormir al destino.
        necesario, disponible, como = directo, por_dia, 'el primer día'
    else:
        necesario, disponible, como = directo, por_dia * dias, 'de ida'
    if necesario <= disponible:
        return None
    if modo == 'base':
        sugerencia = 'Empieza más temprano el primer día o termina más tarde.'
    elif dias < max(RADIO_KM):
        sugerencia = 'Prueba con más días o con un horario más amplio.'
    else:
        sugerencia = 'Prueba con un horario más amplio o con un destino más cercano.'
    return (f'Solo manejar de {origen_nombre} a {destino["nombre"]} {como} toma unas {_duracion(necesario)} '
            f'(estimado, sin paradas) y tu horario da {_duracion(disponible)}. {sugerencia}')


def _duracion(minutos):
    horas, resto = divmod(minutos, 60)
    if not horas:
        return f'{resto} min'
    return f'{horas} h {resto} min' if resto else f'{horas} h'


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


def regresa(modo, regresar):
    """Si el último día se vuelve a la salida: lo decide el tipo de viaje; sin destino, la persona."""
    return {'ida_vuelta': True, 'ida': False, 'base': False}.get(modo, regresar)


def construir_problema(origen, fecha, dias, inicio, fin, intereses, ritmo='normal', personas=1, presupuesto=None,
                       regresar=True, modo='circulo', destino=None):
    """(problema, fechas, destinos por clave). Lo usan el planeador y el experimento.

    - circulo: como siempre; sin destino.
    - ida_vuelta: corredor hasta el destino y regreso a la salida el último día.
    - ida: corredor; el viaje termina en el destino (punto final del optimizador).
    - base: el día 1, corredor hasta el destino y ahí se duerme; desde el día 2 se sale y se vuelve a él.
    """
    if destino is None:
        modo = 'circulo'
    sitios, destinos = candidatos(origen, set(intereses), dias, ritmo, modo, destino)
    fechas = [fecha + timedelta(days=i) for i in range(dias)]
    final = destino['punto'] if modo in ('ida', 'base') else None
    nodo_final = len(sitios) + 1
    dias_del_viaje = []
    for numero, dia in enumerate(fechas):
        if modo == 'base':
            dias_del_viaje.append(Dia(dia.weekday(), inicio, fin, desde=nodo_final if numero else None,
                                      hasta=nodo_final))
        else:
            dias_del_viaje.append(Dia(dia.weekday(), inicio, fin))
    problema = Problema(origen, dias_del_viaje, sitios, personas, presupuesto, regresa(modo, regresar), final)
    return problema, fechas, destinos


def planear(origen, fecha, dias, inicio, fin, intereses, ritmo='normal', personas=1, presupuesto=None,
            regresar=True, modo='circulo', destino=None, origen_nombre='la salida'):
    """El itinerario listo para mostrar. `inicio` y `fin` en minutos desde medianoche."""
    if destino is None:
        modo = 'circulo'
    regresar = regresa(modo, regresar)
    advertencia = advertencia_tiempo(origen, origen_nombre, destino, dias, inicio, fin, modo)
    problema, fechas, destinos = construir_problema(origen, fecha, dias, inicio, fin, intereses, ritmo, personas,
                                                    presupuesto, regresar, modo, destino)
    sitios = problema.sitios
    plan = genetico(problema, semilla=SEMILLA)
    simple = voraz(problema)
    sin_precio, supuestos, resultado_dias = set(), set(), []
    for numero, (dia, paradas) in enumerate(zip(fechas, plan.dias)):
        filas = []
        for parada in paradas:
            sitio = sitios[parada.sitio]
            visto = destinos[sitio.clave]
            precio = sitio.precio_para(dia.weekday())
            if precio is None:
                sin_precio.add(visto.pk)
            if not visto.horario_confirmado:
                supuestos.add(visto.pk)
            filas.append({
                'destino': {'id': visto.pk, 'nombre': visto.nombre, 'url': reverse('destino-detalle',
                            args=[visto.slug]), 'municipio': visto.municipio.nombre,
                            'latitud': sitio.punto[0], 'longitud': sitio.punto[1]},
                'llegada': _hora(parada.llegada), 'inicio': _hora(parada.inicio), 'salida': _hora(parada.salida),
                'km': round(parada.km, 1), 'manejo_min': parada.manejo, 'visita_min': sitio.duracion,
                'precio': None if precio is None else str(precio), 'horario_confirmado': visto.horario_confirmado,
                'guiado': visto.guiado,
                'comida': _lugar(_mas_cercano(sitio.punto, 'comer', 3)) if parada.comida_despues else None,
                'comida_despues': parada.comida_despues,
            })
        ultimo = numero == dias - 1
        # Quedándose en el destino se duerme ahí cada noche; en solo ida, la última noche es en el destino.
        if modo == 'base' or (modo == 'ida' and ultimo):
            punto_dormir = destino['punto']
        elif filas and (not ultimo or not regresar):
            punto_dormir = sitios[paradas[-1].sitio].punto
        else:
            punto_dormir = None
        resultado_dias.append({
            'fecha': dia.isoformat(), 'dia_semana': dia.weekday(), 'paradas': filas,
            'dormir': _lugar(_mas_cercano(punto_dormir, 'dormir', 10)) if punto_dormir else None,
        })
    avisos = [advertencia] if advertencia else []
    avisos.append(f'Tiempos de manejo aproximados: distancia en línea recta × {FACTOR_CARRETERA} por las curvas de '
                  'la carretera, sin tráfico. Confirma la ruta en tu aplicación de mapas.')
    if destino and destino['clave'] and modo != 'circulo':
        visitado = any(sitios[i].clave == destino['clave'] for i in plan.visitados)
        if not visitado:
            avisos.append(f'No cupo una visita a {destino["nombre"]} con ese horario; la ruta llega hasta ahí.'
                          if modo != 'ida_vuelta' else f'No cupo una visita a {destino["nombre"]} con ese horario.')
    if supuestos:
        avisos.append(f'{len(supuestos)} sitio(s) sin horario publicado: supusimos uno habitual. Confírmalo antes '
                      'de ir.')
    if sin_precio:
        avisos.append(f'{len(sin_precio)} sitio(s) sin precio conocido: el total no los incluye.')
    if not plan.visitados:
        avisos.append('No encontramos sitios que quepan en ese horario. Prueba con más horas, otro día o más '
                      'intereses.')
    return {
        'viaje': {'modo': modo, 'modo_nombre': MODOS[modo], 'regresar': regresar, 'advertencia': advertencia,
                  'destino': None if destino is None else {
                      'nombre': destino['nombre'], 'url': destino['url'], 'tipo': destino['tipo'],
                      'latitud': destino['punto'][0], 'longitud': destino['punto'][1]}},
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
