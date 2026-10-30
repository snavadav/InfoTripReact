(() => {
  'use strict';
  const raiz = document.getElementById('lugar');
  const api = `/api/v1/lugares/${raiz.dataset.lugar}/`;
  const form = document.getElementById('resena-form');
  const retirar = document.getElementById('resena-retirar');
  const botones = [...document.querySelectorAll('.estado-lugar')];
  const mensaje = document.getElementById('estado-mensaje');
  let tieneResena = false;

  function pedirEntrar(destino, texto) {
    destino.replaceChildren(document.createTextNode(`${texto} `));
    const enlace = document.createElement('a');
    enlace.href = InfoTrip.loginUrl();
    enlace.textContent = 'Iniciar sesión';
    destino.append(enlace);
  }
  function marcar(abierto) {
    botones.forEach(boton => boton.setAttribute('aria-pressed', String(boton.dataset.abierto === String(abierto))));
  }

  /* ¿Sigue abierto? */
  botones.forEach(boton => boton.addEventListener('click', async () => {
    if (!InfoTrip.hasSession()) { pedirEntrar(mensaje, 'Entra para responder.'); return; }
    botones.forEach(otro => { otro.disabled = true; });
    try {
      const abierto = boton.dataset.abierto === 'true';
      const estado = await InfoTrip.api(`${api}estado/`, {method: 'POST', body: {abierto}});
      marcar(abierto);
      const fecha = new Date(`${estado.ultima}T00:00:00`).toLocaleDateString('es-MX');
      document.getElementById('estado-resumen').textContent = `${estado.abiertos} ${estado.abiertos === 1 ? 'dice' : 'dicen'} que sí, ${estado.cerrados} que no · última respuesta el ${fecha}`;
      mensaje.textContent = 'Gracias. Tu respuesta ayuda al siguiente viajero.';
    } catch (error) { mensaje.textContent = error.message; }
    finally { botones.forEach(otro => { otro.disabled = false; }); }
  }));

  /* Reseña */
  function mostrarPropia(resena) {
    tieneResena = Boolean(resena);
    retirar.hidden = !resena;
    document.getElementById('resena-titulo').textContent = resena ? 'Editar mi reseña' : 'Escribir una reseña';
    if (!resena) return;
    form.elements.calificacion.value = resena.calificacion;
    form.elements.texto.value = resena.texto;
    form.elements.fecha_visita.value = resena.fecha_visita;
    if (form.elements.monto) form.elements.monto.value = resena.monto ?? '';
    document.getElementById('resena-acceso').textContent = `Estado de tu reseña: ${resena.estado_nombre}. Si la editas, vuelve a revisión.`;
  }
  function ubicacion() {
    return new Promise((resolver, rechazar) => {
      if (!navigator.geolocation) { rechazar(new Error('Tu navegador no ofrece ubicación. Quita la casilla para enviar sin ella.')); return; }
      navigator.geolocation.getCurrentPosition(
        posicion => resolver({latitud: posicion.coords.latitude, longitud: posicion.coords.longitude}),
        () => rechazar(new Error('No pudimos obtener tu ubicación. Quita la casilla para enviar sin ella.')),
        {timeout: 15000, maximumAge: 60000},
      );
    });
  }
  form.addEventListener('submit', evento => {
    evento.preventDefault();
    if (!InfoTrip.hasSession()) { pedirEntrar(form.querySelector('.form-status'), 'Entra para enviar tu reseña.'); return; }
    InfoTrip.submit(form, async aviso => {
      // FormData: puede llevar una foto. Lo que va vacío no se envía, para no borrar lo que ya estaba.
      const cuerpo = new FormData(form);
      cuerpo.delete('comprobar');
      if (!form.elements.imagen.files.length) cuerpo.delete('imagen');
      if (form.elements.monto && !form.elements.monto.value) cuerpo.delete('monto');
      const comprobar = form.elements.comprobar.checked;
      if (comprobar) Object.entries(await ubicacion()).forEach(([campo, valor]) => cuerpo.set(campo, valor));
      const resena = await InfoTrip.api(tieneResena ? `${api}mi-opinion/` : `${api}resenas/`, {method: tieneResena ? 'PATCH' : 'POST', body: cuerpo});
      mostrarPropia(resena);
      form.elements.comprobar.checked = false;
      form.elements.imagen.value = '';
      aviso.textContent = comprobar && !resena.ubicacion_comprobada
        ? 'Recibida y pendiente de revisión. No estás lo bastante cerca para comprobar tu ubicación, así que irá sin esa etiqueta.'
        : 'Recibida. Quedó pendiente de revisión; aparecerá cuando se publique.';
    });
  });
  retirar.addEventListener('click', async () => {
    if (!confirm('¿Retirar tu reseña de este lugar?')) return;
    try {
      await InfoTrip.api(`${api}mi-opinion/`, {method: 'DELETE'});
      form.reset();
      mostrarPropia(null);
      document.getElementById('resena-acceso').textContent = 'Tu reseña se retiró. Puedes escribir otra.';
    } catch (error) { form.querySelector('.form-status').textContent = error.message; }
  });

  if (InfoTrip.hasSession()) {
    document.getElementById('resena-acceso').textContent = 'Tu reseña quedará pendiente de revisión.';
    InfoTrip.api(`${api}mi-opinion/`).then(opinion => {
      mostrarPropia(opinion.resena);
      if (opinion.abierto !== null) marcar(opinion.abierto);
    }).catch(() => { /* Sin datos propios la página sigue funcionando. */ });
  }
})();
