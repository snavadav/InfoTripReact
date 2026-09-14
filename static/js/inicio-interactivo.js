(() => {
  const data = document.getElementById('home-places');
  if (!data) return;
  const places = JSON.parse(data.textContent);
  let filtered = [...places];
  let selected = 0;
  let mapMode = false;
  const byId = id => document.getElementById(id);
  const cards = byId('discovery-cards');
  const image = byId('preview-image');
  const map = byId('preview-map');
  function updateVisual(place) {
    image.hidden = mapMode || !place.foto_url;
    byId('preview-placeholder').hidden = mapMode || Boolean(place.foto_url);
    map.hidden = !mapMode;
    if (mapMode && map.getAttribute('src') !== place.mapa_embed) map.src = place.mapa_embed;
    map.title = `Mapa de ${place.nombre}; permite acercar y mover la vista`;
    byId('photo-mode').setAttribute('aria-pressed', String(!mapMode));
    byId('map-mode').setAttribute('aria-pressed', String(mapMode));
    byId('preview-label').hidden = mapMode;
  }
  function select(index) {
    if (!filtered.length) return;
    selected = (index + filtered.length) % filtered.length;
    const place = filtered[selected];
    if (place.foto_url) image.src = place.foto_url;
    else image.removeAttribute('src');
    image.alt = place.alt || `Fotografía de ${place.nombre}`;
    byId('preview-name').textContent = place.nombre;
    byId('preview-description').textContent = place.descripcion;
    byId('preview-label').textContent = place.editorial ? 'INSPIRACIÓN · JALISCO' : `${place.municipio} · Jalisco`;
    byId('preview-detail').href = place.url;
    byId('preview-directions').href = place.maps_url;
    byId('selection-position').textContent = `${selected + 1} de ${filtered.length} · ${place.nombre}`;
    [...cards.children].forEach((card, i) => card.setAttribute('aria-pressed', String(i === selected)));
    const activeCard = cards.children[selected];
    if (activeCard) {
      const viewport = cards.getBoundingClientRect();
      const bounds = activeCard.getBoundingClientRect();
      if (window.matchMedia('(max-width:600px)').matches) {
        if (bounds.left < viewport.left || bounds.right > viewport.right) cards.scrollBy({left: bounds.left - viewport.left, behavior: 'instant'});
      } else if (bounds.top < viewport.top || bounds.bottom > viewport.bottom) {
        cards.scrollBy({top: bounds.top - viewport.top, behavior: 'instant'});
      }
    }
    updateVisual(place);
  }
  function render() {
    cards.replaceChildren();
    byId('discovery-board').hidden = !filtered.length;
    byId('discovery-empty').hidden = Boolean(filtered.length);
    byId('surprise-place').disabled = filtered.length < 2;
    byId('previous-place').disabled = filtered.length < 2;
    byId('next-place').disabled = filtered.length < 2;
    byId('selection-count').textContent = `${filtered.length} ${filtered.length === 1 ? 'lugar para explorar' : 'lugares para explorar'}`;
    filtered.forEach((place, i) => {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'discovery-card';
      card.setAttribute('aria-label', `Explorar ${place.nombre}`);
      if (place.foto_url) {
        const photo = document.createElement('img');
        photo.src = place.foto_url;
        photo.alt = '';
        photo.loading = 'lazy';
        card.append(photo);
      }
      const caption = document.createElement('span');
      const category = document.createElement('small');
      category.textContent = place.categoria;
      const name = document.createElement('strong');
      name.textContent = place.nombre;
      const hint = document.createElement('small');
      hint.textContent = place.editorial ? 'Inspiración de viaje ↗' : `${place.municipio} ↗`;
      caption.append(category, name, hint);
      card.append(caption);
      card.addEventListener('click', () => select(i));
      cards.append(card);
    });
    select(0);
  }
  document.querySelectorAll('[data-category]').forEach(button => button.addEventListener('click', () => {
    filtered = places.filter(place => !button.dataset.category || place.categorias.includes(button.dataset.category));
    document.querySelectorAll('[data-category]').forEach(other => other.setAttribute('aria-pressed', String(other === button)));
    render();
  }));
  byId('previous-place').addEventListener('click', () => select(selected - 1));
  byId('next-place').addEventListener('click', () => select(selected + 1));
  byId('surprise-place').addEventListener('click', () => select(selected + 1 + Math.floor(Math.random() * (filtered.length - 1))));
  byId('map-mode').addEventListener('click', () => { mapMode = true; select(selected); });
  byId('photo-mode').addEventListener('click', () => { mapMode = false; select(selected); });
  document.querySelectorAll('[data-info]').forEach(button => button.addEventListener('click', () => {
    byId('app-info').textContent = button.dataset.info;
    document.querySelectorAll('[data-info]').forEach(other => other.setAttribute('aria-pressed', String(other === button)));
  }));
  render();
  const photoChoices = filtered.map((place, index) => place.foto_url ? index : -1).filter(index => index >= 0);
  if (photoChoices.length) select(photoChoices[Math.floor(Math.random() * photoChoices.length)]);
  else if (filtered.length > 1) select(Math.floor(Math.random() * filtered.length));
})();
