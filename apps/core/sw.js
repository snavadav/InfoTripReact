/* InfoTrip: service worker propio, sin librerías. apps/core/pwa.py le antepone VERSION, STATIC_URL y PRECACHE.
 *
 * Qué guarda:
 *   - Al instalarse: todo el CSS y JS propio, los íconos y la página /sin-conexion/ (caché "app", versionada).
 *   - Las páginas públicas que se visitan, con la red primero (caché "paginas", versionada, como mucho 40).
 *   - Los puntos del mapa de Explorar (/destinos/puntos.json), con la red primero (caché "datos", como mucho 10).
 *   - Las fotos de /static/ que se ven (caché "fotos", versionada, como mucho 60).
 *   - Leaflet de unpkg, solo URLs con versión fija (caché "cdn"; esas URLs nunca cambian de contenido).
 *   - Los cuadros del mapa de OpenStreetMap que se ven, con tope de 50 MB y LRU (caché "mapa").
 * Qué NO guarda nunca: la API (/api/, incluida /api/v1/auth/), /admin/, /media/, nada que no sea GET, las
 * páginas con datos de una persona (pasaporte o escapada compartidos, botes, perfil, mis viajes, favoritos)
 * ni respuestas marcadas no-store o private. Detalle y política de OpenStreetMap: docs/app-instalable.md.
 */
'use strict';

const PREFIJO = 'infotrip-';
const CACHE_APP = `${PREFIJO}app-${VERSION}`;
const CACHE_PAGINAS = `${PREFIJO}paginas-${VERSION}`;
const CACHE_FOTOS = `${PREFIJO}fotos-${VERSION}`;
const CACHE_DATOS = `${PREFIJO}datos-${VERSION}`;
// Sin versión: sobreviven a los despliegues porque su contenido no depende de InfoTrip.
const CACHE_CDN = `${PREFIJO}cdn-v1`;
const CACHE_MAPA = `${PREFIJO}mapa-v1`;
const CACHES_VIGENTES = [CACHE_APP, CACHE_PAGINAS, CACHE_FOTOS, CACHE_DATOS, CACHE_CDN, CACHE_MAPA];

const PAGINA_SIN_CONEXION = PRECACHE[0];
const MAX_PAGINAS = 40;
const MAX_FOTOS = 60;
const MAX_DATOS = 10;
// Con red lenta, pasado este tiempo se muestra la copia guardada (si la hay) en lugar de seguir esperando.
const ESPERA_RED_MS = 4000;

const ORIGEN_MAPA = 'https://tile.openstreetmap.org';
const TOPE_MAPA_BYTES = 50 * 1024 * 1024;
// Si el servidor de cuadros no dice nada, se consideran frescos 7 días (lo que pide su política de uso).
const FRESCURA_POR_DEFECTO_S = 7 * 24 * 3600;
const CABECERA_GUARDADO = 'x-infotrip-guardado';
const CABECERA_BYTES = 'x-infotrip-bytes';

// Páginas públicas iguales para todos: se pueden guardar y mostrar sin red.
const PAGINAS_GUARDABLES = [
  /^\/$/,
  /^\/destinos\/(?:[\w-]+\/(?:costos\/)?)?$/,
  /^\/lugares\/\d+\/$/,
  /^\/costos\/$/,
  /^\/misiones\/$/,
  // Solo el propio: llega sin datos personales y pasaporte.js los añade desde la API. El compartido no.
  /^\/pasaporte\/$/,
  // El planeador y las rutas que alguien decidió hacer públicas con su enlace.
  /^\/planeador\/(?:r\/[0-9a-f-]{36}\/)?$/,
  /^\/creditos\/$/,
  /^\/privacidad\/$/,
  /^\/terminos\/$/,
  /^\/sin-conexion\/$/,
];
// Datos públicos que una página guardable pide aparte: sin ellos, la copia de la página no serviría sin red.
const DATOS_GUARDABLES = [/^\/destinos\/puntos\.json$/];
// Ni se interceptan: el navegador va directo a la red como si no hubiera service worker.
const RUTAS_INTOCABLES = [/^\/api\//, /^\/admin\//, /^\/media\//, /^\/sw\.js$/];

self.addEventListener('install', evento => {
  evento.waitUntil((async () => {
    const cache = await caches.open(CACHE_APP);
    // La página sin conexión es imprescindible: si falla, no se instala y lo reintenta en la próxima visita.
    await cache.add(new Request(PAGINA_SIN_CONEXION, { cache: 'reload' }));
    // Un estático que falle no impide lo demás; se guardará cuando una página lo pida.
    await Promise.all(PRECACHE.slice(1).map(url => cache.add(new Request(url, { cache: 'reload' })).catch(() => {})));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', evento => {
  evento.waitUntil((async () => {
    const nombres = await caches.keys();
    await Promise.all(nombres.filter(nombre => nombre.startsWith(PREFIJO) && !CACHES_VIGENTES.includes(nombre))
      .map(nombre => caches.delete(nombre)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', evento => {
  const peticion = evento.request;
  if (peticion.method !== 'GET') return;
  const url = new URL(peticion.url);

  if (url.origin === self.location.origin) {
    if (RUTAS_INTOCABLES.some(ruta => ruta.test(url.pathname))) return;
    if (url.pathname.startsWith(STATIC_URL)) {
      evento.respondWith(estatico(evento, url));
    } else if (peticion.mode === 'navigate') {
      evento.respondWith(pagina(evento, url));
    } else if (DATOS_GUARDABLES.some(ruta => ruta.test(url.pathname))) {
      evento.respondWith(datos(evento));
    }
    return;
  }
  if (url.origin === ORIGEN_MAPA) {
    evento.respondWith(cuadroDelMapa(evento));
  } else if (url.origin === 'https://unpkg.com' && /@\d+\.\d+\.\d+\//.test(url.pathname)) {
    evento.respondWith(desdeCdn(evento));
  }
});

// ─── Utilidades ────────────────────────────────────────────────

function sePuedeGuardar(respuesta) {
  if (!respuesta || !respuesta.ok || respuesta.redirected) return false;
  const control = (respuesta.headers.get('Cache-Control') || '').toLowerCase();
  return !/no-store|private/.test(control);
}

async function recortar(nombre, maximo) {
  const cache = await caches.open(nombre);
  const claves = await cache.keys();
  // Cache.keys() devuelve en orden de guardado y volver a guardar mueve al final: se borra lo más viejo.
  await Promise.all(claves.slice(0, Math.max(0, claves.length - maximo)).map(clave => cache.delete(clave)));
}

function esperar(ms) {
  return new Promise(resolver => setTimeout(resolver, ms));
}

// ─── Páginas: red primero, copia guardada si no hay red ────────

async function pagina(evento, url) {
  const peticion = evento.request;
  const guardable = PAGINAS_GUARDABLES.some(ruta => ruta.test(url.pathname));
  const red = fetch(peticion).then(respuesta => {
    if (guardable && sePuedeGuardar(respuesta)) evento.waitUntil(guardarPagina(peticion, respuesta.clone()));
    return respuesta;
  });
  // ignoreVary: Django responde con "Vary: Cookie" y la petición del service worker no expone las cookies.
  const copia = guardable ? caches.match(peticion, { cacheName: CACHE_PAGINAS, ignoreVary: true })
    : Promise.resolve(undefined);
  try {
    return await Promise.race([red, esperar(ESPERA_RED_MS).then(async () => (await copia) || red)]);
  } catch {
    return (await copia) || paginaSinConexion();
  }
}

async function guardarPagina(peticion, respuesta) {
  const cabeceras = new Headers(respuesta.headers);
  // La página sin conexión muestra cuándo se guardó cada una.
  cabeceras.set(CABECERA_GUARDADO, String(Date.now()));
  const copia = new Response(await respuesta.blob(), { status: respuesta.status, statusText: respuesta.statusText,
                                                       headers: cabeceras });
  const cache = await caches.open(CACHE_PAGINAS);
  await cache.delete(peticion);
  await cache.put(peticion, copia);
  await recortar(CACHE_PAGINAS, MAX_PAGINAS);
}

// ─── Datos de una página: red primero, copia guardada si no hay red ─

async function datos(evento) {
  const peticion = evento.request;
  try {
    const respuesta = await fetch(peticion);
    if (sePuedeGuardar(respuesta)) {
      const copia = respuesta.clone();
      evento.waitUntil((async () => {
        const cache = await caches.open(CACHE_DATOS);
        await cache.delete(peticion);
        await cache.put(peticion, copia);
        await recortar(CACHE_DATOS, MAX_DATOS);
      })());
    }
    return respuesta;
  } catch (error) {
    const guardada = await caches.match(peticion, { cacheName: CACHE_DATOS, ignoreVary: true });
    if (guardada) return guardada;
    throw error;
  }
}

async function paginaSinConexion() {
  const guardada = await caches.match(PAGINA_SIN_CONEXION, { cacheName: CACHE_APP });
  return guardada || new Response('Sin conexión. Vuelve a intentarlo cuando tengas señal.', {
    status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}

// ─── Estáticos propios: caché primero ──────────────────────────

async function estatico(evento, url) {
  const peticion = evento.request;
  const guardado = await caches.match(peticion, { cacheName: CACHE_APP })
    || await caches.match(peticion, { cacheName: CACHE_FOTOS });
  if (guardado) return guardado;
  const respuesta = await fetch(peticion);
  const ruta = url.pathname.slice(STATIC_URL.length);
  if (sePuedeGuardar(respuesta) && /^(css|js|images)\//.test(ruta)) {
    const copia = respuesta.clone();
    evento.waitUntil((async () => {
      const nombre = ruta.startsWith('images/') ? CACHE_FOTOS : CACHE_APP;
      await (await caches.open(nombre)).put(peticion, copia);
      if (nombre === CACHE_FOTOS) await recortar(CACHE_FOTOS, MAX_FOTOS);
    })());
  }
  return respuesta;
}

// ─── Leaflet en unpkg: URLs con versión, no cambian ───────────

async function desdeCdn(evento) {
  const peticion = evento.request;
  const guardado = await caches.match(peticion, { cacheName: CACHE_CDN });
  if (guardado) return guardado;
  const respuesta = await fetch(peticion);
  // Solo respuestas CORS legibles: las opacas ocupan mucho más en la cuota del navegador.
  if (respuesta.type === 'cors' && sePuedeGuardar(respuesta)) {
    const copia = respuesta.clone();
    evento.waitUntil(caches.open(CACHE_CDN).then(cache => cache.put(peticion, copia)));
  }
  return respuesta;
}

// ─── Cuadros del mapa: LRU con tope de bytes ──────────────────
// Índice en memoria url → bytes, en orden de uso (el más viejo primero). Se reconstruye de la caché al arrancar.

let indiceMapa = null;
let bytesMapa = 0;

function indice() {
  if (!indiceMapa) {
    indiceMapa = (async () => {
      const cache = await caches.open(CACHE_MAPA);
      const mapa = new Map();
      bytesMapa = 0;
      for (const clave of await cache.keys()) {
        const respuesta = await cache.match(clave);
        const bytes = Number(respuesta && respuesta.headers.get(CABECERA_BYTES)) || 0;
        mapa.set(clave.url, bytes);
        bytesMapa += bytes;
      }
      return mapa;
    })();
  }
  return indiceMapa;
}

function segundosDe(control, directiva) {
  const encontrado = new RegExp(`(?:^|,)\\s*${directiva}=(\\d+)`).exec(control);
  return encontrado ? Number(encontrado[1]) : null;
}

// 'fresco': se usa tal cual. 'revalidar': se usa y se renueva en segundo plano. 'vencido': red primero.
// Sigue las cabeceras del servidor de cuadros (max-age y stale-while-revalidate), como pide su política.
function estadoDe(respuesta) {
  const control = (respuesta.headers.get('Cache-Control') || '').toLowerCase();
  const edad = (Date.now() - Number(respuesta.headers.get(CABECERA_GUARDADO))) / 1000;
  const maxEdad = segundosDe(control, 'max-age') ?? FRESCURA_POR_DEFECTO_S;
  if (edad < maxEdad) return 'fresco';
  if (edad < maxEdad + (segundosDe(control, 'stale-while-revalidate') ?? 0)) return 'revalidar';
  return 'vencido';
}

async function cuadroDelMapa(evento) {
  const peticion = evento.request;
  const cache = await caches.open(CACHE_MAPA);
  const guardado = await cache.match(peticion.url);
  if (guardado) {
    const estado = estadoDe(guardado);
    if (estado !== 'vencido') {
      evento.waitUntil(estado === 'fresco' ? usarCuadro(cache, peticion.url, guardado.clone())
        : descargarCuadro(peticion).catch(() => {}));
      return guardado;
    }
  }
  try {
    return await descargarCuadro(peticion, evento);
  } catch (error) {
    // Sin red: mejor un cuadro viejo que un hueco en el mapa.
    if (guardado) return guardado;
    throw error;
  }
}

// Leaflet pide los cuadros sin CORS (respuesta opaca, de tamaño desconocido). Se piden con CORS, que el
// servidor permite, para poder medirlos; con el mismo Referer que mandaría la página.
async function descargarCuadro(peticion, evento) {
  const respuesta = await fetch(peticion.url, {
    mode: 'cors', credentials: 'omit', referrer: peticion.referrer, referrerPolicy: peticion.referrerPolicy,
  });
  if (sePuedeGuardar(respuesta)) {
    const copia = respuesta.clone();
    const guardar = guardarCuadro(peticion.url, copia);
    if (evento) evento.waitUntil(guardar); else await guardar;
  }
  return respuesta;
}

async function guardarCuadro(url, respuesta) {
  const contenido = await respuesta.blob();
  const cabeceras = new Headers(respuesta.headers);
  cabeceras.set(CABECERA_GUARDADO, String(Date.now()));
  cabeceras.set(CABECERA_BYTES, String(contenido.size));
  const cache = await caches.open(CACHE_MAPA);
  await cache.put(url, new Response(contenido, { status: respuesta.status, headers: cabeceras }));
  const mapa = await indice();
  bytesMapa -= mapa.get(url) || 0;
  mapa.delete(url);
  mapa.set(url, contenido.size);
  bytesMapa += contenido.size;
  await expulsar(cache, mapa);
}

// Al usarlo pasa al final del orden; se vuelve a guardar para que el orden se conserve si el navegador
// detiene el service worker (Cache.keys() devuelve en orden de guardado).
async function usarCuadro(cache, url, respuesta) {
  const mapa = await indice();
  if (!mapa.has(url)) return;
  const bytes = mapa.get(url);
  mapa.delete(url);
  mapa.set(url, bytes);
  await cache.put(url, respuesta);
}

async function expulsar(cache, mapa) {
  for (const [url, bytes] of mapa) {
    if (bytesMapa <= TOPE_MAPA_BYTES) break;
    mapa.delete(url);
    bytesMapa -= bytes;
    await cache.delete(url);
  }
}
