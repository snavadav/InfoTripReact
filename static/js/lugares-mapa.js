// Lugares útiles sobre el mapa del explorador: por zona visible y "Cerca de mí".
(() => {
  'use strict';
  const explorador = window.InfoTripExplorador;
  if (!explorador) return;
  const {map} = explorador;
  const ZOOM_MINIMO = 12;
  const byId = id => document.getElementById(id);
  const hint = byId('poi-hint');
  const nearbyButton = byId('nearby');
  const nearbyPanel = byId('nearby-panel');
  const nearbyList = byId('nearby-list');
  const nearbyStatus = byId('nearby-status');
  const typeButtons = [...document.querySelectorAll('[data-lugar-tipo]')];
  const cluster = InfoTripMapa.agrupador().addTo(map);
  let activeType = '', nearbyPoint = null, userLayer = null, zoneRequest = null, zoneTimer = null;
  let markerByPlace = new Map();

  function node(tag, text, className) {
    const el = document.createElement(tag);
    if (text) el.textContent = text;
    if (className) el.className = className;
    return el;
  }
  function link(text, href, external = false) {
    const el = node('a', text);
    el.href = href;
    if (external) { el.target = '_blank'; el.rel = 'noopener noreferrer'; }
    return el;
  }
  function distanceText(km) {
    return km < 1 ? `${Math.round(km * 100) * 10} m` : `${km.toFixed(1)} km`;
  }
  function details(place) {
    const box = node('div', null, 'lugar-popup');
    box.append(node('strong', place.nombre));
    if (place.num_resenas) box.append(node('p', `${place.calificacion_promedio.toFixed(1)} / 5 · ${place.num_resenas} ${place.num_resenas === 1 ? 'reseña' : 'reseñas'}`, 'lugar-popup-nota'));
    const where = [place.subtipo_nombre, place.municipio].filter(Boolean).join(' · ');
    box.append(node('p', place.distancia_km === null ? where : `${where} · ${distanceText(place.distancia_km)}`));
    if (place.horario) box.append(node('p', `Horario registrado: ${place.horario}`));
    const actions = node('div', null, 'lugar-popup-acciones');
    actions.append(link('Ver ficha', place.url), link('Cómo llegar ↗', `https://www.google.com/maps/dir/?api=1&destination=${place.latitud},${place.longitud}`, true));
    const phone = place.telefono.replace(/[^+\d]/g, '');
    if (phone) actions.append(link(place.telefono, `tel:${phone}`));
    if (place.sitio_web) actions.append(link('Sitio web ↗', place.sitio_web, true));
    box.append(actions);
    if (place.osm_url) {
      const credit = node('p', '© ', 'lugar-popup-credito');
      credit.append(link('colaboradores de OpenStreetMap', place.osm_url, true));
      box.append(credit);
    }
    return box;
  }
  function draw(places) {
    cluster.clearLayers();
    markerByPlace = new Map();
    places.forEach(place => {
      const position = InfoTripMapa.coordenadas(place);
      if (!position) return;
      const marker = L.marker(position, {icon: InfoTripMapa.iconoLugar(place.tipo), title: place.nombre, alt: place.nombre});
      marker.bindPopup(() => details(place));
      markerByPlace.set(place.id, marker);
      cluster.addLayer(marker);
    });
  }

  /* Zona visible */
  async function loadZone() {
    if (nearbyPoint) return;
    if (!activeType) { draw([]); hint.hidden = true; return; }
    if (map.getZoom() < ZOOM_MINIMO) {
      draw([]);
      hint.textContent = 'Acércate en el mapa para ver estos lugares.';
      hint.hidden = false;
      return;
    }
    zoneRequest?.abort();
    zoneRequest = new AbortController();
    const bounds = map.getBounds();
    const params = new URLSearchParams({
      sur: bounds.getSouth().toFixed(5), oeste: bounds.getWest().toFixed(5), norte: bounds.getNorth().toFixed(5),
      este: bounds.getEast().toFixed(5), tipo: activeType,
    });
    try {
      const response = await fetch(`/api/v1/lugares/?${params}`, {signal: zoneRequest.signal});
      if (!response.ok) throw new Error();
      const data = await response.json();
      draw(data.resultados);
      hint.textContent = data.truncado ? 'Hay más lugares aquí: acércate para verlos todos.'
        : data.resultados.length ? '' : 'No tenemos lugares de este tipo en esta zona.';
      hint.hidden = !hint.textContent;
    } catch (error) {
      if (error.name === 'AbortError') return;
      hint.textContent = 'No pudimos cargar los lugares. Intenta de nuevo.';
      hint.hidden = false;
    }
  }
  map.on('moveend', () => {
    clearTimeout(zoneTimer);
    zoneTimer = setTimeout(loadZone, 250);
  });

  /* Cerca de mí */
  function showNearby(places, radius) {
    nearbyList.replaceChildren();
    nearbyStatus.textContent = places.length ? `${places.length} a menos de ${radius} km de ti.` : `No encontramos lugares a menos de ${radius} km.`;
    places.forEach(place => {
      const row = node('button', null, 'nearby-fila');
      row.type = 'button';
      const text = node('span');
      text.append(node('strong', place.nombre), node('small', place.subtipo_nombre));
      row.append(text, node('span', distanceText(place.distancia_km), 'nearby-distancia'));
      row.addEventListener('click', () => {
        const marker = markerByPlace.get(place.id);
        if (!marker) return;
        cluster.zoomToShowLayer ? cluster.zoomToShowLayer(marker, () => marker.openPopup()) : marker.openPopup();
        if (window.matchMedia('(max-width:860px)').matches) byId('map-panel').scrollIntoView({block: 'start', behavior: 'instant'});
      });
      nearbyList.append(row);
    });
  }
  async function askNearby() {
    nearbyStatus.textContent = 'Buscando lo más cercano…';
    nearbyPanel.hidden = false;
    hint.hidden = true;
    const ask = async radio => {
      const response = await fetch('/api/v1/lugares/cerca/', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({latitud: nearbyPoint[0], longitud: nearbyPoint[1], radio_km: radio, ...(activeType && {tipo: activeType})}),
      });
      if (!response.ok) throw new Error();
      return response.json();
    };
    try {
      // En un pueblo puede no haber nada a 5 km: entonces se amplía antes de responder que no hay.
      let data = await ask(5);
      if (!data.resultados.length) data = await ask(25);
      draw(data.resultados);
      showNearby(data.resultados, data.radio_km);
      const points = [nearbyPoint, ...data.resultados.slice(0, 15).map(place => [Number(place.latitud), Number(place.longitud)])];
      map.fitBounds(points, {padding: [50, 50], maxZoom: 15});
    } catch {
      nearbyStatus.textContent = 'No pudimos buscar lugares cercanos. Intenta de nuevo.';
    }
  }
  nearbyButton.addEventListener('click', () => {
    if (!navigator.geolocation) { nearbyPanel.hidden = false; nearbyStatus.textContent = 'Tu navegador no ofrece ubicación.'; return; }
    nearbyButton.disabled = true;
    nearbyPanel.hidden = false;
    nearbyList.replaceChildren();
    nearbyStatus.textContent = 'Esperando tu ubicación…';
    navigator.geolocation.getCurrentPosition(position => {
      nearbyButton.disabled = false;
      nearbyButton.setAttribute('aria-pressed', 'true');
      nearbyPoint = [position.coords.latitude, position.coords.longitude];
      if (userLayer) map.removeLayer(userLayer);
      userLayer = L.circleMarker(nearbyPoint, {radius: 7, className: 'mi-ubicacion'}).bindTooltip('Tu ubicación aproximada').addTo(map);
      askNearby();
    }, error => {
      nearbyButton.disabled = false;
      nearbyStatus.textContent = error.code === 1
        ? 'No diste permiso para usar tu ubicación. Puedes mover el mapa y elegir un tipo de lugar.'
        : 'No pudimos obtener tu ubicación. Intenta otra vez o mueve el mapa.';
    }, {enableHighAccuracy: false, timeout: 10000, maximumAge: 60000});
  });
  byId('nearby-close').addEventListener('click', () => {
    nearbyPoint = null;
    nearbyPanel.hidden = true;
    nearbyButton.setAttribute('aria-pressed', 'false');
    if (userLayer) { map.removeLayer(userLayer); userLayer = null; }
    loadZone();
  });

  typeButtons.forEach(button => button.addEventListener('click', () => {
    activeType = activeType === button.dataset.lugarTipo ? '' : button.dataset.lugarTipo;
    typeButtons.forEach(other => other.setAttribute('aria-pressed', String(other.dataset.lugarTipo === activeType)));
    if (nearbyPoint) askNearby();
    else loadZone();
  }));

  // Enlace "Ver qué hay cerca" de la portada: la persona acaba de pedirlo.
  if (location.hash === '#cerca') nearbyButton.click();
})();
