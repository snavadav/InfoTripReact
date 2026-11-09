// App instalable: registra el service worker (/sw.js) y ofrece "Instalar app" de forma discreta.
// En Chrome, Edge y Android el botón aparece solo cuando el navegador avisa que se puede instalar
// (beforeinstallprompt). En iPhone y iPad no existe ese aviso: el botón explica Compartir → Agregar a inicio.
(() => {
  'use strict';
  const CLAVE_CERRADO = 'infotrip_instalar_cerrado';

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => { /* Sin service worker el sitio funciona igual. */ });
    });
  }

  const instalada = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const esIos = /iphone|ipad|ipod/i.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  function cerradoAntes() {
    try { return localStorage.getItem(CLAVE_CERRADO) === '1'; } catch { return false; }
  }
  if (instalada || cerradoAntes()) return;

  let avisoDelNavegador = null;
  let caja = null;

  function crear() {
    caja = document.createElement('div');
    caja.className = 'instalar-app';
    caja.innerHTML = `
      <button type="button" class="instalar-app__boton" aria-expanded="false">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>
        Instalar app
      </button>
      <button type="button" class="instalar-app__cerrar" aria-label="No volver a ofrecer instalar la app">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4"
             stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
      <p class="instalar-app__ios" id="instalarAppIos" hidden>
        En Safari toca <strong>Compartir</strong>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" aria-label="(el cuadro con una flecha hacia arriba)"
             role="img"><path d="M12 15V3M8 7l4-4 4 4M6 11H5v10h14V11h-1"/></svg>
        y luego <strong>Agregar a inicio</strong>. InfoTrip quedará como una app, también sin señal.
      </p>`;
    const boton = caja.querySelector('.instalar-app__boton');
    const ayuda = caja.querySelector('.instalar-app__ios');
    boton.addEventListener('click', async () => {
      if (avisoDelNavegador) {
        avisoDelNavegador.prompt();
        const { outcome } = await avisoDelNavegador.userChoice;
        avisoDelNavegador = null;
        if (outcome === 'accepted') quitar();
        else caja.hidden = true;
        return;
      }
      ayuda.hidden = !ayuda.hidden;
      boton.setAttribute('aria-expanded', String(!ayuda.hidden));
      if (!ayuda.hidden) boton.setAttribute('aria-controls', ayuda.id);
    });
    caja.querySelector('.instalar-app__cerrar').addEventListener('click', () => {
      try { localStorage.setItem(CLAVE_CERRADO, '1'); } catch { /* Sin almacenamiento, vuelve a salir otro día. */ }
      quitar();
    });
    caja.addEventListener('keydown', evento => {
      if (evento.key === 'Escape' && !ayuda.hidden) {
        ayuda.hidden = true;
        boton.setAttribute('aria-expanded', 'false');
        boton.focus();
      }
    });
    document.body.append(caja);
  }

  function mostrar() {
    if (!caja) crear();
    caja.hidden = false;
  }

  function quitar() {
    if (caja) caja.remove();
    caja = null;
  }

  window.addEventListener('beforeinstallprompt', evento => {
    evento.preventDefault();
    avisoDelNavegador = evento;
    mostrar();
  });
  window.addEventListener('appinstalled', quitar);

  if (esIos) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mostrar);
    else mostrar();
  }
})();
