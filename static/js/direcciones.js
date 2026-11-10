// Direcciones con OpenStreetMap (apps/destinos/direcciones.py): buscador con sugerencias y búsqueda inversa.
// El navegador solo llama a nuestra API; nunca a OpenStreetMap directamente.
//
// Uso:
//   const buscador = InfoTripDirecciones.conectar(input, {alElegir(direccion) {…}, boton, estado});
//   const direccion = await InfoTripDirecciones.inversa(lat, lon);  // null si no hay; lanza Error con mensaje amable
// `direccion` es {etiqueta, calle, colonia, municipio, estado, lat, lon}.
// Patrón combobox de ARIA 1.2 con lista emergente: flechas para recorrer, Intro para elegir o buscar la dirección
// completa, Escape para cerrar. Reutiliza los estilos de static/css/buscador.css.
(() => {
  'use strict';
  const API = '/api/v1/direcciones/';
  const ESPERA_MS = 300;
  const MINIMO = 3;
  const TIEMPO_MAXIMO_MS = 9000;
  const SIN_SERVICIO = 'No pudimos buscar direcciones ahora. Puedes marcar el punto directamente en el mapa.';
  const DEMASIADAS = 'Hiciste muchas búsquedas seguidas. Espera un momento o marca el punto en el mapa.';
  let contador = 0;

  async function pedir(ruta, parametros, senal) {
    const tiempo = new AbortController();
    const reloj = setTimeout(() => tiempo.abort(), TIEMPO_MAXIMO_MS);
    senal?.addEventListener('abort', () => tiempo.abort());
    let respuesta;
    try {
      respuesta = await fetch(`${API}${ruta}/?${new URLSearchParams(parametros)}`, {
        headers: {Accept: 'application/json'}, credentials: 'same-origin', signal: tiempo.signal,
      });
    } catch (error) {
      if (senal?.aborted) throw error;
      throw new Error(SIN_SERVICIO);
    } finally {
      clearTimeout(reloj);
    }
    if (respuesta.status === 429) throw new Error(DEMASIADAS);
    const datos = await respuesta.json().catch(() => null);
    if (!respuesta.ok) throw new Error(datos?.detail && respuesta.status === 503 ? datos.detail : SIN_SERVICIO);
    return Array.isArray(datos) ? datos : [];
  }

  async function inversa(lat, lon) {
    const encontrados = await pedir('inversa', {lat: lat.toFixed(5), lon: lon.toFixed(5)});
    return encontrados[0] || null;
  }

  function conectar(input, {alElegir = () => {}, boton = null, estado = null} = {}) {
    const id = `direcciones-opciones-${++contador}`;
    const ancla = input.parentElement;
    ancla.classList.add('buscador-ancla');

    const lista = document.createElement('ul');
    lista.id = id;
    lista.className = 'buscador-opciones';
    lista.setAttribute('role', 'listbox');
    lista.setAttribute('aria-label', 'Direcciones sugeridas');
    lista.hidden = true;
    ancla.appendChild(lista);

    if (!estado) {
      estado = document.createElement('p');
      estado.className = 'sr-only';
      estado.setAttribute('role', 'status');
      ancla.appendChild(estado);
    }

    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-controls', id);
    input.setAttribute('autocomplete', 'off');

    const memoria = new Map();
    let resultados = [];
    let opciones = [];
    let activa = -1;
    let temporizador;
    let peticion;

    function anunciar(texto) { estado.textContent = texto; }

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
      opciones[indice].scrollIntoView({block: 'nearest'});
    }

    function pintar(encontrados) {
      lista.replaceChildren();
      resultados = encontrados;
      opciones = encontrados.map((direccion, i) => {
        const [principal, ...resto] = direccion.etiqueta.split(', ');
        const opcion = document.createElement('li');
        opcion.id = `${id}-${i}`;
        opcion.setAttribute('role', 'option');
        opcion.setAttribute('aria-selected', 'false');
        opcion.dataset.indice = String(i);
        const nombre = document.createElement('span');
        nombre.className = 'buscador-nombre';
        nombre.textContent = principal;
        const detalle = document.createElement('span');
        detalle.className = 'buscador-detalle';
        detalle.textContent = resto.join(', ');
        opcion.append(nombre, detalle);
        lista.appendChild(opcion);
        return opcion;
      });
      activa = -1;
      const hay = opciones.length > 0;
      lista.hidden = !hay;
      input.setAttribute('aria-expanded', String(hay));
      if (!hay) input.removeAttribute('aria-activedescendant');
      return hay;
    }

    function elegir(indice) {
      const direccion = resultados[indice];
      if (!direccion) return;
      input.value = direccion.etiqueta;
      cerrar();
      anunciar(`Elegiste ${direccion.etiqueta}.`);
      alElegir(direccion);
    }

    async function consultar(ruta, texto) {
      const llave = `${ruta}|${texto.toLowerCase()}`;
      if (memoria.has(llave)) return memoria.get(llave);
      peticion?.abort();
      peticion = new AbortController();
      const encontrados = await pedir(ruta, {q: texto}, peticion.signal);
      memoria.set(llave, encontrados);
      return encontrados;
    }

    async function sugerir(texto) {
      try {
        const encontrados = await consultar('sugerir', texto);
        if (input.value.trim() !== texto) return;
        anunciar(pintar(encontrados)
          ? `${encontrados.length} sugerencia${encontrados.length === 1 ? '' : 's'}. Usa las flechas para elegir.`
          : '');
      } catch (error) {
        if (error.name === 'AbortError') return;
        cerrar();
        anunciar(error.message);
      }
    }

    // Búsqueda de la dirección completa (Intro o el botón): una sola petición, no mientras se escribe.
    async function buscar() {
      const texto = input.value.trim();
      clearTimeout(temporizador);
      if (texto.length < MINIMO) { anunciar('Escribe al menos calle y municipio para buscar la dirección.'); return; }
      anunciar('Buscando la dirección…');
      if (boton) boton.disabled = true;
      try {
        const encontrados = await consultar('buscar', texto);
        if (encontrados.length === 1) { resultados = encontrados; elegir(0); }
        else if (pintar(encontrados)) {
          anunciar(`${encontrados.length} direcciones encontradas. Usa las flechas para elegir.`);
          input.focus();
        } else {
          anunciar('No encontramos esa dirección en Jalisco. Prueba con calle, número y municipio, o marca el punto en el mapa.');
        }
      } catch (error) {
        if (error.name !== 'AbortError') { cerrar(); anunciar(error.message); }
      } finally {
        if (boton) boton.disabled = false;
      }
    }

    input.addEventListener('input', () => {
      clearTimeout(temporizador);
      const texto = input.value.trim();
      if (texto.length < MINIMO) { peticion?.abort(); cerrar(); anunciar(''); return; }
      temporizador = setTimeout(() => sugerir(texto), ESPERA_MS);
    });

    input.addEventListener('keydown', evento => {
      const abierta = !lista.hidden && opciones.length > 0;
      if (evento.key === 'ArrowDown' || evento.key === 'ArrowUp') {
        evento.preventDefault();
        if (!abierta) {
          if (opciones.length && resultados.length) { lista.hidden = false; input.setAttribute('aria-expanded', 'true'); }
          return;
        }
        // Recorre las opciones y vuelve al campo (-1) al pasar del final o del principio.
        let siguiente = activa + (evento.key === 'ArrowDown' ? 1 : -1);
        if (siguiente >= opciones.length) siguiente = -1;
        else if (siguiente < -1) siguiente = opciones.length - 1;
        marcar(siguiente);
      } else if (evento.key === 'Enter') {
        // Intro nunca envía el formulario desde este campo: elige la opción o busca la dirección.
        evento.preventDefault();
        if (abierta && activa >= 0) elegir(activa);
        else buscar();
      } else if (evento.key === 'Escape' && abierta) {
        evento.preventDefault();
        evento.stopPropagation();
        cerrar();
      } else if (evento.key === 'Tab') {
        cerrar();
      }
    });

    // mousedown y no click: así el campo no pierde el foco antes de elegir.
    lista.addEventListener('mousedown', evento => evento.preventDefault());
    lista.addEventListener('click', evento => {
      const opcion = evento.target.closest('[role="option"]');
      if (opcion) elegir(Number(opcion.dataset.indice));
    });
    input.addEventListener('blur', cerrar);
    boton?.addEventListener('click', buscar);

    return {cerrar, anunciar, buscar};
  }

  window.InfoTripDirecciones = {conectar, inversa};
})();
