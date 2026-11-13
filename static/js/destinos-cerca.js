// Explorar sin búsqueda: los destinos más cercanos a la persona, arriba de la lista.
// La distancia se calcula aquí con los puntos que ya pidió el mapa (mapa.js). La ubicación se usa una vez y se descarta:
// no se envía al servidor ni se escribe en la URL, en localStorage ni en ningún registro.
(async () => {
  'use strict';
  const MAXIMO = 8; // Lo mismo que una página de la lista: cabe sin tapar el resto.
  const LEJOS_KM = 150;
  const byId = id => document.getElementById(id);
  const section = byId('cerca-destinos');
  if (!section || !window.InfoTripPuntos || !navigator.geolocation) return;
  let places;
  try { places = await window.InfoTripPuntos; } catch { return; } // mapa.js ya avisa que no llegaron.
  places = places
    .map(place => ({...place, lat: Number(place.latitud), lng: Number(place.longitud)}))
    .filter(place => Number.isFinite(place.lat) && Number.isFinite(place.lng));
  if (!places.length) return;

  const title = byId('cerca-destinos-titulo');
  const ask = byId('cerca-destinos-pedir');
  const status = byId('cerca-destinos-estado');
  const list = byId('cerca-destinos-lista');
  const note = byId('cerca-destinos-nota');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let shown = false, waiting = false, userLayer = null;

  function haversineKm(lat1, lng1, lat2, lng2) {
    const rad = Math.PI / 180;
    const dLat = (lat2 - lat1) * rad, dLng = (lng2 - lng1) * rad;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLng / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(a)));
  }
  function distanceText(km) {
    if (km < 1) return 'a menos de 1 km';
    return km < 10 ? `${km.toFixed(1)} km` : `${Math.round(km).toLocaleString('es-MX')} km`;
  }
  function node(tag, text, className) {
    const el = document.createElement(tag);
    if (text) el.textContent = text;
    if (className) el.className = className;
    return el;
  }
  // La misma tarjeta que la lista del servidor (destinos/tarjetas.html), con la distancia junto al municipio.
  function card(place) {
    const link = node('a', null, 'trip-card');
    link.href = place.url;
    link.dataset.slug = place.slug;
    if (place.miniatura_url) {
      const img = node('img');
      Object.assign(img, {src: place.miniatura_url, alt: '', width: 800, height: 480, loading: 'lazy', decoding: 'async'});
      link.append(img);
    } else {
      const placeholder = node('div', null, 'photo-placeholder');
      placeholder.setAttribute('aria-hidden', 'true');
      placeholder.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21zM12 11.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"/></svg>';
      link.append(placeholder);
    }
    const caption = node('div', null, 'trip-card-caption');
    caption.append(
      node('h3', place.nombre),
      node('span', `${place.municipio} · ${distanceText(place.km)}`, 'trip-distancia'),
      node('span', place.categoria, 'trip-tag'),
    );
    link.append(caption);
    return link;
  }

  function show(point) {
    const nearest = places
      .map(place => ({...place, km: haversineKm(point[0], point[1], place.lat, place.lng)}))
      .sort((a, b) => a.km - b.km)
      .slice(0, MAXIMO);
    list.replaceChildren(...nearest.map(card));
    note.hidden = false;
    ask.hidden = true;
    shown = true;
    const far = nearest[0].km > LEJOS_KM;
    status.textContent = far
      ? `Estás a más de ${LEJOS_KM} km de los destinos que tenemos. Estos son los ${nearest.length} más cercanos.`
      : `Te mostramos los ${nearest.length} destinos más cercanos a ti. Abajo sigue la lista completa.`;
    centerMap(point, nearest);
  }

  function centerMap(point, nearest) {
    const map = window.InfoTripExplorador?.map;
    if (!map || !window.L) return;
    // Si la persona abrió "Cerca de mí" (servicios), el mapa ya muestra lo que pidió: no se le mueve.
    if (byId('nearby-panel') && !byId('nearby-panel').hidden) return;
    if (userLayer) map.removeLayer(userLayer);
    userLayer = L.circleMarker(point, {radius: 7, className: 'mi-ubicacion'}).bindTooltip('Tu ubicación aproximada').addTo(map);
    const bounds = [point, ...nearest.slice(0, 5).map(place => [place.lat, place.lng])];
    map.fitBounds(bounds, {padding: [50, 50], maxZoom: 12, animate: !reduceMotion.matches});
  }

  function failed(error) {
    waiting = false;
    list.replaceChildren();
    if (error && error.code === 1) {
      ask.hidden = true;
      status.textContent = 'No diste permiso para usar tu ubicación, así que te mostramos todos los destinos. '
        + 'Si cambias de opinión, puedes permitirlo en la configuración del navegador.';
    } else {
      ask.hidden = false;
      ask.querySelector('strong').textContent = 'Intentar otra vez';
      status.textContent = 'No pudimos obtener tu ubicación. Abajo están todos los destinos.';
    }
  }

  function locate({fromButton = false} = {}) {
    if (waiting || shown) return;
    waiting = true;
    ask.disabled = true;
    status.textContent = 'Buscando destinos cerca de ti…';
    navigator.geolocation.getCurrentPosition(position => {
      waiting = false;
      ask.disabled = false;
      show([position.coords.latitude, position.coords.longitude]);
      // El botón desaparece al responder: el foco pasa al título de la sección para no perderse.
      if (fromButton) title.focus();
    }, error => {
      ask.disabled = false;
      failed(error);
      if (fromButton && ask.hidden) title.focus();
    }, {enableHighAccuracy: false, timeout: 10000, maximumAge: 300000});
  }

  ask.addEventListener('click', () => locate({fromButton: true}));

  async function permission() {
    try {
      if (!navigator.permissions?.query) return null;
      return await navigator.permissions.query({name: 'geolocation'});
    } catch {
      return null;
    }
  }

  (async () => {
    const result = await permission();
    section.hidden = false;
    const state = result ? result.state : 'prompt';
    if (state === 'granted') locate();
    else if (state === 'denied') failed({code: 1});
    else ask.hidden = false;
    // Si la persona da permiso desde otro botón (Mi ubicación, Cerca de mí), la lista se ordena sola.
    if (result) result.addEventListener('change', () => { if (result.state === 'granted') locate(); });
  })();
})();
