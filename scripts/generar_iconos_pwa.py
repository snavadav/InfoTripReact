"""Genera los íconos de la app instalable a partir del logo de la barra (templates/partials/navBar.html).

El logo es un SVG de 24×24: un anillo de radio 9 con trazo de 2.4 y un punto de radio 2.6, en el color --marca.
Aquí se dibuja la misma figura con Pillow, a 4× y reducida, para que los bordes salgan suaves.

Uso:  python scripts/generar_iconos_pwa.py
Escribe static/images/app/ (icono.svg, icono-192.png, icono-512.png, icono-maskable-512.png y apple-touch-icon.png).
"""
from pathlib import Path

from PIL import Image, ImageDraw

MARCA = '#C23E0A'   # --marca en static/css/style.css, el color del logo.
PANEL = '#FFFFFF'   # --panel: el fondo de la barra donde vive el logo.
DESTINO = Path(__file__).resolve().parent.parent / 'static' / 'images' / 'app'
SUPERMUESTREO = 4

SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
<rect width="24" height="24" rx="5" fill="{PANEL}"/>
<g transform="translate(2.4 2.4) scale(.8)">
<circle cx="12" cy="12" r="9" fill="none" stroke="{MARCA}" stroke-width="2.4"/>
<circle cx="12" cy="12" r="2.6" fill="{MARCA}"/>
</g>
</svg>
"""


def dibujar(lado, escala_logo, redondeo):
    """`escala_logo`: fracción del lienzo que ocupa la caja de 24×24 del logo. `redondeo`: radio de las esquinas."""
    grande = lado * SUPERMUESTREO
    imagen = Image.new('RGBA', (grande, grande), (0, 0, 0, 0))
    lapiz = ImageDraw.Draw(imagen)
    lapiz.rounded_rectangle((0, 0, grande - 1, grande - 1), radius=int(grande * redondeo), fill=PANEL)
    unidad = grande * escala_logo / 24
    centro = grande / 2

    def circulo(radio, **estilo):
        lapiz.ellipse((centro - radio, centro - radio, centro + radio, centro + radio), **estilo)

    # Anillo: el trazo de 2.4 va centrado sobre el radio 9, de 7.8 a 10.2.
    circulo(10.2 * unidad, fill=MARCA)
    circulo(7.8 * unidad, fill=PANEL)
    circulo(2.6 * unidad, fill=MARCA)
    return imagen.resize((lado, lado), Image.LANCZOS)


def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    (DESTINO / 'icono.svg').write_text(SVG, encoding='utf-8')
    dibujar(192, .8, .2).save(DESTINO / 'icono-192.png', optimize=True)
    dibujar(512, .8, .2).save(DESTINO / 'icono-512.png', optimize=True)
    # Maskable: fondo a sangre y el logo dentro del círculo seguro central (40 % del lado de radio).
    dibujar(512, .62, 0).save(DESTINO / 'icono-maskable-512.png', optimize=True)
    # iOS no usa el manifiesto para el ícono de inicio y le pone sus propias esquinas.
    dibujar(180, .72, 0).convert('RGB').save(DESTINO / 'apple-touch-icon.png', optimize=True)


if __name__ == '__main__':
    main()
