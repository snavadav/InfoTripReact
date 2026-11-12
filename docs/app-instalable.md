# App instalable (PWA) y uso sin conexión

InfoTrip se puede instalar como app en Android, iPhone, iPad y en escritorio (Chrome y Edge). Sin señal sigue mostrando lo esencial: las páginas públicas que ya se visitaron y las zonas del mapa que ya se vieron.

## Piezas

| Pieza | Dónde | Notas |
|---|---|---|
| Manifiesto | `/manifest.webmanifest` (`apps/core/pwa.py`) | `application/manifest+json`, colores del tema claro (`--panel` y `--fondo`), íconos de 192, 512 y maskable. |
| Íconos | `static/images/app/` | Salen del logo de la barra con `python scripts/generar_iconos_pwa.py`. No se editan a mano. |
| Service worker | `/sw.js` → código en `apps/core/sw.js` | Se sirve desde la raíz para cubrir todo el sitio (no hace falta `Service-Worker-Allowed`). Sin librerías. |
| Página sin conexión | `/sin-conexion/` (`templates/sin_conexion.html`, `static/js/sin-conexion.js`) | Lista las páginas guardadas en el equipo, con la fecha en que se guardaron. |
| Botón "Instalar app" | `static/js/pwa.js`, `static/css/pwa.css` | Abajo a la izquierda. Sale solo si el navegador avisa que se puede instalar (`beforeinstallprompt`) o en iPhone y iPad, donde explica Compartir → Agregar a inicio. La × lo oculta para siempre en ese navegador. |

## Qué se guarda y cómo

| Caché | Qué | Estrategia | Límite |
|---|---|---|---|
| `infotrip-app-<versión>` | Todo el CSS y JS propios (unos 350 KB), los íconos, `curvas.svg` y `/sin-conexion/` | Se guarda al instalar; caché primero | Lo que haya |
| `infotrip-paginas-<versión>` | Páginas públicas visitadas: `/`, `/destinos/…`, `/lugares/<id>/`, `/costos/`, `/misiones/`, `/pasaporte/`, `/planeador/` y `/planeador/r/<uuid>/`, créditos y avisos legales | Red primero; si no hay red o tarda más de 4 s, la copia guardada; si no hay copia, `/sin-conexion/` | 40 páginas |
| `infotrip-datos-<versión>` | Los puntos del mapa de Explorar (`/destinos/puntos.json`, con la búsqueda de cada página): sin ellos, la copia guardada de `/destinos/` mostraría el mapa vacío | Red primero; sin red, la copia guardada | 10 respuestas |
| `infotrip-fotos-<versión>` | Fotos de `/static/images/` que se ven | Caché primero | 60 fotos |
| `infotrip-cdn-v1` | Leaflet y markercluster de unpkg, solo URLs con versión fija | Caché primero | — |
| `infotrip-mapa-v1` | Cuadros de `tile.openstreetmap.org` que se ven | Ver abajo | 50 MB, LRU |

### Lo que nunca se guarda

- La API: nada bajo `/api/`, incluida la autenticación (`/api/v1/auth/`). El service worker ni siquiera intercepta esas peticiones. El access token vive en memoria y el refresh en la cookie HttpOnly `infotrip_refresh`; ninguno pasa por la caché.
- `/admin/` y `/media/` (fotos que suben las personas, que pueden retirarse por moderación).
- Peticiones que no son GET (POST, PUT, DELETE…).
- Páginas con datos de una persona: pasaporte o escapada compartidos de otra persona, botes, perfil, mis viajes, favoritos, login y registro. Solo se guardan las páginas de la lista de arriba. `/pasaporte/` sí, porque llega sin datos personales: `pasaporte.js` añade los sellos y las fotos desde la API.
- Respuestas con `Cache-Control: no-store` o `private` (por ejemplo, las vistas con `never_cache`).

### Versión de la caché y despliegues

`apps/core/pwa.py` antepone a `sw.js` la constante `VERSION`: una huella del código de `sw.js` y de las URLs de los estáticos que guarda. En producción, `CompressedManifestStaticFilesStorage` (WhiteNoise) pone el hash del contenido en cada nombre, así que cualquier cambio de CSS o JS cambia la versión. Al activarse, el service worker nuevo borra las cachés `infotrip-*` de versiones anteriores (las de CDN y mapa se conservan porque no dependen de InfoTrip). En desarrollo, sin hashes, la huella usa el contenido de los archivos.

`/sw.js` se sirve con `Cache-Control: no-cache` para que el navegador lo revise en cada visita.

## Cuadros del mapa y la política de uso de OpenStreetMap

Los servidores de cuadros de OpenStreetMap los mantienen voluntarios y su [política de uso](https://operations.osmfoundation.org/policies/tiles/) pide, entre otras cosas, no descargar en masa, identificarse y respetar las cabeceras de caché. El service worker:

- **Solo guarda los cuadros que la persona ve.** Nunca descarga zonas por adelantado ni ofrece "descargar el mapa".
- **Respeta las cabeceras del servidor.** Mientras el cuadro tenga menos edad que `max-age`, se usa la copia sin pedirlo otra vez. Dentro de `stale-while-revalidate` se muestra la copia y se renueva en segundo plano. Pasado eso, va a la red primero. Si el servidor no manda cabeceras, se consideran frescos 7 días.
- **Se identifica igual que la página.** Manda el mismo `Referer`, el origen del sitio por `referrerPolicy: strict-origin-when-cross-origin` en `static/js/mapa-base.js`, y el `User-Agent` del navegador.
- **Pide con CORS,** que el servidor permite, para conocer el tamaño de cada cuadro. Las respuestas opacas no se pueden medir y cuentan varios MB en la cuota del navegador.
- **Tope de 50 MB con LRU.** Lleva un índice en memoria de bytes por cuadro, ordenado por uso. Al pasar del tope, borra los menos usados. Cada uso vuelve a guardar el cuadro, así que el orden se conserva aunque el navegador detenga el service worker.
- **Sin red,** usa la copia aunque esté vencida. Es mejor un cuadro viejo que un hueco.
- **Atribución:** Leaflet muestra «© OpenStreetMap» en el mapa, también sin conexión.

Si el uso crece, la política pide usar un proveedor propio o comercial. Ese cambio va en `mapa-base.js` y en `ORIGEN_MAPA` de `sw.js`, y en la CSP: `img-src` de la página y `connect-src` de `/sw.js`.

## CSP

- La página: `worker-src 'self'` y `manifest-src 'self'` en `SECURE_CSP` (`infotrip/settings/base.py`).
- `/sw.js` tiene su propia CSP (`csp_override` en `apps/core/pwa.py`): `default-src 'none'; connect-src 'self' https://unpkg.com https://tile.openstreetmap.org`. Dentro de un worker, `fetch()` se rige por `connect-src`, no por `img-src`.
- Google Fonts no se guarda: sin red, el texto usa la fuente del sistema.

## Producción

nginx (`docker/nginx*.conf`) y Caddy pasan `/sw.js` y `/manifest.webmanifest` a Django sin tocar sus cabeceras. nginx no tiene `proxy_cache`. La CI, en el bloque `test_pwa` del job de Docker, comprueba a través de nginx:

- el `Content-Type` y el `no-cache` de `/sw.js`;
- el tipo del manifiesto y que sus íconos existen;
- que la lista de precache use nombres con hash;
- que `/sin-conexion/` responda.

## Probarlo

- Django: `python manage.py test apps.core.test_pwa --settings=infotrip.settings.test`.
- Navegador: `E2E=1 python manage.py test e2e.test_flujos.FlujosTests.test_sin_senal_se_ve_lo_guardado_o_la_pagina_sin_conexion --settings=infotrip.settings.test`. Las demás pruebas e2e bloquean el service worker, porque Playwright no intercepta lo que este pide.
- A mano: DevTools → Application → Manifest, Service workers y Cache storage. Marca "Offline" en Service workers o en Network y recarga.
