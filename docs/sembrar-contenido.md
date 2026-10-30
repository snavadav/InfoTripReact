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

## Contenido de fuentes públicas

`python manage.py sembrar_contenido` carga `apps/destinos/datos/contenido_inicial.json`: horarios, costos, contactos, direcciones y descripciones de museos, zonas arqueológicas y catedrales, tomados del Sistema de Información Cultural de la Secretaría de Cultura y consultados el 30 de octubre de 2026. Corre antes `cargar_destinos_iniciales` e `importar_osm`, para que los sitios que ya existen se completen en lugar de duplicarse.

- Cada dato lleva su fuente y fecha, y lo firma la cuenta "Equipo InfoTrip", que no puede iniciar sesión ni aparece como cronista.
- **Nunca crea reseñas, gastos, calificaciones ni visitas.** Solo pueden venir de personas que fueron.
- Las fichas oficiales pueden estar atrasadas: la fecha indica cuándo se consultaron, no que sigan vigentes. Conviene confirmarlas antes de presentarlas como actuales.
- Se puede repetir: no cambia descripciones editadas ni datos que hayan aportado otras personas.
