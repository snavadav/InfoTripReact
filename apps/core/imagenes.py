from io import BytesIO
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.files.base import ContentFile
from rest_framework import serializers


def imagen_segura(archivo):
    if archivo.size > 5 * 1024 * 1024:
        raise serializers.ValidationError('La imagen no puede superar 5 MB.')
    try:
        with Image.open(archivo) as imagen:
            if imagen.format not in ('JPEG', 'PNG', 'WEBP') or imagen.width * imagen.height > 20000000:
                raise serializers.ValidationError('Usa JPEG, PNG o WebP de hasta 20 megapíxeles.')
            imagen.load()
            salida = BytesIO()
            limpia = ImageOps.exif_transpose(imagen).convert('RGB')
            limpia.thumbnail((2400, 2400))
            limpia.save(salida, format='JPEG', quality=88)
        return ContentFile(salida.getvalue(), name=f'{uuid4().hex}.jpg')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise serializers.ValidationError('No pudimos leer la imagen.')


def miniatura_de(contenido):
    """JPEG de hasta 800 px para tarjetas y listas, a partir de una imagen ya validada por imagen_segura()."""
    contenido.seek(0)
    with Image.open(contenido) as imagen:
        copia = imagen.convert('RGB')
        copia.thumbnail((800, 800))
        salida = BytesIO()
        copia.save(salida, format='JPEG', quality=75, optimize=True)
    contenido.seek(0)
    return ContentFile(salida.getvalue(), name=f'{uuid4().hex}.jpg')
