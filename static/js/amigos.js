(() => {
  'use strict';
  const {lista} = window.InfoTripAmigos;
  const estado = document.getElementById('amigos-estado');
  const buscar = document.getElementById('buscar-form');
  const campo = document.getElementById('buscar-q');
  const resultados = document.getElementById('buscar-resultados');
  const privacidad = document.getElementById('privacidad-form');
  let espera = null, consulta = 0;

  function hecho(mensaje, error = false) {
    estado.textContent = mensaje;
    estado.dataset.error = error ? 'si' : '';
    cargar();
    if (campo.value.trim()) buscarAhora();
  }
  async function cargar() {
    try {
      const datos = await InfoTrip.api('/api/v1/amigos/');
      if (!datos.username) {
        document.getElementById('amigos-sin-usuario').hidden = false;
        return;
      }
      document.getElementById('ver-mi-perfil').href = `/u/${encodeURIComponent(datos.username)}/`;
      lista(document.getElementById('lista-recibidas'), datos.recibidas, 'No tienes solicitudes nuevas.', hecho, {bloquear: true});
      lista(document.getElementById('lista-amigos'), datos.amigos, 'Todavía no tienes amigos en InfoTrip. Búscalos por su @usuario.', hecho);
      lista(document.getElementById('lista-enviadas'), datos.enviadas, 'No tienes solicitudes pendientes.', hecho);
      lista(document.getElementById('lista-bloqueados'), datos.bloqueados, 'No has bloqueado a nadie.', hecho);
      document.getElementById('amigos-contenido').hidden = false;
      // Desde un aviso (/amigos/#recibidas-titulo): la sección aparece al cargar, así que se lleva ahí a mano.
      if (location.hash) {
        document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView();
        history.replaceState(history.state, '', location.pathname + location.search);
      }
    } catch (error) { estado.textContent = error.message; }
  }
  async function buscarAhora() {
    const texto = campo.value.trim().replace(/^@/, '').toLowerCase();
    const aviso = buscar.querySelector('.form-status');
    if (texto.length < 2) { resultados.replaceChildren(); aviso.textContent = ''; return; }
    const propia = ++consulta;
    try {
      const personas = await InfoTrip.api(`/api/v1/amigos/buscar/?q=${encodeURIComponent(texto)}`);
      if (propia !== consulta) return;
      lista(resultados, personas, `Nadie con un @usuario que empiece con «${texto}».`, hecho, {bloquear: true});
      aviso.textContent = personas.length ? `${personas.length} resultado${personas.length === 1 ? '' : 's'}.` : '';
    } catch (error) { if (propia === consulta) aviso.textContent = error.message; }
  }
  campo.addEventListener('input', () => {
    clearTimeout(espera);
    espera = setTimeout(buscarAhora, 300);
  });
  buscar.addEventListener('submit', event => {
    event.preventDefault();
    clearTimeout(espera);
    buscarAhora();
  });

  async function cargarPrivacidad() {
    try {
      const perfil = await InfoTrip.api('/api/v1/auth/perfil/');
      privacidad.elements.visibilidad.value = perfil.visibilidad;
      privacidad.elements.mostrar_amigos.checked = perfil.mostrar_amigos;
    } catch { /* El resto de la página funciona igual. */ }
  }
  privacidad.addEventListener('submit', event => {
    event.preventDefault();
    InfoTrip.submit(privacidad, async aviso => {
      await InfoTrip.api('/api/v1/auth/perfil/', {method: 'PATCH', body: {
        visibilidad: privacidad.elements.visibilidad.value, mostrar_amigos: privacidad.elements.mostrar_amigos.checked,
      }});
      aviso.textContent = 'Guardado.';
    });
  });

  if (!InfoTrip.hasSession()) {
    document.getElementById('amigos-login').hidden = false;
  } else {
    cargar();
    cargarPrivacidad();
  }
})();
