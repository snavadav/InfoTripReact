(() => {
  // Avisos sin leer en la barra. Solo con sesión; el número se recuerda 5 minutos en esta pestaña para no
  // pedirlo en cada página. Mi perfil los marca como leídos al mostrarlos (perfil.js).
  const CLAVE = 'infotrip_avisos';
  const VIGENCIA_MS = 5 * 60 * 1000;
  if (!localStorage.getItem('usuario')) return;
  const enlaces = document.querySelectorAll('[data-avisos]');
  const cuenta = document.getElementById('account-toggle');
  const menu = document.getElementById('hamburger');
  if (!enlaces.length) return;

  function pintar(total) {
    enlaces.forEach(enlace => {
      enlace.hidden = false;
      const numero = enlace.querySelector('.nav-avisos');
      numero.textContent = total > 99 ? '99+' : String(total);
      numero.hidden = !total;
      numero.setAttribute('aria-label', total === 1 ? '1 aviso sin leer' : `${total} avisos sin leer`);
    });
    cuenta?.classList.toggle('con-avisos', total > 0);
    menu?.classList.toggle('con-avisos', total > 0);
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

  if (location.pathname === '/perfil/') { recordar(0); pintar(0); return; }
  // Se llegó desde un aviso (?aviso=<id> en el enlace del correo): ese aviso queda leído y el número se ajusta.
  const parametros = new URLSearchParams(location.search);
  const abierto = Number(parametros.get('aviso')) || null;
  if (abierto) {
    parametros.delete('aviso');
    const resto = parametros.toString();
    history.replaceState(history.state, '', location.pathname + (resto ? '?' + resto : '') + location.hash);
    pedir(`/api/v1/notificaciones/${abierto}/leida/`, {method: 'POST'}).then(datos => {
      if (!datos) return;
      recordar(datos.no_leidas || 0);
      pintar(datos.no_leidas || 0);
    }).catch(() => { /* Si falla, el aviso se marca como leído al abrir Mi perfil. */ });
    return;
  }

  const guardado = recordado();
  if (guardado !== null) { pintar(guardado); return; }
  pintar(0);
  pedir('/api/v1/notificaciones/').then(datos => {
    if (!datos) return;
    recordar(datos.no_leidas || 0);
    pintar(datos.no_leidas || 0);
  }).catch(() => { /* Sin red o sin sesión vigente: la barra queda sin número. */ });
})();
