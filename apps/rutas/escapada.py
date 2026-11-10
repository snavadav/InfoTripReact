"""Guardar una ruta del planeador como escapada (apps.comunidad.Viaje) para seguir editándola en Mis viajes.

El plan se vuelve a calcular en el servidor con la misma petición (sale igual: el genético usa una semilla fija),
así que nada de lo que se guarda viene del navegador salvo qué opción de comida eligió la persona, y esa se
acepta solo si es una de las que el plan ofrece.

Privacidad: la escapada lleva destinos, horarios y lugares públicos; nunca el punto de salida de quien la armó.

Invitar amigos: al abrirse en el editor (`/mis-viajes/?editar=<id>`), la escapada ofrece «Invitar amigos», que
usa el bote del grupo (apps.comunidad.bote, POST /api/v1/mis-viajes/<id>/bote/invitar/). Aquí no se repite esa
lógica. `despues_de_guardar(viaje, request, datos)` queda para lo que haga falta en el servidor tras guardar.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.urls import reverse

from apps.comunidad.models import Viaje

NOMBRE_MAXIMO = 120
DESTINO_MAXIMO = 200
TITULO_MAXIMO = 150
NOTAS_MAXIMO = 500
NOTAS_VIAJE_MAXIMO = 3000


def _corto(texto, limite):
    return texto if len(texto) <= limite else texto[:limite - 1] + '…'


def nombre_de(plan, datos):
    destino = (plan.get('viaje') or {}).get('destino')
    if destino:
        return _corto(f'Escapada a {destino["nombre"]}', NOMBRE_MAXIMO)
    municipios = _municipios(plan)
    if municipios:
        return _corto(f'Escapada por {municipios[0]}', NOMBRE_MAXIMO)
    return 'Escapada del planeador'


def _municipios(plan):
    vistos = []
    for dia in plan['dias']:
        for parada in dia['paradas']:
            if parada['destino']['municipio'] not in vistos:
                vistos.append(parada['destino']['municipio'])
    return vistos


def _comida_elegida(contenedor, elegidas):
    """La opción que eligió la persona (si es una de las ofrecidas) o la sugerida."""
    for opcion in contenedor.get('comidas') or []:
        if opcion['id'] in elegidas:
            return opcion
    return contenedor.get('comida')


def _actividad_de_comida(numero, hora, comida, personas, gastos):
    notas = f'{comida["tipo"]} a {comida["distancia"]} de la parada anterior.'
    if comida.get('precio'):
        precio = comida['precio']
        notas += f' ${precio["minimo"]} a ${precio["maximo"]} por persona según {precio["reportes"]} reseña(s).'
        # El máximo reportado: mejor que sobre a que falte. Solo con precio real de reseñas publicadas.
        gastos.append({'concepto': 'comida', 'descripcion': _corto(f'Comida en {comida["nombre"]}', 120),
                       'monto': str(Decimal(precio['maximo'])), 'reparto': 'individual', 'cantidad': 1})
    return {'dia': numero, 'hora': hora, 'titulo': _corto(f'Comer en {comida["nombre"]}', TITULO_MAXIMO),
            'notas': _corto(notas, NOTAS_MAXIMO)}


def actividades_y_gastos(plan, elegidas=()):
    """(actividades, gastos): la agenda por día y lo que cuesta, solo con precios conocidos."""
    elegidas = set(elegidas)
    personas = plan['totales']['personas']
    actividades, gastos = [], []
    for numero, dia in enumerate(plan['dias'], start=1):
        libres = {}
        for libre in dia.get('descansos', []):
            libres.setdefault(libre['despues_de'], []).append(libre)

        def descansar(posicion):
            for libre in libres.get(posicion, []):
                actividades.append({'dia': numero, 'hora': libre['inicio'], 'titulo': 'Tiempo libre',
                                    'notas': f'{libre["duracion_min"]} min para descansar.'})
                comida = _comida_elegida(libre, elegidas) if libre.get('comida_despues') else None
                if comida:
                    actividades.append(_actividad_de_comida(numero, libre['fin'], comida, personas, gastos))

        descansar(0)
        for posicion, parada in enumerate(dia['paradas'], start=1):
            destino = parada['destino']
            notas = [f'{destino["municipio"]}. Llegada {parada["llegada"]}, visita de {parada["visita_min"]} min.']
            if not parada['horario_confirmado']:
                notas.append('Horario supuesto: confírmalo antes de ir.')
            actividades.append({'dia': numero, 'hora': parada['inicio'],
                                'titulo': _corto(destino['nombre'], TITULO_MAXIMO),
                                'notas': _corto(' '.join(notas), NOTAS_MAXIMO)})
            if parada['precio'] is not None and Decimal(parada['precio']) > 0:
                gastos.append({'concepto': 'entradas', 'descripcion': _corto(f'Entrada a {destino["nombre"]}', 120),
                               'monto': parada['precio'], 'reparto': 'individual', 'cantidad': 1})
            comida = _comida_elegida(parada, elegidas) if parada['comida_despues'] else None
            if comida:
                actividades.append(_actividad_de_comida(numero, parada['salida'], comida, personas, gastos))
            descansar(posicion)
        if dia.get('dormir'):
            actividades.append({'dia': numero, 'hora': '', 'titulo': _corto(f'Dormir: {dia["dormir"]["nombre"]}',
                                                                             TITULO_MAXIMO),
                                'notas': 'Sugerencia cercana del planeador; sin reservación.'})
    return actividades, gastos


def crear_escapada(usuario, plan, datos, elegidas=()):
    """Guarda el plan como Viaje de `usuario` y lo devuelve. `datos` es la petición ya validada."""
    actividades, gastos = actividades_y_gastos(plan, elegidas)
    total = sum((Decimal(g['monto']) * g['cantidad'] * datos['personas'] for g in gastos), Decimal('0'))
    destino = (plan.get('viaje') or {}).get('destino')
    notas = ['Armada con el planeador de InfoTrip.'] + [a for a in plan['avisos']]
    if gastos:
        notas.append('El presupuesto suma solo entradas y comidas con precio conocido.')
    with transaction.atomic():
        viaje = Viaje.objects.create(
            autor=usuario, nombre=nombre_de(plan, datos),
            destino=_corto(destino['nombre'] if destino else ', '.join(_municipios(plan)) or 'Jalisco',
                           DESTINO_MAXIMO),
            fecha_inicio=datos['fecha'], fecha_fin=datos['fecha'] + timedelta(days=datos['dias'] - 1),
            personas=datos['personas'], presupuesto=total, gastos=gastos,
            actividades=sorted(actividades, key=lambda a: (a['dia'], a['hora'] or '99:99')),
            notas=_corto('\n'.join(notas), NOTAS_VIAJE_MAXIMO),
        )
        viaje.lugares.set([p['destino']['id'] for dia in plan['dias'] for p in dia['paradas']])
    return viaje


def url_del_editor(viaje):
    return f"{reverse('mis-viajes')}?editar={viaje.pk}"


def despues_de_guardar(viaje, request, datos):
    """Punto de extensión: lo que haga falta tras guardar (por ejemplo, invitar amigos). Hoy, nada."""
