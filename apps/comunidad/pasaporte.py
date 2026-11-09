"""Pasaporte de Pueblos Mágicos: una página por pueblo, un sello por visita comprobada y una tarjeta para compartir.

Cada página lleva de fondo la foto propia de la persona, si subió una; si no, la del catálogo, y si tampoco hay,
una ilustración con el nombre del municipio. La foto propia es privada: en el pasaporte compartido solo aparece
si su autor la marca para mostrarse y la moderación la aprueba. El pasaporte compartido nunca muestra fechas.
"""
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.urls import reverse
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.imagenes import imagen_segura
from apps.destinos.fotos import FOTOS_CATALOGO
from apps.destinos.models import Destino
from .models import FotoPasaporte, PasaporteCompartido, VisitaComprobada
from .selectors import PUEBLOS_MAGICOS, SLUGS_PUEBLOS, misiones_por_destino
from .views import AporteThrottle

# Tinta del sello por región. Todas contrastan al menos 4.5:1 con el papel del sello (--sello-papel).
TINTA_POR_REGION = {
    'altos-de-jalisco': '#A1381B',
    'centro-de-jalisco': '#1F4E8C',
    'costa-de-jalisco': '#006A73',
    'ribera-de-chapala': '#5B3E96',
    'sierra-de-jalisco': '#2B6436',
    'valles-de-jalisco': '#875400',
}
TINTA_SIN_REGION = '#4A535B'
# La foto propia se guarda a este tamaño: de sobra para una página del pasaporte y ligera en el teléfono.
LADO_FOTO = 1600


def sellos_de(usuario=None):
    """Los 12 pueblos. `disponible`: ya tiene ficha publicada y por tanto se puede ganar su sello."""
    publicados = set(Destino.objects.filter(es_activo=True, slug__in=SLUGS_PUEBLOS).values_list('slug', flat=True))
    visitados = set()
    if usuario:
        visitados = set(VisitaComprobada.objects.filter(autor=usuario, destino__slug__in=publicados)
                        .values_list('destino__slug', flat=True))
    return [{'slug': slug, 'nombre': nombre, 'disponible': slug in publicados, 'sello': slug in visitados}
            for slug, nombre in PUEBLOS_MAGICOS]


def credito_de_catalogo(slug):
    foto = FOTOS_CATALOGO.get(slug)
    if not foto:
        return None
    return {'url': static(foto['imagen']), 'alt': foto['alt'], 'autor': foto['autor'],
            'licencia': foto['licencia'], 'licencia_url': foto['licencia_url'], 'fuente': foto['fuente']}


def paginas():
    """Lo público de cada página: pueblo, municipio, región, tinta y foto del catálogo. Sin datos de nadie."""
    destinos = {destino.slug: destino for destino in Destino.objects.filter(es_activo=True, slug__in=SLUGS_PUEBLOS)
                .select_related('municipio__region')}
    resultado = []
    for numero, (slug, nombre) in enumerate(PUEBLOS_MAGICOS, start=1):
        destino = destinos.get(slug)
        region = destino.municipio.region if destino else None
        resultado.append({
            'numero': numero, 'slug': slug, 'nombre': nombre, 'disponible': bool(destino),
            'municipio': destino.municipio.nombre if destino else nombre,
            'region': region.nombre if region else '', 'region_slug': region.slug if region else '',
            'tinta': TINTA_POR_REGION.get(region.slug, TINTA_SIN_REGION) if region else TINTA_SIN_REGION,
            'latitud': str(destino.latitud) if destino else '', 'longitud': str(destino.longitud) if destino else '',
            'destino_id': destino.pk if destino else None,
            'foto': credito_de_catalogo(slug), 'sello': False,
            # Los nombres largos se escriben más pequeños para que quepan en el borde del sello.
            'sello_letra': 13 if len(nombre) > 16 else 15 if len(nombre) > 11 else 17,
        })
    return resultado


def avance_por_region(paginas_):
    regiones = {}
    for pagina in paginas_:
        if not pagina['disponible']:
            continue
        region = regiones.setdefault(pagina['region_slug'], {
            'slug': pagina['region_slug'], 'nombre': pagina['region'], 'tinta': pagina['tinta'],
            'total': 0, 'sellados': 0,
        })
        region['total'] += 1
        region['sellados'] += pagina['sello']
    return sorted(regiones.values(), key=lambda region: region['nombre'])


def estado_de_foto(foto):
    if not foto:
        return None
    return {'mostrar': foto.mostrar, 'estado': foto.estado, 'visible_en_compartido': foto.visible_en_compartido,
            'url': reverse('mi-pasaporte-foto-imagen', kwargs={'slug': foto.destino.slug})
            + f'?v={int(foto.actualizado.timestamp())}'}


ESTADO_FOTO = inline_serializer('FotoDePasaporte', fields={
    'mostrar': serializers.BooleanField(), 'estado': serializers.ChoiceField(choices=FotoPasaporte.ESTADOS),
    'visible_en_compartido': serializers.BooleanField(), 'url': serializers.CharField(),
}, allow_null=True)


class MiPasaporteView(APIView):
    """Tus sellos con su fecha, tus fotos y tu avance por región. Solo para ti: el enlace compartido no da fechas."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: inline_serializer('MiPasaporte', fields={
        'nombre': serializers.CharField(),
        'sellos': inline_serializer('SelloDePasaporte', fields={
            'slug': serializers.SlugField(), 'nombre': serializers.CharField(),
            'disponible': serializers.BooleanField(), 'sello': serializers.BooleanField(),
            'fecha': serializers.DateField(allow_null=True), 'foto': ESTADO_FOTO,
            'datos_que_faltan': serializers.IntegerField(),
        }, many=True),
        'regiones': inline_serializer('AvancePorRegion', fields={
            'slug': serializers.SlugField(), 'nombre': serializers.CharField(),
            'total': serializers.IntegerField(), 'sellados': serializers.IntegerField(),
        }, many=True),
        'total': serializers.IntegerField(), 'de': serializers.IntegerField(),
        'enlace': serializers.UUIDField(allow_null=True),
    })})
    def get(self, request):
        sellos = sellos_de(request.user)
        visitas = dict(VisitaComprobada.objects.filter(autor=request.user, destino__slug__in=SLUGS_PUEBLOS)
                       .values_list('destino__slug', 'fecha'))
        fotos = {foto.destino.slug: foto for foto in FotoPasaporte.objects.filter(autor=request.user)
                 .select_related('destino')}
        paginas_ = paginas()
        ids = {pagina['slug']: pagina['destino_id'] for pagina in paginas_}
        # Las misiones de la comunidad: qué datos prácticos faltan en los pueblos que ya visitaste.
        misiones = misiones_por_destino([ids[sello['slug']] for sello in sellos if sello['sello']])
        for sello, pagina in zip(sellos, paginas_):
            pagina['sello'] = sello['sello']
            sello['fecha'] = visitas.get(sello['slug']) if sello['sello'] else None
            sello['foto'] = estado_de_foto(fotos.get(sello['slug'])) if sello['sello'] else None
            sello['datos_que_faltan'] = len(misiones[ids[sello['slug']]]['faltan']) if sello['sello'] else 0
        compartido = PasaporteCompartido.objects.filter(usuario=request.user).first()
        return Response({
            'nombre': request.user.nombre, 'sellos': sellos,
            'regiones': [{clave: region[clave] for clave in ('slug', 'nombre', 'total', 'sellados')}
                         for region in avance_por_region(paginas_)],
            'total': sum(sello['sello'] for sello in sellos), 'de': len(sellos),
            'enlace': compartido.enlace if compartido else None,
        })


class CompartirPasaporteView(APIView):
    """POST crea el enlace público de la tarjeta; DELETE lo retira."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: inline_serializer('EnlaceDePasaporte', fields={
        'enlace': serializers.UUIDField(),
    })})
    def post(self, request):
        compartido, _ = PasaporteCompartido.objects.get_or_create(usuario=request.user)
        return Response({'enlace': compartido.enlace})

    @extend_schema(responses={204: None})
    def delete(self, request):
        PasaporteCompartido.objects.filter(usuario=request.user).delete()
        return Response(status=204)


class FotoPasaporteSerializer(serializers.Serializer):
    imagen = serializers.ImageField(required=False)
    mostrar = serializers.BooleanField(required=False)

    def validate_imagen(self, imagen):
        return imagen_segura(imagen, lado=LADO_FOTO)


def destino_visitado(usuario, slug):
    """El pueblo, si la persona comprobó su visita. Sin visita no hay página sellada a la que poner foto."""
    if slug not in SLUGS_PUEBLOS:
        raise Http404
    destino = get_object_or_404(Destino, slug=slug, es_activo=True)
    if not VisitaComprobada.objects.filter(autor=usuario, destino=destino).exists():
        raise serializers.ValidationError('Primero comprueba tu visita a este lugar: la foto va en su página sellada.')
    return destino


def borrar_al_confirmar(archivo):
    nombre, almacen = archivo.name, archivo.storage
    transaction.on_commit(lambda: almacen.delete(nombre))


class FotoPasaporteView(APIView):
    """POST sube o reemplaza tu foto (privada salvo que marques `mostrar`); PATCH cambia `mostrar`; DELETE la borra.

    La imagen se vuelve a codificar: así se descartan los datos EXIF, incluida la ubicación GPS de la cámara.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_throttles(self):
        return [AporteThrottle()] if self.request.method == 'POST' else []

    @extend_schema(request={'multipart/form-data': FotoPasaporteSerializer}, responses={200: ESTADO_FOTO})
    def post(self, request, slug):
        destino = destino_visitado(request.user, slug)
        datos = FotoPasaporteSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        if 'imagen' not in datos.validated_data:
            raise serializers.ValidationError({'imagen': 'Selecciona una imagen.'})
        with transaction.atomic():
            foto = FotoPasaporte.objects.select_for_update().filter(autor=request.user, destino=destino).first()
            if foto:
                borrar_al_confirmar(foto.imagen)
            else:
                foto = FotoPasaporte(autor=request.user, destino=destino)
            foto.imagen = datos.validated_data['imagen']
            foto.mostrar = datos.validated_data.get('mostrar', False)
            # Una foto nueva vuelve a revisión aunque la anterior estuviera aprobada.
            foto.estado = 'pendiente'
            foto.save()
        return Response(estado_de_foto(foto))

    @extend_schema(request=inline_serializer('MostrarFoto', fields={'mostrar': serializers.BooleanField()}),
                   responses={200: ESTADO_FOTO})
    def patch(self, request, slug):
        destino = destino_visitado(request.user, slug)
        datos = FotoPasaporteSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        if 'mostrar' not in datos.validated_data:
            raise serializers.ValidationError({'mostrar': 'Indica si quieres mostrar la foto.'})
        foto = get_object_or_404(FotoPasaporte, autor=request.user, destino=destino)
        foto.mostrar = datos.validated_data['mostrar']
        foto.save(update_fields=['mostrar', 'actualizado'])
        return Response(estado_de_foto(foto))

    @extend_schema(responses={204: None})
    def delete(self, request, slug):
        foto = get_object_or_404(FotoPasaporte, autor=request.user, destino__slug=slug)
        with transaction.atomic():
            borrar_al_confirmar(foto.imagen)
            foto.delete()
        return Response(status=204)


def respuesta_de_imagen(foto, cache):
    # Se lee entera (pesa poco, ya reducida) para no dejar el archivo abierto mientras se envía.
    with foto.imagen.open('rb') as archivo:
        respuesta = HttpResponse(archivo.read(), content_type='image/jpeg')
    respuesta['Cache-Control'] = cache
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


class ImagenFotoPasaporteView(APIView):
    """El archivo de tu foto. Solo para ti: la página lo pide con tu sesión y lo muestra sin publicarlo."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={(200, 'image/jpeg'): bytes})
    def get(self, request, slug):
        foto = get_object_or_404(FotoPasaporte, autor=request.user, destino__slug=slug)
        return respuesta_de_imagen(foto, 'private, no-store')


def compartido_activo(enlace):
    return get_object_or_404(PasaporteCompartido.objects.select_related('usuario'), enlace=enlace,
                             usuario__es_activo=True)


def fotos_visibles(usuario, visitados):
    """Fotos propias que el pasaporte compartido puede mostrar: marcadas por su autor y aprobadas."""
    return set(FotoPasaporte.objects.filter(autor=usuario, mostrar=True, estado='publicado',
                                            destino__slug__in=visitados).values_list('destino__slug', flat=True))


def pasaporte(request):
    """Página del pasaporte. Llega sin datos personales: pasaporte.js añade los sellos, fechas y fotos propias."""
    paginas_ = paginas()
    return render(request, 'comunidad/pasaporte.html', {
        'paginas': paginas_, 'regiones': avance_por_region(paginas_), 'de': len(paginas_),
        'seo': {'titulo': 'Pasaporte de Pueblos Mágicos de Jalisco — InfoTrip',
                'descripcion': 'Visita los 12 Pueblos Mágicos de Jalisco y junta un sello por cada uno.'},
    })


def pasaporte_publico(request, enlace):
    """Tarjeta para compartir: nombre y sellos, sin fechas, para no revelar cuándo estuvo la persona en cada lugar."""
    compartido = compartido_activo(enlace)
    paginas_ = paginas()
    visitados = {sello['slug'] for sello in sellos_de(compartido.usuario) if sello['sello']}
    propias = fotos_visibles(compartido.usuario, visitados)
    for pagina in paginas_:
        pagina['sello'] = pagina['slug'] in visitados
        if pagina['slug'] in propias:
            pagina['foto_propia'] = reverse('pasaporte-publico-foto', kwargs={'enlace': enlace,
                                                                              'slug': pagina['slug']})
    return render(request, 'comunidad/pasaporte_publico.html', {
        'nombre': compartido.usuario.nombre, 'paginas': paginas_, 'regiones': avance_por_region(paginas_),
        'de': len(paginas_), 'total': len(visitados),
    })


def foto_publica(request, enlace, slug):
    """La foto propia en el pasaporte compartido, solo si sigue marcada para mostrarse y aprobada."""
    compartido = compartido_activo(enlace)
    visitados = {sello['slug'] for sello in sellos_de(compartido.usuario) if sello['sello']}
    if slug not in fotos_visibles(compartido.usuario, visitados):
        raise Http404
    foto = FotoPasaporte.objects.get(autor=compartido.usuario, destino__slug=slug)
    # Poco tiempo en caché: si la persona deja de compartir, la foto deja de verse pronto.
    return respuesta_de_imagen(foto, 'private, max-age=300')
