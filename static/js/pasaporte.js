(() => {
  'use strict';
  if (!InfoTrip.hasSession()) return;
  const progreso = document.getElementById('pasaporte-progreso');
  const seccion = document.getElementById('pasaporte-compartir');
  const compartir = document.getElementById('pasaporte-enlace');
  const retirar = document.getElementById('pasaporte-retirar');
  const estado = document.getElementById('pasaporte-estado');

  async function cargar() {
    try {
      const datos = await InfoTrip.api('/api/v1/mi-pasaporte/');
      datos.sellos.filter(sello => sello.sello).forEach(sello => {
        const tarjeta = document.querySelector(`[data-sello="${sello.slug}"]`);
        tarjeta.classList.add('passport-stamp--done');
        tarjeta.querySelector('.passport-state').textContent = 'Con sello';
      });
      progreso.textContent = `Llevas ${datos.total} de ${datos.de} sellos.`;
      seccion.hidden = false;
      retirar.hidden = !datos.enlace;
    } catch (error) {
      progreso.textContent = error.message;
    }
  }
  compartir.addEventListener('click', async () => {
    try {
      const {enlace} = await InfoTrip.api('/api/v1/mi-pasaporte/compartir/', {method: 'POST'});
      retirar.hidden = false;
      const aviso = await InfoTrip.share('Mi pasaporte de Pueblos Mágicos de Jalisco', `${location.origin}/pasaporte/${enlace}/?ref=compartido`);
      if (aviso) estado.textContent = aviso;
    } catch (error) { estado.textContent = error.message; }
  });
  retirar.addEventListener('click', async () => {
    try {
      await InfoTrip.api('/api/v1/mi-pasaporte/compartir/', {method: 'DELETE'});
      retirar.hidden = true;
      estado.textContent = 'El enlace anterior ya no funciona.';
    } catch (error) { estado.textContent = error.message; }
  });
  cargar();
})();
