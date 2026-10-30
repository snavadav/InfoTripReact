(() => {
  'use strict';
  const boton = document.getElementById('bote-unirse');
  const estado = document.getElementById('bote-unirse-estado');
  boton.addEventListener('click', async () => {
    if (!InfoTrip.hasSession()) {
      location.href = InfoTrip.loginUrl();
      return;
    }
    boton.disabled = true;
    estado.textContent = 'Uniéndote…';
    try {
      const {viaje} = await InfoTrip.api(`/api/v1/botes/${boton.dataset.enlace}/unirse/`, {method: 'POST'});
      location.href = `/mis-viajes/${viaje}/bote/`;
    } catch (error) {
      estado.textContent = error.message;
      boton.disabled = false;
    }
  });
})();
