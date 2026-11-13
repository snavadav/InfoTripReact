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
  // Cada botón lleva el mismo dibujo que sus marcas en el mapa: así se reconoce el tipo sin leyenda.
  typeButtons.forEach(button => {
    const trazo = InfoTripMapa.TRAZOS_LUGAR[button.dataset.lugarTipo];
    if (!trazo) return;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', trazo);
    svg.append(path);
    button.prepend(svg);
  });
  // Se pueden encender varios tipos a la vez.
  const active = new Set();
  let nearbyPoint = null, nearbyTurn = 0, userLayer = null, zoneRequest = null, zoneTimer = null;
  // Tipo → respuesta de "Cerca de mí" para la ubicación actual: encender otro tipo no vuelve a pedir los demás.
  let nearbyCache = new Map();
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
    } else if (place.atribucion) {
      box.append(node('p', place.atribucion, 'lugar-popup-credito'));
    }
    return box;
  }
  // Con `conservar`, solo cambia lo necesario: mover el mapa recarga la zona, y abrir un recuadro cerca
  // del borde mueve el mapa; si se redibujara todo, el recuadro se cerraría justo al abrirse.
  function draw(places, {conservar = false} = {}) {
    if (conservar) {
      const vigentes = new Set(places.map(place => place.id));
      markerByPlace.forEach((marker, id) => {
        if (vigentes.has(id) || marker.isPopupOpen()) return;
        cluster.removeLayer(marker);
        markerByPlace.delete(id);
      });
    } else {
      cluster.clearLayers();
      markerByPlace = new Map();
    }
    places.forEach(place => {
      const position = InfoTripMapa.coordenadas(place);
      if (!position || markerByPlace.has(place.id)) return;
      const marker = L.marker(position, {icon: InfoTripMapa.iconoLugar(place.tipo), title: place.nombre, alt: place.nombre});
      marker.bindPopup(() => details(place));
      markerByPlace.set(place.id, marker);
      cluster.addLayer(marker);
    });
  }

  /* Zona visible */
  async function loadZone() {
    // Una respuesta que llegara tarde volvería a pintar lo que ya se apagó.
    zoneRequest?.abort();
    if (nearbyPoint) return;
    if (!active.size) { draw([]); hint.hidden = true; return; }
    if (map.getZoom() < ZOOM_MINIMO) {
      draw([]);
      hint.textContent = 'Acércate en el mapa para ver estos lugares.';
      hint.hidden = false;
      return;
    }
    zoneRequest = new AbortController();
    const {signal} = zoneRequest;
    const bounds = map.getBounds();
    const zone = {
      sur: bounds.getSouth().toFixed(5), oeste: bounds.getWest().toFixed(5), norte: bounds.getNorth().toFixed(5),
      este: bounds.getEast().toFixed(5),
    };
    try {
      // Una petición por tipo: cada uno tiene su propio tope, y así los restaurantes no dejan fuera a los hoteles.
      const parts = await Promise.all([...active].map(async tipo => {
        const response = await fetch(`/api/v1/lugares/?${new URLSearchParams({...zone, tipo})}`, {signal});
        if (!response.ok) throw new Error();
        return response.json();
      }));
      if (signal.aborted) return;
      const places = parts.flatMap(part => part.resultados);
      draw(places, {conservar: true});
      hint.textContent = parts.some(part => part.truncado) ? 'Hay más lugares aquí: acércate para verlos todos.'
        : places.length ? '' : `No tenemos lugares de ${parts.length > 1 ? 'estos tipos' : 'este tipo'} en esta zona.`;
      hint.hidden = !hint.textContent;
    } catch (error) {
      if (error.name === 'AbortError' || signal.aborted) return;
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
    const turn = ++nearbyTurn;
    const ask = async (radio, tipo) => {
      const response = await fetch('/api/v1/lugares/cerca/', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({latitud: nearbyPoint[0], longitud: nearbyPoint[1], radio_km: radio, ...(tipo && {tipo})}),
      });
      if (!response.ok) throw new Error();
      return response.json();
    };
    const nearest = tipo => {
      if (!nearbyCache.has(tipo)) {
        const cache = nearbyCache;
        // En un pueblo puede no haber nada a 5 km: entonces se amplía antes de responder que no hay.
        const pending = ask(5, tipo).then(data => data.resultados.length ? data : ask(25, tipo));
        pending.catch(() => cache.delete(tipo));
        cache.set(tipo, pending);
      }
      return nearbyCache.get(tipo);
    };
    try {
      // Sin tipo elegido se busca de todo; con varios, lo más cercano de cada uno.
      const parts = await Promise.all((active.size ? [...active] : ['']).map(nearest));
      // Si mientras tanto se eligió otro tipo o se cerró el panel, manda la búsqueda más nueva.
      if (turn !== nearbyTurn || !nearbyPoint) return;
      const places = parts.flatMap(part => part.resultados).sort((a, b) => a.distancia_km - b.distancia_km || a.id - b.id);
      draw(places);
      showNearby(places, Math.max(...parts.map(part => part.radio_km)));
      const points = [nearbyPoint, ...places.slice(0, 15).map(place => [Number(place.latitud), Number(place.longitud)])];
      map.fitBounds(points, {padding: [50, 50], maxZoom: 15});
    } catch {
      if (turn !== nearbyTurn) return;
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
      nearbyCache = new Map();
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
    nearbyCache = new Map();
    nearbyPanel.hidden = true;
    nearbyButton.setAttribute('aria-pressed', 'false');
    if (userLayer) { map.removeLayer(userLayer); userLayer = null; }
    draw([]);
    loadZone();
  });

  typeButtons.forEach(button => button.addEventListener('click', () => {
    const tipo = button.dataset.lugarTipo;
    if (!active.delete(tipo)) active.add(tipo);
    button.setAttribute('aria-pressed', String(active.has(tipo)));
    // Un recuadro abierto conserva su marcador: se cierra para que el tipo apagado desaparezca completo.
    map.closePopup();
    if (nearbyPoint) askNearby();
    else loadZone();
  }));

  // Enlace "Ver qué hay cerca" de la portada: la persona acaba de pedirlo.
  if (location.hash === '#cerca') nearbyButton.click();
})();
