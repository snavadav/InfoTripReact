// Piezas comunes de los mapas: fondo, marcadores por categoría y agrupación. Requiere Leaflet.
window.InfoTripMapa = (() => {
  'use strict';
  const CENTRO_JALISCO = [20.45, -103.75];
  const ZOOM_JALISCO = 8;

  // Iconos propios, trazados a 24×24. Sin datos de la persona: es seguro insertarlos como HTML.
  const TRAZOS = {
    'Pueblos': 'M4 20V10l8-6 8 6v10M10 20v-6h4v6',
    'Costa': 'M3 16c2-2 4-2 6 0s4 2 6 0 4-2 6 0M3 20c2-2 4-2 6 0s4 2 6 0 4-2 6 0M12 12V4M12 4l5 4H7z',
    'Lago': 'M3 11c2-2 4-2 6 0s4 2 6 0 4-2 6 0M3 16c2-2 4-2 6 0s4 2 6 0 4-2 6 0',
    'Lagos': 'M3 11c2-2 4-2 6 0s4 2 6 0 4-2 6 0M3 16c2-2 4-2 6 0s4 2 6 0 4-2 6 0',
    'Arqueología': 'M3 20h18M6 20v-4h12v4M9 16v-4h6v4M11 12V8h2v4',
    'Ciudad y cultura': 'M4 20V9l8-5 8 5v11M4 20h16M9 20v-7M15 20v-7',
    'Miradores': 'M2 12s4-6 10-6 10 6 10 6-4 6-10 6-10-6-10-6zM12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z',
    'Naturaleza': 'M12 3l5 8h-3l4 6H6l4-6H7zM12 17v4',
  };
  const TRAZO_GENERAL = 'M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21zM12 11.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4z';

  function icono(punto, seleccionado = false) {
    const trazo = TRAZOS[punto.categoria] || TRAZO_GENERAL;
    const clases = `pin${seleccionado ? ' pin--activo' : ''}${punto.destacado ? ' pin--destacado' : ''}`;
    return L.divIcon({
      className: 'pin-envoltura',
      html: `<span class="${clases}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${trazo}"/></svg></span>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
      popupAnchor: [0, -14],
    });
  }

  function crear(contenedor, {rueda = true, alFallarFondo = null} = {}) {
    const mapa = L.map(contenedor, {scrollWheelZoom: rueda, zoomControl: false});
    L.control.zoom({position: 'topright', zoomInTitle: 'Acercar', zoomOutTitle: 'Alejar'}).addTo(mapa);
    mapa.attributionControl.setPrefix(false);
    const fondo = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      // OpenStreetMap exige saber qué sitio pide el mapa, y el sitio no envía Referer a otros dominios
      // (Referrer-Policy: same-origin). Solo aquí se envía el dominio, nunca la ruta de la página.
      referrerPolicy: 'strict-origin-when-cross-origin',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(mapa);
    if (alFallarFondo) fondo.on('tileerror', alFallarFondo);
    return mapa;
  }

  function agrupador() {
    if (!L.markerClusterGroup) return L.featureGroup();
    return L.markerClusterGroup({
      showCoverageOnHover: false,
      maxClusterRadius: 44,
      spiderfyDistanceMultiplier: 1.6,
      iconCreateFunction: grupo => L.divIcon({
        className: 'pin-envoltura',
        html: `<span class="pin-grupo">${grupo.getChildCount()}</span>`,
        iconSize: [36, 36],
        iconAnchor: [18, 18],
      }),
    });
  }

  function coordenadas(punto) {
    const lat = Number(punto.latitud), lng = Number(punto.longitud);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
    return [lat, lng];
  }

  // Devuelve {slug: marcador} con los puntos que tienen coordenadas válidas.
  function agregarPuntos(grupo, puntos, alElegir) {
    const marcadores = new Map();
    puntos.forEach(punto => {
      const posicion = coordenadas(punto);
      if (!posicion) return;
      const marcador = L.marker(posicion, {icon: icono(punto), title: punto.nombre, alt: punto.nombre, riseOnHover: true});
      marcador.on('click', () => alElegir(punto, marcador));
      marcador.on('keypress', evento => { if (evento.originalEvent.key === 'Enter') alElegir(punto, marcador); });
      marcadores.set(punto.slug, marcador);
      grupo.addLayer(marcador);
    });
    return marcadores;
  }

  // Coordenada legible, parte de la identidad visual: 20.6764° N, 103.3422° O.
  function formatoCoordenadas(lat, lng) {
    const a = Number(lat), o = Number(lng);
    return `${Math.abs(a).toFixed(4)}° ${a >= 0 ? 'N' : 'S'}, ${Math.abs(o).toFixed(4)}° ${o >= 0 ? 'E' : 'O'}`;
  }

  return {CENTRO_JALISCO, ZOOM_JALISCO, icono, crear, agrupador, coordenadas, agregarPuntos, formatoCoordenadas};
})();
