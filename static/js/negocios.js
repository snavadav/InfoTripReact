(() => {
  'use strict';
  const form = document.getElementById('negocios-form');
  form.addEventListener('submit', event => {
    event.preventDefault();
    InfoTrip.submit(form, async estado => {
      const cuerpo = Object.fromEntries(new FormData(form));
      cuerpo.acepto = form.elements.acepto.checked;
      const respuesta = await InfoTrip.api('/api/v1/negocios/interes/', {method: 'POST', body: cuerpo, auth: false});
      form.reset();
      estado.textContent = respuesta.mensaje;
    });
  });
})();
