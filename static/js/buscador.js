// Autocompletado del campo de búsqueda (patrón combobox de ARIA 1.2, lista emergente).
// Mejora progresiva: sin JavaScript el formulario sigue buscando igual. Se activa en cualquier
// <input data-autocompletar="URL">. Elegir una opción abre su página; Intro sin opción activa envía la búsqueda.
(() => {
  const ESPERA_MS = 250;
  const MINIMO = 2;
  const TIPOS = { coleccion: 'Colección', categoria: 'Categoría', municipio: 'Municipio', destino: 'Destino', lugar: 'Lugar' };
  let contador = 0;

  document.querySelectorAll('input[data-autocompletar]').forEach(input => {
    const url = input.dataset.autocompletar;
    const id = `buscador-opciones-${++contador}`;
    const ancla = input.parentElement;
    ancla.classList.add('buscador-ancla');

    const lista = document.createElement('ul');
    lista.id = id;
    lista.className = 'buscador-opciones';
    lista.setAttribute('role', 'listbox');
    lista.setAttribute('aria-label', 'Sugerencias');
    lista.hidden = true;
    ancla.appendChild(lista);

    const estado = document.createElement('p');
    estado.className = 'sr-only';
    estado.setAttribute('role', 'status');
    ancla.appendChild(estado);

    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-controls', id);
    input.setAttribute('autocomplete', 'off');

    const cache = new Map();
    let opciones = [];
    let activa = -1;
    let temporizador;
    let peticion;

    function cerrar() {
      lista.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
      activa = -1;
    }

    function marcar(indice) {
      activa = indice;
      opciones.forEach((opcion, i) => opcion.setAttribute('aria-selected', String(i === indice)));
      if (indice < 0) { input.removeAttribute('aria-activedescendant'); return; }
      input.setAttribute('aria-activedescendant', opciones[indice].id);
      opciones[indice].scrollIntoView({ block: 'nearest' });
    }

    function pintar(datos, texto) {
      lista.replaceChildren();
      opciones = [];
      activa = -1;
      const resultados = datos.resultados || [];
      if (!resultados.length && datos.sugerencia) {
        resultados.push({ tipo: 'sugerencia', nombre: datos.sugerencia, detalle: '¿Quisiste decir…?',
          url: `${input.form.action}?${new URLSearchParams({ q: datos.sugerencia })}` });
      }
      resultados.forEach((resultado, i) => {
        const opcion = document.createElement('li');
        opcion.id = `${id}-${i}`;
        opcion.setAttribute('role', 'option');
        opcion.setAttribute('aria-selected', 'false');
        opcion.dataset.url = resultado.url;
        const nombre = document.createElement('span');
        nombre.className = 'buscador-nombre';
        nombre.textContent = resultado.nombre;
        const detalle = document.createElement('span');
        detalle.className = 'buscador-detalle';
        const tipo = TIPOS[resultado.tipo];
        detalle.textContent = tipo && tipo !== resultado.detalle && !resultado.detalle.startsWith(tipo)
          ? `${tipo} · ${resultado.detalle}` : resultado.detalle;
        opcion.append(nombre, detalle);
        lista.appendChild(opcion);
        opciones.push(opcion);
      });
      const hay = opciones.length > 0 && input.value.trim() === texto;
      lista.hidden = !hay;
      input.setAttribute('aria-expanded', String(hay));
      estado.textContent = hay
        ? `${opciones.length} sugerencia${opciones.length === 1 ? '' : 's'}. Usa las flechas para elegir.`
        : '';
    }

    async function consultar(texto) {
      if (cache.has(texto)) { pintar(cache.get(texto), texto); return; }
      peticion?.abort();
      peticion = new AbortController();
      try {
        const respuesta = await fetch(`${url}?${new URLSearchParams({ q: texto })}`, {
          headers: { Accept: 'application/json' }, signal: peticion.signal,
        });
        if (!respuesta.ok) { cerrar(); return; }
        const datos = await respuesta.json();
        cache.set(texto, datos);
        pintar(datos, texto);
      } catch (error) {
        if (error.name !== 'AbortError') cerrar();
      }
    }

    input.addEventListener('input', () => {
      clearTimeout(temporizador);
      const texto = input.value.trim();
      if (texto.length < MINIMO) { peticion?.abort(); cerrar(); estado.textContent = ''; return; }
      temporizador = setTimeout(() => consultar(texto), ESPERA_MS);
    });

    input.addEventListener('keydown', event => {
      const abierta = !lista.hidden && opciones.length > 0;
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        if (!abierta) {
          const texto = input.value.trim();
          if (cache.has(texto)) pintar(cache.get(texto), texto);
          return;
        }
        event.preventDefault();
        // Recorre las opciones y vuelve al campo (-1) al pasar del final o del principio.
        let siguiente = activa + (event.key === 'ArrowDown' ? 1 : -1);
        if (siguiente >= opciones.length) siguiente = -1;
        else if (siguiente < -1) siguiente = opciones.length - 1;
        marcar(siguiente);
      } else if (event.key === 'Enter' && abierta && activa >= 0) {
        event.preventDefault();
        window.location.assign(opciones[activa].dataset.url);
      } else if (event.key === 'Escape' && abierta) {
        event.preventDefault();
        event.stopPropagation();
        cerrar();
      } else if (event.key === 'Tab') {
        cerrar();
      }
    });

    // mousedown y no click: así el campo no pierde el foco antes de elegir.
    lista.addEventListener('mousedown', event => event.preventDefault());
    lista.addEventListener('click', event => {
      const opcion = event.target.closest('[role="option"]');
      if (opcion) window.location.assign(opcion.dataset.url);
    });
    input.addEventListener('blur', cerrar);
    input.addEventListener('focus', () => {
      const texto = input.value.trim();
      if (cache.has(texto)) pintar(cache.get(texto), texto);
    });
  });
})();
