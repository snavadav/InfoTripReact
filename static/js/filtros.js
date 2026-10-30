(() => {
  // Los filtros avanzados empiezan plegados para que los resultados se vean sin desplazarse;
  // siguen abiertos si hay alguno aplicado o un error que corregir. Sin JavaScript, siempre abiertos.
  const panel = document.getElementById('filters-panel');
  if (panel) panel.open = panel.dataset.activos === 'true';
})();
