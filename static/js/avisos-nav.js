(() => {
  // Campana de avisos en la barra: número de no leídos y un panel con los últimos, como en una red social.
  // Solo con sesión. El número se recuerda 5 minutos en esta pestaña para no pedirlo en cada página; al abrir el
  // panel se piden de nuevo. Cada aviso se marca como leído al abrirlo (?aviso=<id>) o con «Marcar todo».
  const CLAVE = 'infotrip_avisos';
  const VIGENCIA_MS = 5 * 60 * 1000;
  const envoltura = document.getElementById('avisos-wrap');
  if (!envoltura || !localStorage.getItem('usuario')) return;
  const boton = document.getElementById('avisos-toggle');
  const numero = document.getElementById('avisos-numero');
  const panel = document.getElementById('avisos-panel');
  const lista = document.getElementById('avisos-lista');
  const todosLeidos = document.getElementById('avisos-todos-leidos');
  envoltura.hidden = false;

  // Un icono por familia de aviso; se dibuja con DOM (sin innerHTML) para la CSP.
  const TRAZOS = {
    viaje: ['M8 2v4', 'M16 2v4', 'M3 10h18', 'M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z'],
    dinero: ['M3 7h18v12H3z', 'M3 11h18', 'M16 15h2'],
    personas: ['M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', 'M2 21v-1a6 6 0 0 1 12 0v1', 'M16 3.1a4 4 0 0 1 0 7.8', 'M22 21v-1a6 6 0 0 0-4-5.6'],
    estrella: ['M12 3l2.8 5.6 6.2.9-4.5 4.4 1 6.1-5.5-2.9-5.5 2.9 1-6.1L3 9.5l6.2-.9z'],
  };
  const FAMILIA = {viaje_pronto: 'viaje', viaje_hoy: 'viaje', viaje_resena: 'viaje', pago: 'dinero', cuentas: 'dinero',
    bote: 'dinero', amistad: 'personas'};
  function icono(tipo) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    for (const d of TRAZOS[FAMILIA[tipo] || 'estrella']) {
      const trazo = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      trazo.setAttribute('d', d);
      svg.append(trazo);
    }
    const caja = document.createElement('span');
    caja.className = `aviso-icono aviso-icono--${FAMILIA[tipo] || 'estrella'}`;
    caja.append(svg);
    return caja;
  }
  function nodo(etiqueta, texto, clase) {
    const elemento = document.createElement(etiqueta);
    if (texto) elemento.textContent = texto;
    if (clase) elemento.className = clase;
    return elemento;
  }
  const relativo = new Intl.RelativeTimeFormat('es-MX', {numeric: 'auto'});
  function hace(fecha) {
    const segundos = (new Date(fecha) - Date.now()) / 1000;
    for (const [unidad, tamano] of [['day', 86400], ['hour', 3600], ['minute', 60]]) {
      if (Math.abs(segundos) >= tamano) return relativo.format(Math.round(segundos / tamano), unidad);
    }
    return 'ahora';
  }
  function conAviso(enlace, id) {
    const [ruta, ancla] = enlace.split('#');
    return `${ruta}${ruta.includes('?') ? '&' : '?'}aviso=${id}${ancla ? '#' + ancla : ''}`;
  }

  function pintar(total) {
    numero.textContent = total > 99 ? '99+' : String(total);
    numero.hidden = !total;
    boton.setAttribute('aria-label', !total ? 'Avisos' : total === 1 ? 'Avisos, 1 sin leer' : `Avisos, ${total} sin leer`);
    todosLeidos.hidden = !total;
  }
  function recordar(total) {
    try { sessionStorage.setItem(CLAVE, JSON.stringify({total, cuando: Date.now()})); } catch { /* Sin almacenamiento se pide en cada página. */ }
  }
  function recordado() {
    try {
      const dato = JSON.parse(sessionStorage.getItem(CLAVE) || 'null');
      return dato && Date.now() - dato.cuando < VIGENCIA_MS ? dato.total : null;
    } catch { return null; }
  }
  function actualizar(total) { recordar(total); pintar(total); }
  function csrf() {
    const cookie = document.cookie.split('; ').find(item => item.startsWith('csrftoken='));
    return cookie ? decodeURIComponent(cookie.slice('csrftoken='.length)) : '';
  }
  // En páginas con cuenta-api.js se comparte su token; en las demás se pide uno con el mismo cerrojo de sesión.
  async function pedir(url, opciones = {}) {
    if (window.InfoTrip) return window.InfoTrip.api(url, opciones);
    const renovar = async () => {
      const respuesta = await fetch('/api/v1/auth/token/refresh/', {method: 'POST', headers: {'X-CSRFToken': csrf()}});
      return respuesta.ok ? (await respuesta.json()).access : null;
    };
    const access = await (navigator.locks ? navigator.locks.request('infotrip-sesion', renovar) : renovar());
    if (!access) return null;
    const respuesta = await fetch(url, {...opciones, headers: {Authorization: 'Bearer ' + access}});
    return respuesta.ok ? respuesta.json() : null;
  }

  function elemento(aviso) {
    const item = nodo('li', null, aviso.leida ? 'aviso' : 'aviso aviso--nuevo');
    const destino = aviso.enlace ? nodo('a') : nodo('button');
    if (aviso.enlace) destino.href = conAviso(aviso.enlace, aviso.id);
    else destino.type = 'button';
    destino.className = 'aviso-enlace';
    const cuerpo = nodo('span', null, 'aviso-cuerpo');
    if (!aviso.leida) cuerpo.append(nodo('span', 'Sin leer: ', 'sr-only'));
    cuerpo.append(nodo('span', aviso.texto, 'aviso-texto'));
    const pie = nodo('span', null, 'aviso-pie');
    pie.append(nodo('span', hace(aviso.creado)));
    if (aviso.enlace) pie.append(nodo('span', aviso.accion + ' →', 'aviso-accion-nav'));
    cuerpo.append(pie);
    destino.append(icono(aviso.tipo), cuerpo);
    if (!aviso.leida) {
      const punto = nodo('span', null, 'aviso-punto');
      punto.setAttribute('aria-hidden', 'true');
      destino.append(punto);
    }
    if (!aviso.enlace && !aviso.leida) {
      destino.addEventListener('click', async () => {
        const datos = await pedir(`/api/v1/notificaciones/${aviso.id}/leida/`, {method: 'POST'});
        if (!datos) return;
        item.className = 'aviso';
        destino.querySelectorAll('.aviso-punto, .sr-only').forEach(marca => marca.remove());
        actualizar(datos.no_leidas || 0);
      });
    }
    item.append(destino);
    return item;
  }
  function grupo(titulo, avisos) {
    if (!avisos.length) return [];
    const ul = nodo('ul', null, 'avisos-grupo');
    ul.setAttribute('aria-label', titulo);
    ul.append(...avisos.map(elemento));
    return [nodo('h3', titulo, 'avisos-grupo-titulo'), ul];
  }
  async function cargar() {
    lista.replaceChildren(nodo('p', 'Cargando…', 'avisos-vacio'));
    try {
      const datos = await pedir('/api/v1/notificaciones/');
      if (!datos) throw new Error();
      actualizar(datos.no_leidas || 0);
      const avisos = datos.results || [];
      if (!avisos.length) {
        lista.replaceChildren(nodo('p', 'No tienes avisos por ahora. Aquí verás tus recordatorios de viaje, pagos del bote y solicitudes de amistad.', 'avisos-vacio'));
        return;
      }
      lista.replaceChildren(...grupo('Nuevos', avisos.filter(a => !a.leida)), ...grupo('Anteriores', avisos.filter(a => a.leida)));
    } catch {
      lista.replaceChildren(nodo('p', 'No pudimos cargar tus avisos. Revisa tu conexión e inténtalo de nuevo.', 'avisos-vacio'));
    }
  }

  function abrir(abierto) {
    panel.hidden = !abierto;
    boton.setAttribute('aria-expanded', String(abierto));
    // El menú de cuenta se cierra solo al pulsar fuera de él (navbar.js): un solo menú abierto a la vez.
    if (abierto) cargar();
  }
  boton.addEventListener('click', () => abrir(panel.hidden));
  document.addEventListener('click', event => {
    if (!panel.hidden && !envoltura.contains(event.target)) abrir(false);
  });
  document.getElementById('account-toggle')?.addEventListener('click', () => { if (!panel.hidden) abrir(false); });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !panel.hidden) { abrir(false); boton.focus(); }
  });
  todosLeidos.addEventListener('click', async () => {
    const datos = await pedir('/api/v1/notificaciones/leidas/', {method: 'POST'});
    if (!datos) return;
    actualizar(0);
    lista.querySelectorAll('.aviso--nuevo').forEach(item => item.classList.remove('aviso--nuevo'));
    lista.querySelectorAll('.aviso-punto, .aviso .sr-only').forEach(marca => marca.remove());
    boton.focus();
  });

  if (location.pathname === '/perfil/') { actualizar(0); return; }
  // Se llegó desde un aviso (?aviso=<id> en el panel o en el correo): ese aviso queda leído y el número se ajusta.
  const parametros = new URLSearchParams(location.search);
  const abierto = Number(parametros.get('aviso')) || null;
  if (abierto) {
    parametros.delete('aviso');
    const resto = parametros.toString();
    history.replaceState(history.state, '', location.pathname + (resto ? '?' + resto : '') + location.hash);
    pedir(`/api/v1/notificaciones/${abierto}/leida/`, {method: 'POST'}).then(datos => {
      if (datos) actualizar(datos.no_leidas || 0);
    }).catch(() => { /* Si falla, el aviso se marca como leído al abrir Mi perfil. */ });
    return;
  }

  function consultar() {
    pedir('/api/v1/notificaciones/').then(datos => {
      if (datos) actualizar(datos.no_leidas || 0);
    }).catch(() => { /* Sin red o sin sesión vigente: la campana queda sin número. */ });
  }
  const guardado = recordado();
  if (guardado !== null) pintar(guardado);
  else { pintar(0); consultar(); }
  // Al volver a la pestaña después de un rato, el número se pone al día.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && recordado() === null) consultar();
  });
})();
