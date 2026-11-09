// Página pública de una ruta compartida: el itinerario ya viene en el HTML; aquí van el mapa y compartir.
(() => {
  'use strict';
  const pagina = document.getElementById('ruta-compartida');
  const datos = JSON.parse(document.getElementById('ruta-datos').textContent);
  const COLORES = 3;
  // La dirección real de esta página, aunque se abra desde otro dominio (pruebas o una vista previa).
  const url = location.origin + location.pathname;

  InfoTripCompartirRuta.conectar(pagina.querySelector('.planeador-compartir'), pagina.dataset.titulo, url);

  function colorDia(numero) {
    return getComputedStyle(pagina).getPropertyValue(`--dia-${numero % COLORES}`).trim() || '#0A7564';
  }
  function numerado(numero, dia) {
    return L.divIcon({className: 'pin-envoltura', html: `<span class="pin-ruta dia-${dia % COLORES}">${numero}</span>`,
      iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -14]});
  }
  function popup(texto, enlace) {
    const caja = document.createElement('div');
    const a = document.createElement('a');
    a.href = enlace;
    a.textContent = texto;
    caja.append(a);
    return caja;
  }

  function dibujar() {
    const contenedor = document.getElementById('ruta-mapa');
    if (!window.L || !window.InfoTripMapa) {
      contenedor.textContent = 'No se pudo cargar el mapa. El itinerario se muestra abajo.';
      return;
    }
    const mapa = InfoTripMapa.crear('ruta-mapa');
    mapa.setView(InfoTripMapa.CENTRO_JALISCO, InfoTripMapa.ZOOM_JALISCO);
    const capa = L.featureGroup().addTo(mapa);
    const origen = 'latitud' in datos.origen ? [datos.origen.latitud, datos.origen.longitud] : null;
    if (origen) {
      L.marker(origen, {icon: InfoTripMapa.icono({}, true), title: datos.origen.nombre, alt: datos.origen.nombre})
        .bindPopup(Object.assign(document.createElement('strong'), {textContent: `Salida: ${datos.origen.nombre}`}))
        .addTo(capa);
    }
    let anterior = origen;
    datos.dias.forEach((paradas, numero) => {
      const trazo = anterior ? [anterior] : [];
      paradas.forEach((parada, indice) => {
        const punto = [parada.latitud, parada.longitud];
        trazo.push(punto);
        L.marker(punto, {icon: numerado(indice + 1, numero), title: parada.nombre,
          alt: `Día ${numero + 1}, parada ${indice + 1}: ${parada.nombre}`})
          .bindPopup(popup(`Día ${numero + 1} · ${indice + 1}. ${parada.nombre}`, parada.url)).addTo(capa);
      });
      if (numero === datos.dias.length - 1 && datos.regresar && origen && paradas.length) trazo.push(origen);
      // Líneas rectas: indican el orden, no el camino por carretera.
      if (trazo.length > 1) {
        L.polyline(trazo, {className: `ruta-linea dia-${numero % COLORES}`, color: colorDia(numero), weight: 3,
          opacity: .85, dashArray: '6 6'}).addTo(capa);
      }
      if (paradas.length) anterior = trazo[trazo.length - 1];
    });
    const limites = capa.getBounds();
    if (limites.isValid()) mapa.fitBounds(limites.pad(0.15), {maxZoom: 14, animate: false});
  }

  if (document.readyState === 'complete') dibujar();
  else window.addEventListener('load', dibujar);
})();
