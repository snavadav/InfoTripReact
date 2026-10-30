// Explorador: el mapa muestra todos los resultados y el panel flotante, el lugar elegido.
(() => {
  'use strict';
  const places = JSON.parse(document.getElementById('map-places').textContent);
  const panel = document.getElementById('map-panel');
  const toggle = document.getElementById('toggle-map');
  const status = document.getElementById('map-status');
  const placePanel = document.getElementById('place-panel');
  const byId = id => document.getElementById(id);
  let map, cluster, markers = new Map(), current = null, locationLayer, routeLine;

  if (toggle) {
    toggle.hidden = false;
    toggle.addEventListener('click', () => {
      panel.classList.toggle('mapa-oculto');
      const hidden = panel.classList.contains('mapa-oculto');
      toggle.textContent = hidden ? 'Ver mapa' : 'Ocultar mapa';
      toggle.setAttribute('aria-expanded', String(!hidden));
      if (!hidden && map) map.invalidateSize();
    });
  }

  function fit() {
    const points = [...markers.values()].map(marker => marker.getLatLng());
    if (points.length) map.fitBounds(points, {padding: [40, 40], maxZoom: 13});
    else map.setView(InfoTripMapa.CENTRO_JALISCO, InfoTripMapa.ZOOM_JALISCO);
  }

  /* Panel del lugar */
  async function loadDescription(place) {
    const target = byId('place-description');
    target.textContent = '';
    try {
      const response = await fetch(`/api/v1/destinos/${encodeURIComponent(place.slug)}/`);
      if (response.ok && current === place) target.textContent = (await response.json()).descripcion;
    } catch { /* La descripción es opcional; la ficha sigue a un clic. */ }
  }
  let favorite = false;
  function showFavorite() {
    const button = byId('place-favorite');
    button.textContent = favorite ? 'Guardado' : 'Guardar';
    button.setAttribute('aria-pressed', String(favorite));
  }
  async function loadFavorite(place) {
    favorite = false;
    showFavorite();
    if (!InfoTrip.hasSession()) return;
    try {
      const data = await InfoTrip.api(`/api/v1/favoritos/${encodeURIComponent(place.slug)}/`);
      if (current === place) { favorite = data.favorito; showFavorite(); }
    } catch { /* Sin estado se muestra como no guardado. */ }
  }
  function select(place, marker, {move = true} = {}) {
    if (current) markers.get(current.slug)?.setIcon(InfoTripMapa.icono(current));
    current = place;
    marker.setIcon(InfoTripMapa.icono(place, true));
    marker.setZIndexOffset(1000);
    const show = () => { if (move) map.panTo(marker.getLatLng()); };
    if (cluster.zoomToShowLayer) cluster.zoomToShowLayer(marker, show);
    else show();
    const photo = byId('place-photo');
    photo.hidden = !place.miniatura_url;
    if (place.miniatura_url) { photo.src = place.miniatura_url; photo.alt = ''; }
    byId('place-name').textContent = place.nombre;
    byId('place-where').textContent = `${place.municipio} · ${place.region}`;
    byId('place-category').textContent = place.categoria;
    byId('place-coordinates').textContent = InfoTripMapa.formatoCoordenadas(place.latitud, place.longitud);
    byId('place-detail').href = place.url;
    byId('place-directions').href = place.maps_url;
    byId('place-status').textContent = '';
    placePanel.hidden = false;
    document.querySelectorAll('.trip-card[aria-current]').forEach(card => card.removeAttribute('aria-current'));
    document.querySelector(`.trip-card[data-slug="${CSS.escape(place.slug)}"]`)?.setAttribute('aria-current', 'true');
    status.textContent = `Seleccionaste ${place.nombre}.`;
    showRouteButton();
    loadDescription(place);
    loadFavorite(place);
  }
  function closePlace() {
    if (current) markers.get(current.slug)?.setIcon(InfoTripMapa.icono(current));
    current = null;
    placePanel.hidden = true;
    document.querySelectorAll('.trip-card[aria-current]').forEach(card => card.removeAttribute('aria-current'));
  }
  byId('place-close').addEventListener('click', closePlace);
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !placePanel.hidden) closePlace(); });

  byId('place-favorite').addEventListener('click', async () => {
    const feedback = byId('place-status');
    if (!InfoTrip.hasSession()) {
      feedback.replaceChildren(document.createTextNode('Entra para guardar este lugar. '));
      const link = document.createElement('a');
      link.href = InfoTrip.loginUrl();
      link.textContent = 'Iniciar sesión';
      feedback.append(link);
      return;
    }
    const button = byId('place-favorite');
    button.disabled = true;
    try {
      await InfoTrip.api(`/api/v1/favoritos/${encodeURIComponent(current.slug)}/`, {method: favorite ? 'DELETE' : 'PUT'});
      favorite = !favorite;
      showFavorite();
      feedback.textContent = favorite ? 'Guardado en tus favoritos.' : 'Quitado de tus favoritos.';
    } catch (error) { feedback.textContent = error.message; }
    finally { button.disabled = false; }
  });

  /* Recorrido: se guarda solo en este navegador. */
  const ROUTE_KEY = 'infotrip_recorrido', ROUTE_MAX = 10;
  function readRoute() {
    try { return JSON.parse(localStorage.getItem(ROUTE_KEY)) || []; } catch { return []; }
  }
  let route = readRoute();
  function saveRoute() {
    try { localStorage.setItem(ROUTE_KEY, JSON.stringify(route)); } catch { /* Sin espacio: dura esta página. */ }
    showRoute();
  }
  function showRouteButton() {
    if (!current) return;
    const included = route.some(stop => stop.slug === current.slug);
    const button = byId('place-route');
    button.textContent = included ? 'Quitar del recorrido' : 'Agregar al recorrido';
    button.setAttribute('aria-pressed', String(included));
  }
  function directions() {
    const stops = route.map(stop => `${stop.latitud},${stop.longitud}`);
    const params = new URLSearchParams({api: '1', destination: stops[stops.length - 1], travelmode: 'driving'});
    if (stops.length > 1) params.set('waypoints', stops.slice(0, -1).join('|'));
    return `https://www.google.com/maps/dir/?${params}`;
  }
  function showRoute() {
    const box = byId('route-panel');
    const list = byId('route-stops');
    box.hidden = !route.length;
    list.replaceChildren();
    route.forEach((stop, index) => {
      const item = document.createElement('li');
      const name = document.createElement('a');
      name.href = stop.url;
      name.textContent = stop.nombre;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '×';
      remove.setAttribute('aria-label', `Quitar ${stop.nombre} del recorrido`);
      remove.addEventListener('click', () => { route.splice(index, 1); saveRoute(); showRouteButton(); });
      item.append(name, remove);
      list.append(item);
    });
    byId('route-open').href = route.length ? directions() : '#';
    byId('route-trip').href = `/mis-viajes/?destino=${encodeURIComponent(route.map(stop => stop.nombre).join(', ').slice(0, 200))}`;
    if (map) {
      if (routeLine) map.removeLayer(routeLine);
      routeLine = null;
      if (route.length > 1) {
        routeLine = L.polyline(route.map(stop => [Number(stop.latitud), Number(stop.longitud)]), {className: 'linea-recorrido', interactive: false}).addTo(map);
      }
    }
  }
  byId('place-route').addEventListener('click', () => {
    const index = route.findIndex(stop => stop.slug === current.slug);
    if (index >= 0) route.splice(index, 1);
    else if (route.length >= ROUTE_MAX) { byId('place-status').textContent = `Un recorrido admite hasta ${ROUTE_MAX} paradas.`; return; }
    else route.push({slug: current.slug, nombre: current.nombre, url: current.url, latitud: current.latitud, longitud: current.longitud});
    saveRoute();
    showRouteButton();
  });
  byId('route-clear').addEventListener('click', () => { route = []; saveRoute(); showRouteButton(); });
  byId('route-fit').addEventListener('click', () => {
    if (route.length) map.fitBounds(route.map(stop => [Number(stop.latitud), Number(stop.longitud)]), {padding: [60, 60], maxZoom: 14});
  });

  /* Mapa */
  if (!window.L) {
    status.textContent = 'No se pudo cargar el mapa. Revisa tu conexión y recarga la página; las fichas siguen disponibles.';
    byId('locate-me').disabled = true;
    byId('fit-results').disabled = true;
    return;
  }
  map = InfoTripMapa.crear('destinations-map', {
    alFallarFondo: () => { status.textContent = 'El fondo del mapa no está disponible. Puedes seguir abriendo los marcadores y las fichas.'; },
  });
  cluster = InfoTripMapa.agrupador().addTo(map);
  markers = InfoTripMapa.agregarPuntos(cluster, places, (place, marker) => select(place, marker, {move: false}));
  fit();
  showRoute();
  if (!markers.size) status.textContent = 'No hay destinos con coordenadas en estos resultados. Prueba otros filtros.';

  // Una tarjeta ubica el lugar en el mapa; con Ctrl, Cmd o sin mapa sigue siendo un enlace a la ficha.
  const bySlug = new Map(places.map(place => [place.slug, place]));
  document.querySelectorAll('.trip-card[data-slug]').forEach(card => card.addEventListener('click', event => {
    const place = bySlug.get(card.dataset.slug), marker = markers.get(card.dataset.slug);
    if (!place || !marker || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    select(place, marker);
    if (panel.classList.contains('mapa-oculto')) toggle.click();
    // En móvil la lista queda debajo del mapa: se vuelve a él para ver el lugar elegido.
    if (window.matchMedia('(max-width:860px)').matches) panel.scrollIntoView({block: 'start', behavior: 'instant'});
  }));

  byId('fit-results').addEventListener('click', fit);
  const locate = byId('locate-me');
  locate.addEventListener('click', () => {
    if (!navigator.geolocation) { status.textContent = 'Tu navegador no ofrece ubicación. Busca un municipio con los filtros.'; return; }
    locate.disabled = true;
    status.textContent = 'Esperando tu ubicación…';
    navigator.geolocation.getCurrentPosition(position => {
      locate.disabled = false;
      if (locationLayer) map.removeLayer(locationLayer);
      const point = [position.coords.latitude, position.coords.longitude];
      locationLayer = L.featureGroup([
        L.circle(point, {radius: position.coords.accuracy, className: 'mi-ubicacion-radio'}),
        L.circleMarker(point, {radius: 7, className: 'mi-ubicacion'}).bindTooltip('Tu ubicación aproximada'),
      ]).addTo(map);
      map.setView(point, 13);
      status.textContent = 'Ubicación aproximada. No se guarda en tu cuenta ni filtra los resultados.';
    }, error => {
      locate.disabled = false;
      status.textContent = error.code === 1 ? 'No permitiste el acceso a tu ubicación. Puedes buscar un municipio manualmente.' : 'No pudimos obtener tu ubicación. Intenta otra vez o busca un municipio.';
    }, {enableHighAccuracy: false, timeout: 10000, maximumAge: 60000});
  });
})();
