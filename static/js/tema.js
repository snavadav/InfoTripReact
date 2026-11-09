// Se carga en <head>, sin defer, para aplicar el tema antes de pintar y evitar el destello.
(() => {
  'use strict';
  const CLAVE = 'infotrip_tema';
  const raiz = document.documentElement;

  function guardado() {
    try { return localStorage.getItem(CLAVE); } catch { return null; }
  }
  function aplicar(tema) {
    raiz.dataset.theme = tema;
    document.querySelectorAll('[data-theme-toggle]').forEach(boton => {
      // Etiqueta fija y estado en aria-pressed: el lector de pantalla anuncia "Tema oscuro, activado/desactivado".
      boton.setAttribute('aria-label', 'Tema oscuro');
      boton.title = tema === 'dark' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro';
      boton.setAttribute('aria-pressed', String(tema === 'dark'));
    });
  }

  // El tema claro es el predeterminado: es el de mejor lectura a pleno sol y en pantallas modestas.
  // El oscuro queda a un toque y se recuerda en este navegador.
  aplicar(guardado() === 'dark' ? 'dark' : 'light');

  document.addEventListener('DOMContentLoaded', () => {
    aplicar(raiz.dataset.theme);
    document.querySelectorAll('[data-theme-toggle]').forEach(boton => boton.addEventListener('click', () => {
      const tema = raiz.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(CLAVE, tema); } catch { /* Sin almacenamiento, el cambio dura esta página. */ }
      aplicar(tema);
    }));
  });
})();
