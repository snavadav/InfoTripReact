(() => {
  'use strict';
  const {acciones, lista, nodo} = window.InfoTripAmigos;
  const raiz = document.getElementById('perfil-publico');
  const username = raiz.dataset.username;
  const estado = document.getElementById('perfil-estado');

  function hecho(mensaje, error = false) {
    estado.textContent = mensaje;
    estado.dataset.error = error ? 'si' : '';
    cargar();
  }
  function mostrar(perfil) {
    document.title = `${perfil.nombre} (@${perfil.username}) — InfoTrip`;
    document.getElementById('perfil-nombre').textContent = perfil.nombre;
    document.getElementById('perfil-arroba').textContent = `@${perfil.username}${perfil.relacion === 'amigos' ? ' · Son amigos' : ''}${perfil.relacion === 'yo' ? ' · Así te ven los demás según tu configuración' : ''}`;
    document.getElementById('perfil-inicial').textContent = (perfil.nombre || '?').charAt(0).toUpperCase();
    const botones = document.getElementById('perfil-acciones');
    botones.replaceChildren();
    if (perfil.relacion === 'anonimo') {
      const entrar = nodo('a', 'Inicia sesión para agregar');
      entrar.href = InfoTrip.loginUrl();
      botones.append(entrar);
    } else if (perfil.relacion === 'yo') {
      const ajustes = nodo('a', 'Cambiar quién ve mi perfil');
      ajustes.href = '/amigos/#privacidad-titulo';
      botones.append(ajustes);
    } else {
      botones.append(acciones(perfil, hecho, {bloquear: true}));
    }
    document.getElementById('perfil-sin-permiso').hidden = perfil.detalle;
    document.getElementById('perfil-pasaporte').hidden = !perfil.detalle;
    document.getElementById('perfil-lugares').hidden = !perfil.detalle;
    document.getElementById('perfil-amigos').hidden = !perfil.detalle || !perfil.amigos;
    if (!perfil.detalle) return;
    const sellos = document.getElementById('perfil-sellos');
    sellos.replaceChildren();
    perfil.sellos.forEach(sello => {
      const li = nodo('li', `${sello.sello ? '✓ ' : ''}${sello.nombre}`);
      li.dataset.sello = sello.sello ? 'si' : 'no';
      if (!sello.sello) li.append(nodo('span', ' (sin sello)', 'sr-only'));
      sellos.append(li);
    });
    const ganados = perfil.sellos.filter(sello => sello.sello).length;
    document.getElementById('perfil-sellos-resumen').textContent = `${ganados} de ${perfil.sellos.length} sellos.`;
    const lugares = document.getElementById('perfil-lugares-lista');
    lugares.replaceChildren();
    if (!perfil.lugares.length) lugares.append(nodo('li', 'Aún no hay visitas comprobadas.'));
    perfil.lugares.forEach(lugar => {
      const li = nodo('li'), enlace = nodo('a', lugar.nombre);
      enlace.href = `/destinos/${encodeURIComponent(lugar.slug)}/`;
      li.append(enlace);
      lugares.append(li);
    });
    if (perfil.amigos) {
      const amigos = perfil.amigos.map(amigo => ({...amigo, relacion: 'yo'}));
      lista(document.getElementById('perfil-amigos-lista'), amigos, 'Sin amigos que mostrar.', hecho);
    }
  }
  async function cargar() {
    try {
      const perfil = await InfoTrip.api(`/api/v1/personas/${encodeURIComponent(username)}/`, {auth: InfoTrip.hasSession()});
      mostrar(perfil);
    } catch (error) {
      document.getElementById('perfil-nombre').textContent = 'Perfil no disponible';
      estado.textContent = error.message.includes('No encontrado') || error.message.includes('not found')
        ? 'No encontramos a nadie con ese nombre de usuario.' : error.message;
    }
  }
  cargar();
})();
