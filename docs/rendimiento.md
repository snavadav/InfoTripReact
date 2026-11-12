# Rendimiento

Fase 3 de la auditoría integral del 11/11/2026 («Rendimiento y arquitectura»). Qué se cambió, cómo se midió y qué
queda pendiente de datos de producción.

## Cómo se mide

Igual que la auditoría: tamaño del cuerpo de la respuesta y tiempo total de tres cargas seguidas sin caché del
navegador (`curl -H "Cache-Control: no-cache"`), después de una carga para calentar el proceso. En local se usa
`runserver` con una base SQLite que reproduce el catálogo de producción (los 356 destinos públicos y los 300 lugares
que devuelve la zona de Guadalajara, leídos de la API pública). La zona de Guadalajara es siempre
`?sur=20.62&oeste=-103.42&norte=20.72&este=-103.28`.

En producción las cifras llevan además unos 95 ms de red y Caddy comprime las respuestas (zstd o gzip).

## Qué se cambió

Cada recomendación va en su propio PR (R2 y R13 juntos porque comparten la caché del catálogo).

| Recomendación | Cambio | Dónde |
|---|---|---|
| R2 | Los puntos del mapa de Explorar salen del HTML a `/destinos/puntos.json` (misma búsqueda, sin la página), con caché del catálogo y 5 minutos en el navegador; el service worker guarda la última copia | `apps/destinos/frontend.py`, `static/js/mapa.js`, `apps/core/sw.js` |
| R13 | Caché del catálogo (`apps/destinos/cache_catalogo.py`): documentos del buscador, categorías y municipios, opciones de los filtros, costos por destino, misiones y cronistas, y el sitemap completo | `apps/destinos/busqueda.py`, `frontend.py`, `sitemaps.py` |
| R14 | La zona del mapa devuelve solo lo del marcador; la ficha completa llega al abrir el recuadro (`/api/v1/lugares/<id>/`) | `apps/destinos/lugares.py`, `static/js/lugares-mapa.js` |
| R15 | Leaflet, markercluster y las fuentes Geist se sirven desde `static/`; la CSP ya no admite unpkg ni Google Fonts | `static/vendor/`, `static/fonts/`, `infotrip/settings/base.py` |

## Resultados (local, 11/11/2026)

«Antes» es `master` en `fcf95fc` (ya con las fases 1 y 2, incluida R3); «después», cada rama con su cambio.
Tiempos: tres cargas sin caché. Consultas: las de una petición repetida, contadas con `CaptureQueriesContext`.

| Indicador | Antes | Después | Meta de la auditoría |
|---|---|---|---|
| HTML de `/destinos/` (R2) | 207 083 B · 167–247 ms · 14 consultas | 30 971 B · 39–46 ms · 6 consultas | < 40 KB |
| HTML de `/destinos/?page=2` (R2) | 206 267 B · 162–179 ms | 30 155 B · 44–50 ms | — |
| `/destinos/puntos.json` (R2) | — (dentro del HTML) | 162 741 B (unos 26 KB comprimido) · 13–28 ms; el navegador lo reutiliza 5 min | — |
| Sugerencia del buscador (R13) | 7 consultas · 26–37 ms | 3 consultas · 26–37 ms | < 130 ms en total |
| `/sitemap.xml` (R13) | 3 consultas · 56–71 ms | 0 consultas · 2–3 ms | — |
| `/misiones/` (R13) | 4 consultas · 42–45 ms | 0 consultas · 21–25 ms | — |
| `/costos/` (R13) | 2 consultas · 11–12 ms | 1 consulta · 9–10 ms | — |
| Zona de Guadalajara (R14) | 133 119 B · 97–112 ms | 28 189 B · 14–16 ms | < 30 KB |
| Zona de Guadalajara, solo «Comer» (R14) | 65 569 B · 55–78 ms | 13 849 B · 11–13 ms | — |
| Dominios de terceros al cargar una ficha (R15) | unpkg.com, fonts.googleapis.com, fonts.gstatic.com y los mosaicos | Solo los mosaicos (tile.openstreetmap.org) | Solo los mosaicos |
| Portada | 23–26 ms (R3 ya quitó los puntos que no usaba) | Sin cambio | < 180 ms con la red |

En SQLite local una consulta cuesta décimas de milisegundo, así que la sugerencia no se acelera aquí; en producción
cada una cruza la red de Docker hasta PostgreSQL y `documentos()` traía las descripciones de los 356 destinos en cada
tecla. El tiempo real hay que confirmarlo con los registros de gunicorn tras desplegar (R19).

### La caché del catálogo

Cada valor se guarda bajo una versión del catálogo. Guardar o borrar un destino, municipio, región, categoría,
servicio, aporte, dato práctico, confirmación o referencia de costo cambia la versión (señales de Django), así que
lo nuevo se ve en la siguiente petición. Lo que no pasa por señales (`queryset.update()`, cambios hechos a mano en la
base, la baja de una cuenta que tenía fotos) se ve como mucho 10 minutos después, cuando caduca lo guardado. En
producción la caché es Redis, compartida por los tres procesos de gunicorn; sin Redis (desarrollo) cada proceso
tiene la suya.

Las pruebas empiezan con la caché vacía (`infotrip/test_runner.py`).

## Pendiente de datos de producción

R12, R22 y R23 se evaluaron sin cambiarlos: dependen de mediciones que la Fase 1 (R19) acaba de habilitar y que
todavía no tienen una semana de historia. Lo que sigue es la recomendación y el dato que la decide.

### R12: procesos de gunicorn

**Hoy.** `web` arranca con `--workers 3` en `docker-compose.yml` y en el `CMD` del `Dockerfile`: tres procesos
síncronos, sin hilos, con el tiempo límite por defecto (30 s), en un t3.small de 2 GB que también ejecuta
PostgreSQL, Redis, Caddy y las tareas. Un plan del planeador ocupa un proceso entre 1 y 2 s de CPU; con tres planes a
la vez, el resto de las peticiones espera.

**Qué cambia la Fase 3.** Explorar deja de calcular los puntos en cada página (de unos 165 ms a unos 45 ms por
página en local) y la zona del mapa tarda unos 14 ms en lugar de unos 110 ms. Eso libera tiempo de proceso, pero no
cambia el caso del planeador.

**Recomendación.** No cambiarlo todavía. Con una semana de registros con duración (R19):

1. Calcular el p95 de `/api/v1/rutas/planear/` y `/api/v1/rutas/alternativas/` y de las páginas con el comando de `docs/operacion.md` («Tiempos de
   respuesta»), y contar cuántas peticiones del planeador se solapan en el mismo segundo.
2. Ver la memoria con `docker stats --no-stream` en un momento de uso normal.
3. Decidir:
   - Si el planeador rara vez se solapa y el p95 de páginas está por debajo de 500 ms: dejar 3 procesos.
   - Si hay solapes y la memoria libre del servidor es menor de 400 MB: pasar a `gthread` con 2 hilos por proceso
     (`worker_class = 'gthread'`, `threads = 2`). Con el GIL no acelera el planeador, pero las peticiones que esperan
     a la base de datos dejan de quedar detrás de un plan, y casi no usa memoria extra.
   - Si hay solapes y sobran más de 400 MB: un cuarto proceso (unos 120 MB más).
4. Sea cual sea la decisión, mover `workers` (y `threads`) a `gunicorn.conf.py`, leído de `WEB_CONCURRENCY`, para
   que no esté repetido en el `Dockerfile` y en `docker-compose.yml`.

Validación: el p95 del planeador y una prueba con 5 planes simultáneos (`ab -n 20 -c 5` o un script con `curl`)
mientras se mide el tiempo de `/destinos/`.

### R22: modo «editorial»

**Hoy.** `inicio()`, `listado()`, `puntos_mapa()` y `detalle()` preguntan `Destino.objects.exists()` en cada visita
para decidir si mostrar la selección editorial de una instalación sin destinos. En producción siempre hay destinos,
así que la rama nunca se usa; la consulta es un `SELECT … LIMIT 1` sobre la llave primaria (menos de 1 ms en
PostgreSQL).

**Recomendación.** Prioridad baja: no compensa tocar cuatro vistas y sus pruebas por una consulta de menos de 1 ms.
Si se hace, la forma más barata es guardar la respuesta con la caché del catálogo
(`cache_catalogo.guardado('catalogo-vacio', …)`), que ya se invalida al crear el primer destino; retirar el modo por
completo obliga a reescribir las pruebas que lo usan (`test_mapa_editorial_y_catalogo_usan_destino_correcto`,
`test_sin_destinos_no_ofrece_cercania`, `test_editorial_filtrada_sin_coordenadas_inventadas`).

### R23: dependencias de la imagen y servicios en bucle

**Hoy.** `requirements.txt` instala scikit-learn, numpy, joblib y el SDK de Anthropic en la única imagen. Solo los
importan el curador (`apps/curador/modelo.py`, `caracteristicas.py` y sus comandos) y el lector de sitios oficiales
(`apps/datos/lector.py`), que corren como comandos de gestión, no al atender peticiones: no ocupan memoria en
`web`. `avisos` y `tareas` son bucles de `sh` que arrancan Python solo al ejecutar el comando y luego duermen.

**Recomendación.** No cambiarlo sin una medición que lo justifique. Separar las dependencias obligaría a mantener dos
imágenes (o una con extras) porque `tareas` sí necesita el SDK de Anthropic. Vale la pena si:

- la construcción en el t3.small pasa de 10 minutos (medir con `time docker compose build web`), o
- el disco queda con menos del 20 % libre (`df -h`, `docker system df`).

En ese caso, un `requirements-tareas.txt` con lo de ML y Anthropic, y una etapa de `Dockerfile` para `tareas` y el
curador. Unificar `avisos` y `tareas` en un solo bucle ahorraría un contenedor `sh` en reposo (unos pocos MB); no se
recomienda por eso solo.
