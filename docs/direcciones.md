# Direcciones con OpenStreetMap

Permite escribir una dirección y que el punto se coloque solo en el mapa, y al revés: al marcar el punto, se llena la dirección. Hoy se usa en «Proponer un lugar» (`/lugares/proponer/`); el componente está listo para «Salir desde una dirección» en el planeador.

Se eligió OpenStreetMap en lugar de Google porque los términos de Google exigen mostrar sus resultados en un mapa de Google, limitan guardar coordenadas y cobran por consulta. Con OSM el costo es $0 y la licencia ODbL permite guardar los datos citando a los colaboradores.

## Piezas

| Pieza | Archivo |
| --- | --- |
| API y proveedores | `apps/destinos/direcciones.py` |
| Rutas | `apps/destinos/urls.py` (bajo `/api/v1/`) |
| Componente del navegador | `static/js/direcciones.js` (estilos en `static/css/buscador.css`) |
| Uso en Proponer un lugar | `templates/destinos/proponer_lugar.html`, `static/js/proponer-lugar.js` |
| Pruebas | `apps/destinos/test_direcciones.py`, `e2e/test_flujos.py` (`test_proponer_un_lugar_por_direccion`, `test_sin_servicio_de_direcciones_el_mapa_sigue_funcionando`) |

## API

Las tres responden una lista de hasta 5 resultados, siempre con la misma forma:

```json
[{"etiqueta": "Avenida Juárez 976, Centro, Guadalajara, Jalisco", "calle": "Avenida Juárez 976",
  "colonia": "Centro", "municipio": "Guadalajara", "estado": "Jalisco", "lat": 20.67412, "lon": -103.34877}]
```

| Ruta | Para qué | Proveedor | Límite por persona (usuario o IP) |
| --- | --- | --- | --- |
| `GET /api/v1/direcciones/sugerir/?q=` | Sugerencias mientras se escribe (mínimo 3 caracteres) | Photon | 60/min |
| `GET /api/v1/direcciones/buscar/?q=` | Una dirección completa (Intro o «Ubicar en el mapa») | Nominatim | 20/min |
| `GET /api/v1/direcciones/inversa/?lat=&lon=` | De un punto a su dirección | Nominatim | 30/min |

Si el proveedor falla, tarda más de 5 s o no hay turno, la respuesta es **503** con `detail` en lenguaje claro y `Retry-After: 5`. La interfaz lo muestra en un `role=status` y el mapa sigue funcionando: siempre se puede marcar el punto a mano.

## Reglas de uso de los servicios públicos

- **Nominatim no se usa para autocompletar.** Su [política de uso](https://operations.osmfoundation.org/policies/nominatim/) lo prohíbe; las sugerencias van a [Photon](https://photon.komoot.io/) (komoot), pensado para eso.
- **Nominatim: como máximo 1 petición por segundo en total.** Antes de cada petición se toma un turno con `cache.add('direcciones:turno:nominatim', 1, timeout=1)`, que en Redis es un `SET NX EX 1` atómico compartido por todos los procesos de gunicorn. Sin turno se espera en pasos de 0.2 s hasta unos 1.6 s; después, 503 amable. Si Redis no responde, no se consulta (no se podría garantizar el límite).
- **Identificación:** `User-Agent: InfoTrip/1.0 (+https://infotrip.online; <contacto>)` y, a Nominatim, el parámetro `email`. El contacto sale de `CONTACTO_GEOCODIFICACION` (si está vacío, de `CONTACTO_PRIVACIDAD`); nunca se escribe en el código.
- **Caché de 30 días** por consulta normalizada (minúsculas, sin acentos, espacios colapsados), por operación y por proveedor. Así una misma dirección no se vuelve a pedir. Los errores no se guardan.
- **Solo Jalisco:** `viewbox` + `bounded=1` + `countrycodes=mx` en Nominatim y `bbox` en Photon; después se descartan los resultados de otros estados que caen en el recuadro (Michoacán, Nayarit, Guanajuato…). Una búsqueda inversa fuera del recuadro ni siquiera se consulta.
- **Idioma:** `accept-language=es` en Nominatim. Photon no tiene español; devuelve el nombre local, que en México ya está en español.

## Privacidad

- El navegador **nunca** llama a OpenStreetMap: todo pasa por nuestro dominio, así que la CSP no cambia y los servicios externos no reciben la IP ni la cuenta de nadie.
- **No se guarda quién buscó qué.** Las claves de la caché son una huella (SHA-256) de la consulta, sin usuario ni IP; el valor es solo la lista de resultados.
- Las coordenadas que llegan se **redondean a 5 decimales** (~1 m) antes de usarlas.
- Las coordenadas y lo que se busca **no aparecen en los registros**: el módulo solo registra el código de error o el tipo de fallo; las respuestas 503 no se repiten como error de Django (ni llegan a Sentry, que además ya quita la cadena de consulta); `gunicorn.conf.py` y `docker/nginx*.conf` registran método, ruta y estado, sin la cadena de consulta, y en desarrollo `runserver` también la omite (`infotrip/registros.py`). Caddy no lleva registro de accesos.
- El navegador guarda las respuestas solo en su caché privada (`Cache-Control: private`).

## Cambiar de proveedor

Todo es configuración (variables de entorno):

| Variable | Por defecto | Para qué |
| --- | --- | --- |
| `GEOCODIFICACION_PROVEEDOR` | `apps.destinos.direcciones.OSMPublico` | Clase del proveedor |
| `GEOCODIFICACION_NOMINATIM_URL` | `https://nominatim.openstreetmap.org` | Nominatim (o compatible) |
| `GEOCODIFICACION_PHOTON_URL` | `https://photon.komoot.io/api/` | Photon |
| `GEOCODIFICACION_CLAVE` | vacío | Se envía como `key` (LocationIQ y similares); nunca va al navegador |
| `GEOCODIFICACION_SEGUNDOS_ENTRE_PETICIONES` | `1` | Turno de Nominatim; `0` sin límite (servidor propio) |
| `CONTACTO_GEOCODIFICACION` | `CONTACTO_PRIVACIDAD` | Contacto del User-Agent y `email` |

Ejemplos:

- **Nominatim propio** (por ejemplo, con el extracto de México de Geofabrik): `GEOCODIFICACION_NOMINATIM_URL=https://geo.midominio.mx` y `GEOCODIFICACION_SEGUNDOS_ENTRE_PETICIONES=0`.
- **LocationIQ** (API compatible con Nominatim): `GEOCODIFICACION_NOMINATIM_URL=https://us1.locationiq.com/v1`, `GEOCODIFICACION_CLAVE=<clave>` y el límite que dé su plan.
- **Otro servicio** (Geoapify…): una clase nueva que herede de `Proveedor` e implemente `sugerir(consulta)`, `buscar(consulta)` e `inversa(lat, lon)` devolviendo la lista normalizada (usa `resultado(...)`), y apuntar `GEOCODIFICACION_PROVEEDOR` a ella. La caché, el filtro de Jalisco, los límites y las vistas no cambian.
- **Sin servicio:** `apps.destinos.direcciones.Desactivado` responde listas vacías sin salir a la red. Es el que usan las pruebas (`infotrip/settings/test.py`), así que ni la CI ni las pruebas consultan a OpenStreetMap.

## Componente del navegador

```js
const buscador = InfoTripDirecciones.conectar(input, {
  alElegir(direccion) { /* {etiqueta, lat, lon, …} */ },
  boton,   // opcional: botón que busca la dirección completa
  estado,  // opcional: elemento role=status visible; si no, se crea uno oculto para lectores de pantalla
});
const direccion = await InfoTripDirecciones.inversa(lat, lon);  // null si no hay; lanza Error con mensaje amable
```

Patrón combobox de ARIA 1.2: sugerencias tras 300 ms sin escribir, flechas para recorrerlas, Intro para elegir (o, sin opción activa, buscar la dirección completa sin enviar el formulario), Escape para cerrar. Sin scripts en línea.

En «Proponer un lugar»: al elegir una sugerencia el marcador cae ahí y se puede arrastrar; al pulsar el mapa, moverlo o usar la ubicación, se busca la dirección del punto. Si el campo está vacío o tiene una dirección que pusimos nosotros, se reemplaza; si la persona escribió la suya, se le pregunta («Usar esta dirección» o «Conservar la mía»). `PropuestaLugar` guarda `direccion`, `latitud` y `longitud` igual que antes.

## Licencia y créditos

Los datos de direcciones son © colaboradores de OpenStreetMap, con licencia [ODbL](https://opendatacommons.org/licenses/odbl/). Se pueden guardar (por ejemplo, la dirección de una propuesta aprobada) siempre que se cite la fuente: está en `/creditos/` («Direcciones: © colaboradores de OpenStreetMap, vía Nominatim y Photon (ODbL)») y junto al campo de dirección.
