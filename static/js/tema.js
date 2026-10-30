// Se carga en <head>, sin defer, para aplicar el tema antes de pintar y evitar el destello.
(() => {
  'use strict';
  const CLAVE = 'infotrip_tema';
  const raiz = document.documentElement;
  const sistema = window.matchMedia('(prefers-color-scheme: dark)');

  function guardado() {
    try { return localStorage.getItem(CLAVE); } catch { return null; }
  }
  function aplicar(tema) {
    raiz.dataset.theme = tema;
    document.querySelectorAll('[data-theme-toggle]').forEach(boton => {
      boton.setAttribute('aria-label', tema === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro');
      boton.setAttribute('aria-pressed', String(tema === 'dark'));
    });
  }

  // Sin preferencia guardada se sigue la del sistema, también si cambia con la página abierta.
  aplicar(guardado() || (sistema.matches ? 'dark' : 'light'));
  sistema.addEventListener('change', evento => {
    if (!guardado()) aplicar(evento.matches ? 'dark' : 'light');
  });

  document.addEventListener('DOMContentLoaded', () => {
    aplicar(raiz.dataset.theme);
    document.querySelectorAll('[data-theme-toggle]').forEach(boton => boton.addEventListener('click', () => {
      const tema = raiz.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(CLAVE, tema); } catch { /* Sin almacenamiento, el cambio dura esta página. */ }
      aplicar(tema);
    }));
  });
})();
