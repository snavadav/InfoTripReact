(() => {
  const cards = [...document.querySelectorAll('.home-place')];
  const featuredImage = document.getElementById('featured-image');
  if (!cards.length || !featuredImage) return;
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  let category = 'Todos';
  const query = document.getElementById('home-query');
  function filterCards() {
    let count = 0;
    cards.forEach(card => {
      const matches = (category === 'Todos' || card.dataset.category === category) && normalize(card.dataset.name).includes(normalize(query.value));
      card.hidden = !matches;
      if (matches) count++;
    });
    document.querySelectorAll('.home-filters button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.homeFilter === category)));
    document.getElementById('inspiration-empty').hidden = count > 0;
    document.getElementById('inspiration-status').textContent = `${count} ${count === 1 ? "lugar" : "lugares"} en esta selección.`;
  }
  document.querySelectorAll('[data-home-filter]').forEach(button => button.addEventListener('click', () => {
    category = button.dataset.homeFilter;
    query.value = '';
    filterCards();
  }));
  document.getElementById('inspiration-search').addEventListener('submit', event => {
    event.preventDefault();
    category = 'Todos';
    filterCards();
    document.getElementById('destinos').scrollIntoView({behavior: 'instant'});
  });
  query.addEventListener('input', filterCards);
  document.getElementById('change-feature').addEventListener('click', () => {
    const alternatives = cards.filter(card => card.dataset.name !== document.getElementById('featured-name').textContent);
    const selected = alternatives[Math.floor(Math.random() * alternatives.length)];
    if (!selected) return;
    const photo = selected.querySelector('img');
    featuredImage.src = photo.src;
    featuredImage.alt = photo.alt;
    document.getElementById('featured-name').textContent = selected.dataset.name;
    document.getElementById('featured-category').textContent = `${selected.dataset.category} · Jalisco`;
    document.getElementById('featured-phrase').textContent = selected.dataset.phrase;
    document.getElementById('feature-status').textContent = `Ahora se muestra ${selected.dataset.name}.`;
  });
  const dialog = document.getElementById('place-lightbox');
  cards.forEach(card => card.querySelector('button').addEventListener('click', () => {
    const photo = card.querySelector('img');
    const image = document.getElementById('lightbox-image');
    image.src = photo.src;
    image.alt = photo.alt;
    document.getElementById('lightbox-title').textContent = card.dataset.name;
    document.getElementById('lightbox-description').textContent = card.querySelector('.home-place-copy p').textContent;
    dialog.showModal();
  }));
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
})();
