(() => {
  'use strict';
  const form = document.getElementById('comentario-form');
  form.addEventListener('submit', evento => {
    evento.preventDefault();
    InfoTrip.submit(form, async aviso => {
      const cuerpo = {...Object.fromEntries(new FormData(form)), pagina: form.dataset.desde};
      // Con sesión se envía autenticado para poder responder; sin ella, como visitante.
      const respuesta = await InfoTrip.api('/api/v1/comentarios/', {method: 'POST', body: cuerpo, auth: InfoTrip.hasSession()});
      form.reset();
      aviso.textContent = respuesta.mensaje;
    });
  });
})();
