(() => {
  'use strict';
  // Filas y botones de personas para /amigos/ y /u/<username>/. Solo nombre y @usuario: nunca el correo.
  const api = '/api/v1/amigos/';

  function nodo(tag, texto, clase) {
    const el = document.createElement(tag);
    if (texto) el.textContent = texto;
    if (clase) el.className = clase;
    return el;
  }
  function boton(texto, accion, etiqueta) {
    const el = nodo('button', texto);
    el.type = 'button';
    if (etiqueta) el.setAttribute('aria-label', etiqueta);
    el.addEventListener('click', async () => {
      el.disabled = true;
      try { await accion(); } finally { el.disabled = false; }
    });
    return el;
  }
  function enlacePerfil(persona) {
    const enlace = nodo('a', persona.nombre);
    enlace.href = `/u/${encodeURIComponent(persona.username)}/`;
    const arroba = nodo('small', `@${persona.username}`);
    const caja = nodo('span');
    caja.append(enlace, arroba);
    return caja;
  }

  // `hecho(mensaje)` se llama tras cada cambio para recargar la vista y anunciar el resultado.
  function acciones(persona, hecho, {bloquear = false} = {}) {
    const caja = nodo('div', null, 'amigos-acciones');
    const quien = `@${persona.username}`;
    const llamar = async (url, opciones, mensaje) => {
      try { await InfoTrip.api(url, opciones); hecho(mensaje); }
      catch (error) { hecho(error.message, true); }
    };
    switch (persona.relacion) {
      case 'ninguna':
        caja.append(boton('Agregar', () => llamar(`${api}solicitudes/`, {method: 'POST', body: {username: persona.username}},
          `Solicitud enviada a ${quien}.`), `Enviar solicitud de amistad a ${quien}`));
        break;
      case 'enviada':
        caja.append(boton('Cancelar solicitud', () => llamar(`${api}solicitudes/${persona.solicitud}/`, {method: 'DELETE'},
          `Cancelaste la solicitud a ${quien}.`), `Cancelar la solicitud a ${quien}`));
        break;
      case 'recibida':
        caja.append(
          boton('Aceptar', () => llamar(`${api}solicitudes/${persona.solicitud}/aceptar/`, {method: 'POST'},
            `Ahora tú y ${quien} son amigos.`), `Aceptar la solicitud de ${quien}`),
          boton('Rechazar', () => llamar(`${api}solicitudes/${persona.solicitud}/rechazar/`, {method: 'POST'},
            `Rechazaste la solicitud de ${quien}.`), `Rechazar la solicitud de ${quien}`));
        break;
      case 'amigos':
        caja.append(boton('Eliminar amistad', () => {
          if (!confirm(`¿Dejar de ser amigos de ${quien}? No se le avisará.`)) return null;
          return llamar(`${api}${encodeURIComponent(persona.username)}/`, {method: 'DELETE'}, `Ya no eres amigo de ${quien}.`);
        }, `Eliminar la amistad con ${quien}`));
        break;
      case 'bloqueado':
        caja.append(boton('Desbloquear', () => llamar(`${api}bloqueos/${encodeURIComponent(persona.username)}/`, {method: 'DELETE'},
          `Desbloqueaste a ${quien}.`), `Desbloquear a ${quien}`));
        break;
      default:
        break;
    }
    if (bloquear && !['yo', 'bloqueado', 'anonimo'].includes(persona.relacion)) {
      caja.append(boton('Bloquear', () => {
        if (!confirm(`¿Bloquear a ${quien}? Se eliminará su amistad o solicitud, no podrá enviarte otra ni verte al buscar.`)) return null;
        return llamar(`${api}bloqueos/`, {method: 'POST', body: {username: persona.username}}, `Bloqueaste a ${quien}.`);
      }, `Bloquear a ${quien}`));
    }
    return caja;
  }

  function fila(persona, hecho, opciones) {
    const li = nodo('li', null, 'amigos-fila');
    li.append(enlacePerfil(persona), acciones(persona, hecho, opciones));
    return li;
  }
  function lista(contenedor, personas, vacio, hecho, opciones) {
    contenedor.replaceChildren();
    if (!personas.length) contenedor.append(nodo('li', vacio, 'amigos-vacio'));
    personas.forEach(persona => contenedor.append(fila(persona, hecho, opciones)));
  }

  window.InfoTripAmigos = {acciones, fila, lista, nodo};
})();
