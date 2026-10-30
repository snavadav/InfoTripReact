(() => {
  'use strict';
  const contenedor = document.getElementById('ficha-mapa');
  if (!contenedor) return;
  if (!window.L || !window.InfoTripMapa) { contenedor.hidden = true; return; }
  const {latitud, longitud, nombre, categoria} = contenedor.dataset;
  const posicion = InfoTripMapa.coordenadas({latitud, longitud});
  if (!posicion) { contenedor.hidden = true; return; }
  const mapa = InfoTripMapa.crear(contenedor, {rueda: false});
  mapa.setView(posicion, 13);
  L.marker(posicion, {icon: InfoTripMapa.icono({categoria}, true), title: nombre, alt: nombre, zIndexOffset: 1000}).addTo(mapa);
})();
