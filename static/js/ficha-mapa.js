(() => {
  'use strict';
  const contenedor = document.getElementById('ficha-mapa');
  if (!contenedor) return;
  if (!window.L || !window.InfoTripMapa) { contenedor.hidden = true; return; }
  const {latitud, longitud, nombre, categoria, lugarTipo} = contenedor.dataset;
  const posicion = InfoTripMapa.coordenadas({latitud, longitud});
  if (!posicion) { contenedor.hidden = true; return; }
  const mapa = InfoTripMapa.crear(contenedor, {rueda: false});
  mapa.setView(posicion, 13);
  const icono = lugarTipo ? InfoTripMapa.iconoLugar(lugarTipo) : InfoTripMapa.icono({categoria}, true);
  L.marker(posicion, {icon: icono, title: nombre, alt: nombre, zIndexOffset: 1000}).addTo(mapa);
})();
