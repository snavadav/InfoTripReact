# Sembrar contenido

Una ficha le sirve a un viajero cuando tiene datos prácticos. El catálogo trae 15 destinos con foto, ubicación y descripción, pero **ningún dato práctico**: horarios, precios y formas de pago cambian, y no se pueden inventar ni copiar sin comprobar. Los tiene que aportar una persona.

`/admin/metricas/` muestra el avance en "Fichas con al menos 3 datos prácticos".

## Cómo hacerlo

1. Carga el catálogo: `python manage.py cargar_destinos_iniciales`.
2. Crea cuentas normales para las personas del equipo que vayan a aportar.
3. Abre la ficha de un destino y usa **Sugerir información o una corrección**.
4. Para cada dato, indica la fuente y la fecha en que la consultaste.
5. Publícalo desde `/admin/moderacion/`. Conviene que lo revise otra persona.

## Por dónde empezar

Tres datos por destino bastan para que una ficha sea útil. Empieza por los destinos que tu público buscará primero.

| Dato | Dónde comprobarlo |
|---|---|
| Cómo acceder | Visita propia, o el sitio de turismo del municipio |
| Horarios | Sitio oficial o llamada al lugar; solo aplica a lugares concretos, no a una localidad entera |
| Precios y cargos | Sitio oficial o visita propia, con la fecha |

Un dato concreto y fechado vale más que muchos genéricos: "Museo X: martes a domingo, 10 a 18 h, consultado en su sitio el 30/10/2026".

## Después

Pide a los primeros viajeros que confirmen datos con el botón "¿Sigue vigente?". El aviso al terminar un viaje guardado también los invita a reseñar y confirmar.
