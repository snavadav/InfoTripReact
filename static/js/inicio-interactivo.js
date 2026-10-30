(() => {
  const data = document.getElementById('home-places');
  if (!data) return;
  const places = JSON.parse(data.textContent);
  const points = JSON.parse(document.getElementById('home-points').textContent);
  let filtered = [...places];
  let selected = 0;
  let mapMode = false;
  const byId = id => document.getElementById(id);
  const cards = byId('discovery-cards');
  const image = byId('preview-image');
  const map = byId('preview-map');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let bigMap = null, cluster = null, markers = new Map(), activeSlug = null;

  function popupFor(point) {
    const popup = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = point.nombre;
    const text = document.createElement('p');
    text.textContent = point.municipio;
    const link = document.createElement('a');
    link.href = point.url;
    link.textContent = 'Ver ficha →';
    popup.append(title, text, link);
    return popup;
  }
  function drawPins() {
    if (!bigMap) return;
    cluster.clearLayers();
    activeSlug = null;
    const choice = document.querySelector('[data-category][aria-pressed="true"]')?.dataset.category;
    const visible = points.filter(point => !choice || point.categorias.includes(choice));
    markers = InfoTripMapa.agregarPuntos(cluster, visible, (point, marker) => {
      const index = filtered.findIndex(place => place.slug === point.slug);
      if (index >= 0) select(index, {move: false});
      else marker.bindPopup(popupFor(point)).openPopup();
    });
  }
  function highlight(place, move) {
    if (!bigMap) return;
    if (activeSlug && markers.has(activeSlug)) {
      markers.get(activeSlug).setIcon(InfoTripMapa.icono(points.find(point => point.slug === activeSlug)));
    }
    const marker = markers.get(place.slug), point = points.find(item => item.slug === place.slug);
    activeSlug = marker ? place.slug : null;
    if (!marker) return;
    marker.setIcon(InfoTripMapa.icono(point, true));
    marker.setZIndexOffset(1000);
    if (move) cluster.zoomToShowLayer ? cluster.zoomToShowLayer(marker) : bigMap.panTo(marker.getLatLng(), {animate: !reducedMotion});
  }
  function updateVisual(place) {
    image.hidden = mapMode || !place.foto_url;
    byId('preview-placeholder').hidden = mapMode || Boolean(place.foto_url);
    map.hidden = !mapMode;
    if (mapMode && map.getAttribute('src') !== place.mapa_embed) map.src = place.mapa_embed;
    map.title = `Mapa de ${place.nombre}; permite acercar y mover la vista`;
    byId('photo-mode').setAttribute('aria-pressed', String(!mapMode));
    byId('map-mode').setAttribute('aria-pressed', String(mapMode));
  }
  function select(index, {move = true} = {}) {
    if (!filtered.length) return;
    selected = (index + filtered.length) % filtered.length;
    const place = filtered[selected];
    if (place.foto_url) image.src = place.foto_url;
    else image.removeAttribute('src');
    image.alt = place.alt || `Fotografía de ${place.nombre}`;
    byId('preview-name').textContent = place.nombre;
    byId('preview-description').textContent = place.descripcion;
    byId('preview-label').textContent = place.editorial ? 'Inspiración · Jalisco' : `${place.municipio} · ${place.categoria}`;
    byId('preview-detail').href = place.url;
    byId('preview-directions').href = place.maps_url;
    byId('selection-position').textContent = `${selected + 1} de ${filtered.length} · ${place.nombre}`;
    [...cards.children].forEach((card, i) => card.setAttribute('aria-pressed', String(i === selected)));
    const activeCard = cards.children[selected];
    if (activeCard) {
      const viewport = cards.getBoundingClientRect();
      const bounds = activeCard.getBoundingClientRect();
      if (window.matchMedia('(max-width:860px)').matches) {
        if (bounds.left < viewport.left || bounds.right > viewport.right) cards.scrollTo({left: cards.scrollLeft + bounds.left - viewport.left, behavior: 'instant'});
      } else if (bounds.top < viewport.top || bounds.bottom > viewport.bottom) {
        cards.scrollBy({top: bounds.top - viewport.top, behavior: 'instant'});
      }
    }
    updateVisual(place);
    highlight(place, move);
  }
  function render() {
    cards.replaceChildren();
    byId('discovery-board').hidden = !filtered.length;
    byId('place-preview').hidden = !filtered.length;
    byId('discovery-empty').hidden = Boolean(filtered.length);
    byId('surprise-place').disabled = filtered.length < 2;
    byId('previous-place').disabled = filtered.length < 2;
    byId('next-place').disabled = filtered.length < 2;
    byId('selection-count').textContent = `${filtered.length} ${filtered.length === 1 ? 'lugar destacado' : 'lugares destacados'}`;
    filtered.forEach((place, i) => {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'discovery-card';
      card.setAttribute('aria-label', `Explorar ${place.nombre}`);
      if (place.foto_url) {
        const photo = document.createElement('img');
        photo.src = place.miniatura_url;
        photo.alt = '';
        photo.loading = 'lazy';
        card.append(photo);
      }
      const caption = document.createElement('span');
      const name = document.createElement('strong');
      name.textContent = place.nombre;
      const hint = document.createElement('small');
      hint.textContent = place.editorial ? 'Inspiración de viaje' : `${place.municipio} · ${place.categoria}`;
      caption.append(name, hint);
      card.append(caption);
      card.addEventListener('click', () => select(i));
      cards.append(card);
    });
    drawPins();
    select(0, {move: false});
  }
  document.querySelectorAll('[data-category]').forEach(button => button.addEventListener('click', () => {
    filtered = places.filter(place => !button.dataset.category || place.categorias.includes(button.dataset.category));
    document.querySelectorAll('[data-category]').forEach(other => other.setAttribute('aria-pressed', String(other === button)));
    render();
  }));
  byId('previous-place').addEventListener('click', () => select(selected - 1));
  byId('next-place').addEventListener('click', () => select(selected + 1));
  byId('surprise-place').addEventListener('click', () => select(selected + 1 + Math.floor(Math.random() * (filtered.length - 1))));
  byId('map-mode').addEventListener('click', () => { mapMode = true; select(selected, {move: false}); });
  byId('photo-mode').addEventListener('click', () => { mapMode = false; select(selected, {move: false}); });

  // Sin el mapa grande (sin conexión a Leaflet) la portada sigue funcionando con la lista y la vista previa.
  if (window.L && window.InfoTripMapa) {
    bigMap = InfoTripMapa.crear('home-map', {rueda: false});
    bigMap.setView(InfoTripMapa.CENTRO_JALISCO, InfoTripMapa.ZOOM_JALISCO);
    cluster = InfoTripMapa.agrupador().addTo(bigMap);
  } else {
    byId('home-map').hidden = true;
  }
  render();
  const photoChoices = filtered.map((place, index) => place.foto_url ? index : -1).filter(index => index >= 0);
  if (photoChoices.length) select(photoChoices[Math.floor(Math.random() * photoChoices.length)], {move: false});
  else if (filtered.length > 1) select(Math.floor(Math.random() * filtered.length), {move: false});
})();
