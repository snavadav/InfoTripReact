(() => {
  'use strict';
  const form = document.getElementById('usuario-form');
  const campo = document.getElementById('usuario-nombre');
  const aviso = document.getElementById('usuario-disponible');
  const despues = document.getElementById('usuario-despues');
  // Solo rutas del propio sitio, igual que en el inicio de sesión.
  const siguiente = (() => {
    const url = new URL(new URLSearchParams(location.search).get('next') || '/', location.origin);
    return url.origin === location.origin ? url.pathname + url.search + url.hash : '/';
  })();
  despues.href = siguiente;
  let espera = null, consulta = 0;

  function recordar(username) {
    try {
      const usuario = JSON.parse(localStorage.getItem('usuario') || 'null');
      if (usuario) localStorage.setItem('usuario', JSON.stringify({...usuario, username}));
    } catch { /* Solo afecta a la interfaz. */ }
  }
  async function revisar() {
    const valor = campo.value.trim().replace(/^@/, '').toLowerCase();
    if (!valor) { aviso.textContent = ''; return; }
    const propia = ++consulta;
    try {
      const datos = await InfoTrip.api(`/api/v1/auth/username/disponible/?username=${encodeURIComponent(valor)}`);
      if (propia !== consulta) return;
      aviso.textContent = datos.disponible ? `✓ @${datos.username} está disponible.` : datos.motivo;
      aviso.dataset.estado = datos.disponible ? 'si' : 'no';
    } catch (error) { if (propia === consulta) aviso.textContent = error.message; }
  }
  campo.addEventListener('input', () => {
    clearTimeout(espera);
    aviso.textContent = '';
    // Espera a que deje de escribir: una consulta por pausa, no una por tecla.
    espera = setTimeout(revisar, 400);
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    InfoTrip.submit(form, async estado => {
      const datos = await InfoTrip.api('/api/v1/auth/username/', {method: 'POST', body: {username: campo.value}});
      recordar(datos.username);
      estado.textContent = `Listo: ahora eres @${datos.username}.`;
      location.assign(siguiente);
    });
  });

  async function cargar() {
    if (!InfoTrip.hasSession()) { document.getElementById('usuario-login').hidden = false; return; }
    try {
      const datos = await InfoTrip.api('/api/v1/auth/username/');
      form.hidden = false;
      if (datos.username) {
        recordar(datos.username);
        document.getElementById('usuario-titulo').textContent = `Tu nombre de usuario es @${datos.username}`;
        document.getElementById('usuario-intro').textContent = datos.puede_cambiar
          ? 'Puedes cambiarlo ahora. Después tendrás que esperar 30 días para volver a hacerlo.'
          : `Podrás cambiarlo a partir del ${new Date(datos.cambiar_desde).toLocaleDateString('es-MX')}.`;
        campo.value = datos.username;
        despues.textContent = 'Volver';
        form.querySelector('button[type="submit"]').disabled = !datos.puede_cambiar;
        campo.readOnly = !datos.puede_cambiar;
      } else {
        // Solo una propuesta: no se guarda hasta que la persona la acepte.
        campo.value = datos.sugerencia;
        if (datos.sugerencia) revisar();
      }
      campo.focus();
    } catch (error) { aviso.textContent = error.message; }
  }
  cargar();
})();
