(() => {
  // En móvil los filtros empiezan plegados para que los resultados se vean sin desplazarse;
  // siguen abiertos si hay alguno aplicado o un error que corregir. Sin JavaScript, siempre abiertos.
  const panel = document.getElementById('filters-panel');
  if (!panel) return;
  const desktop = window.matchMedia('(min-width: 768px)');
  const active = panel.dataset.activos === 'true';
  function adjust() { panel.open = desktop.matches || active; }
  desktop.addEventListener('change', adjust);
  adjust();
})();
