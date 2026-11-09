// Página sin conexión: lista las páginas que el service worker (apps/core/sw.js) guardó en este equipo.
(() => {
  'use strict';
  const PREFIJO_PAGINAS = 'infotrip-paginas-';
  const lista = document.getElementById('paginasGuardadas');
  const vacia = document.getElementById('sinGuardadas');
  const estado = document.getElementById('estadoConexion');
  const fecha = new Intl.DateTimeFormat('es-MX', { dateStyle: 'medium', timeStyle: 'short' });

  document.getElementById('reintentar').addEventListener('click', () => location.reload());
  window.addEventListener('online', () => { estado.textContent = 'Volviste a tener señal. Pulsa «Reintentar».'; });
  window.addEventListener('offline', () => { estado.textContent = ''; });

  function tituloDe(html, ruta) {
    const titulo = new DOMParser().parseFromString(html, 'text/html').title || ruta;
    return titulo.replace(/\s+—\s+InfoTrip$/, '').trim() || ruta;
  }

  async function guardadas() {
    const paginas = [];
    const nombres = (await caches.keys()).filter(nombre => nombre.startsWith(PREFIJO_PAGINAS));
    for (const nombre of nombres) {
      const cache = await caches.open(nombre);
      for (const peticion of await cache.keys()) {
        const url = new URL(peticion.url);
        if (url.origin !== location.origin || url.pathname === location.pathname) continue;
        const respuesta = await cache.match(peticion, { ignoreVary: true });
        if (!respuesta) continue;
        paginas.push({
          ruta: url.pathname + url.search,
          titulo: tituloDe(await respuesta.text(), url.pathname),
          guardada: Number(respuesta.headers.get('x-infotrip-guardado')) || 0,
        });
      }
    }
    return paginas.sort((a, b) => b.guardada - a.guardada);
  }

  async function mostrar() {
    let paginas = [];
    try {
      if ('caches' in window) paginas = await guardadas();
    } catch { /* Sin acceso a la caché (modo privado estricto): se muestra como vacía. */ }
    lista.replaceChildren(...paginas.map(({ ruta, titulo, guardada }) => {
      const item = document.createElement('li');
      const enlace = document.createElement('a');
      enlace.href = ruta;
      enlace.textContent = titulo;
      item.append(enlace);
      if (guardada) {
        const cuando = document.createElement('small');
        cuando.textContent = `Guardada el ${fecha.format(guardada)}`;
        item.append(cuando);
      }
      return item;
    }));
    vacia.hidden = paginas.length > 0;
  }

  mostrar();
})();
