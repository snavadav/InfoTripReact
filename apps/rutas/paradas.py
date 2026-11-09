"""Lo que el planeador muestra de cada parada: descripción, datos prácticos con su fuente y reseñas recientes.

Solo lectura y solo lo publicado: lo pendiente de moderación, oculto o de cuentas dadas de baja no aparece.
"""
from django.db.models import Avg, Count, Exists, F, OuterRef, Window
from django.db.models.functions import RowNumber
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.comunidad.models import Colaboracion, VisitaComprobada
from apps.comunidad.selectors import dato_vigente_primero, publicados, publicas
from apps.destinos.models import Destino

# Un plan de tres días no pasa de unas treinta paradas.
MAXIMO_DESTINOS = 30
RESENAS_POR_DESTINO = 3
CAMPOS = ('horarios', 'precios')
NOMBRE_CAMPO = dict(Colaboracion.CAMPOS)


class DestinosSerializer(serializers.Serializer):
    destinos = serializers.RegexField(r'^\d+(,\d+)*$', max_length=400, error_messages={
        'invalid': 'Indica los destinos como números separados por comas.'})

    def validate_destinos(self, valor):
        claves = list(dict.fromkeys(int(clave) for clave in valor.split(',')))
        if len(claves) > MAXIMO_DESTINOS:
            raise serializers.ValidationError(f'Pide como máximo {MAXIMO_DESTINOS} destinos a la vez.')
        return claves


def practicos(claves):
    """{destino_id: [dato vigente de horarios y precios, con su fuente y fecha]}."""
    vigentes = {}
    for dato in dato_vigente_primero(publicas().filter(destino_id__in=claves, tipo='correccion', campo__in=CAMPOS)):
        vigentes.setdefault((dato.destino_id, dato.campo), dato)
    resultado = {clave: [] for clave in claves}
    for (destino_id, campo), dato in sorted(vigentes.items(), key=lambda fila: CAMPOS.index(fila[0][1])):
        resultado[destino_id].append({'campo': campo, 'nombre': NOMBRE_CAMPO[campo], 'texto': dato.texto,
                                      'fuente': dato.fuente, 'fecha_dato': dato.fecha_dato})
    return resultado


def resenas(claves):
    """({destino_id: [las más recientes]}, {destino_id: (total, promedio)})."""
    todas = publicados().filter(tipo='resena', destino_id__in=claves)
    resumen = {fila['destino_id']: (fila['total'], fila['promedio']) for fila in
               todas.order_by().values('destino_id').annotate(total=Count('pk'), promedio=Avg('calificacion'))}
    visitas = VisitaComprobada.objects.filter(autor_id=OuterRef('autor_id'), destino_id=OuterRef('destino_id'))
    recientes = (todas.select_related('autor').annotate(
        visita_comprobada=Exists(visitas),
        orden=Window(RowNumber(), partition_by=F('destino_id'), order_by=[F('creado').desc(), F('pk').desc()]),
    ).filter(orden__lte=RESENAS_POR_DESTINO).order_by('destino_id', '-creado', '-pk'))
    por_destino = {clave: [] for clave in claves}
    for resena in recientes:
        por_destino[resena.destino_id].append({
            'id': resena.pk, 'calificacion': resena.calificacion, 'texto': resena.texto,
            'autor_nombre': resena.nombre_publico, 'fecha_visita': resena.fecha_visita,
            'visita_comprobada': resena.visita_comprobada,
        })
    return por_destino, resumen


class ParadasView(APIView):
    """GET ?destinos=1,2,3: descripción, horario y precio vigentes con su fuente, y reseñas publicadas recientes."""
    permission_classes = [AllowAny]

    @extend_schema(parameters=[OpenApiParameter('destinos', OpenApiTypes.STR, required=True,
                                                description='Claves de destino separadas por comas.')],
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        peticion = DestinosSerializer(data=request.query_params)
        peticion.is_valid(raise_exception=True)
        claves = peticion.validated_data['destinos']
        destinos = Destino.objects.filter(pk__in=claves, es_activo=True).only('pk', 'descripcion')
        datos = practicos(claves)
        recientes, resumen = resenas(claves)
        respuesta = []
        for destino in sorted(destinos, key=lambda d: claves.index(d.pk)):
            total, promedio = resumen.get(destino.pk, (0, None))
            respuesta.append({
                'id': destino.pk, 'descripcion': destino.descripcion, 'practicos': datos[destino.pk],
                'resenas': recientes[destino.pk], 'total_resenas': total,
                'promedio': None if promedio is None else round(promedio, 1),
            })
        return Response({'destinos': respuesta})
