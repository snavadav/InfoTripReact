(() => {
  const list = document.getElementById('favorites-list');
  const status = document.getElementById('favorites-status');
  const more = document.getElementById('favorites-more');
  let next = null;

  function node(tag, text) {
    const el = document.createElement(tag);
    if (text) el.textContent = text;
    return el;
  }

  function link(text, url) {
    const el = node('a', text);
    el.href = url;
    return el;
  }

  // Formulario para vincular el favorito a una escapada guardada.
  function tripForm(item, feedback) {
    const form = node('form');
    form.className = 'community-form';
    const label = node('label', 'Agregar a una escapada guardada');
    const select = node('select');
    select.required = true;
    select.append(new Option('Cargar mis escapadas…', ''));
    label.append(select);

    const load = node('button', 'Cargar escapadas');
    load.type = 'button';
    let tripsNext = '/api/v1/mis-viajes/';
    load.addEventListener('click', async () => {
      load.disabled = true;
      try {
        const data = await InfoTrip.api(tripsNext);
        data.results.forEach(viaje => select.append(new Option(viaje.nombre, String(viaje.id))));
        tripsNext = data.next;
        load.hidden = !tripsNext;
        load.textContent = 'Cargar más escapadas';
        if (select.options.length === 1) feedback.textContent = 'Primero crea y guarda una escapada en Mis viajes.';
      } catch (error) {
        feedback.textContent = error.message;
      } finally {
        load.disabled = false;
      }
    });

    const save = node('button', 'Agregar lugar');
    save.type = 'submit';
    const state = node('p');
    state.className = 'form-status';
    state.setAttribute('role', 'status');
    form.append(label, load, save, state);

    form.addEventListener('submit', event => {
      event.preventDefault();
      InfoTrip.submit(form, async message => {
        await InfoTrip.api(`/api/v1/mis-viajes/${select.value}/lugares/`, {method: 'POST', body: {slug: item.slug}});
        message.textContent = 'Lugar agregado. Lo encontrarás en Mis viajes.';
      });
    });
    return form;
  }

  function render(item) {
    const card = node('article');
    card.className = 'community-box';
    card.append(node('h2', item.nombre));
    const feedback = node('p');
    feedback.setAttribute('role', 'status');

    if (item.activo) {
      card.append(
        link('Ver destino →', `/destinos/${encodeURIComponent(item.slug)}/`),
        node('span', ' · '),
        link('Crear escapada aquí →', `/mis-viajes/?destino=${encodeURIComponent(item.nombre)}`),
      );
      card.append(tripForm(item, feedback));
    } else {
      card.append(node('p', 'Este destino ya no está disponible en el catálogo. Puedes quitarlo de tus favoritos.'));
    }

    const remove = node('button', 'Quitar de favoritos');
    remove.type = 'button';
    remove.addEventListener('click', async () => {
      remove.disabled = true;
      try {
        await InfoTrip.api(`/api/v1/favoritos/${encodeURIComponent(item.slug)}/`, {method: 'DELETE'});
        card.remove();
        if (!list.children.length) status.textContent = 'No hay favoritos en esta página. Explora destinos para guardar más.';
      } catch (error) {
        feedback.textContent = error.message;
        remove.disabled = false;
      }
    });
    card.append(remove, feedback);
    list.append(card);
  }

  async function load() {
    more.disabled = true;
    try {
      const data = await InfoTrip.api(next || '/api/v1/favoritos/');
      data.results.forEach(render);
      next = data.next;
      more.hidden = !next;
      if (!list.children.length) {
        status.textContent = 'Todavía no tienes favoritos. Abre la ficha de un destino y selecciona Guardar lugar.';
      }
    } catch (error) {
      status.textContent = error.message;
      document.getElementById('favorites-login').hidden = InfoTrip.hasSession();
    } finally {
      more.disabled = false;
    }
  }

  more.addEventListener('click', load);
  if (InfoTrip.hasSession()) load();
  else document.getElementById('favorites-login').hidden = false;
})();
