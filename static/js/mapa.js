(() => {
  const panel = document.getElementById('map-panel');
  const toggle = document.getElementById('toggle-map');
  const status = document.getElementById('map-status');
  const places = JSON.parse(document.getElementById('map-places').textContent);
  const markers = new Map();
  let map, locationLayer;
  toggle.hidden = false;
  function fit() {
    const points = [...markers.values()].map(marker => marker.getLatLng());
    if (points.length) map.fitBounds(points, {padding: [35, 35], maxZoom: 13});
    else map.setView([20.65, -103.8], 8);
  }
  function openMap() {
    panel.hidden = false;
    toggle.textContent = 'Ocultar mapa';
    toggle.setAttribute('aria-expanded', 'true');
    if (!window.L) {
      status.textContent = 'No se pudo cargar el mapa. Revisa tu conexión y recarga la página; los detalles siguen disponibles.';
      document.getElementById('locate-me').disabled = true;
      document.getElementById('fit-results').disabled = true;
      return false;
    }
    if (!map) {
      map = L.map('destinations-map', {scrollWheelZoom: false});
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      }).on('tileerror', () => {
        status.textContent = 'El fondo del mapa no está disponible. Puedes seguir abriendo los marcadores y las fichas.';
      }).addTo(map);
      places.forEach(place => {
        const lat = Number(place.latitud), lng = Number(place.longitud);
        if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) return;
        const popup = document.createElement('div');
        const title = document.createElement('strong'); title.textContent = place.nombre;
        const text = document.createElement('p'); text.textContent = place.municipio;
        const link = document.createElement('a'); link.href = place.url; link.textContent = 'Ver destino →';
        popup.append(title, text, link);
        const marker = L.marker([lat, lng], {title: place.nombre, alt: place.nombre}).addTo(map).bindPopup(popup);
        marker.on('click', () => {status.textContent = `Seleccionaste ${place.nombre}.`;});
        markers.set(place.slug, marker);
      });
      fit();
      if (!markers.size) status.textContent = 'No hay destinos con coordenadas en esta página. Prueba otros filtros o consulta las fichas disponibles.';
    }
    map.invalidateSize();
    return true;
  }
  toggle.addEventListener('click', () => {
    if (panel.hidden) openMap();
    else {
      panel.hidden = true;
      toggle.textContent = 'Ver mapa';
      toggle.setAttribute('aria-expanded', 'false');
    }
  });
  document.querySelectorAll('[data-map-slug]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', () => {
      if (!openMap()) return;
      const marker = markers.get(button.dataset.mapSlug);
      if (!marker) return;
      map.setView(marker.getLatLng(), 14); marker.openPopup();
      panel.scrollIntoView({behavior: 'instant', block: 'start'});
      status.textContent = `Mostrando ${button.textContent.replace('Ubicar ', '')}.`;
    });
  });
  document.getElementById('fit-results').addEventListener('click', fit);
  const locate = document.getElementById('locate-me');
  locate.addEventListener('click', () => {
    if (!navigator.geolocation) { status.textContent = 'Tu navegador no ofrece ubicación. Busca un municipio con los filtros.'; return; }
    locate.disabled = true;
    status.textContent = 'Esperando tu ubicación…';
    navigator.geolocation.getCurrentPosition(position => {
      locate.disabled = false;
      if (locationLayer) map.removeLayer(locationLayer);
      const point = [position.coords.latitude, position.coords.longitude];
      locationLayer = L.featureGroup([
        L.circle(point, {radius: position.coords.accuracy, color: '#6741d9'}),
        L.marker(point, {title: 'Tu ubicación aproximada'}).bindPopup('Tu ubicación aproximada')
      ]).addTo(map);
      map.setView(point, 13);
      status.textContent = 'Ubicación aproximada. No se guarda en tu cuenta ni filtra los resultados.';
    }, error => {
      locate.disabled = false;
      status.textContent = error.code === 1 ? 'No permitiste el acceso a tu ubicación. Puedes buscar un municipio manualmente.' : 'No pudimos obtener tu ubicación. Intenta otra vez o busca un municipio.';
    }, {enableHighAccuracy: false, timeout: 10000, maximumAge: 60000});
  });
})();
