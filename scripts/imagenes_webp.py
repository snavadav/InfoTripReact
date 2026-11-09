"""Genera los iconos WebP de las fotos del catálogo (static/images/destinos y las de inspiración).

Por cada foto `nombre.jpg` (no las `-m.jpg`) crea `nombre-i.webp`: un recorte cuadrado de 160 px para los
iconos de 56-76 px de las tarjetas (nítido hasta 2x). Antes se descargaba la miniatura de 640 px (~50 KB)
o, en las de inspiración, la foto completa (hasta 320 KB) para pintarla en 56 px; el icono pesa ~6 KB.

Uso:  python scripts/imagenes_webp.py
Se vuelve a correr cuando se agrega una foto al catálogo; apps/destinos/tests.py comprueba que no falte ninguna.
"""
from pathlib import Path

from PIL import Image, ImageOps

RAIZ = Path(__file__).resolve().parent.parent / 'static' / 'images'
ICONO = 160


def fotos():
    yield from (RAIZ / 'destinos').glob('*.jpg')
    yield RAIZ / 'ptVallarta.jpg'
    yield RAIZ / 'tequila.jpg'


def main():
    for origen in sorted(fotos()):
        if origen.stem.endswith('-m'):
            continue
        with Image.open(origen) as imagen:
            imagen = ImageOps.exif_transpose(imagen).convert('RGB')
            icono = ImageOps.fit(imagen, (ICONO, ICONO), Image.LANCZOS)
            icono.save(origen.with_name(origen.stem + '-i.webp'), 'WEBP', quality=70, method=6)
        print(origen.name, '->', origen.stem + '-i.webp')


if __name__ == '__main__':
    main()
