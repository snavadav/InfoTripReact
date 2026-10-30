(() => {
  'use strict';
  const raiz = document.getElementById('bote');
  const api = `/api/v1/mis-viajes/${raiz.dataset.viaje}/bote/`;
  const form = document.getElementById('bote-form');
  const estado = document.getElementById('bote-estado');
  const conceptos = {comida: 'Comida', transporte: 'Transporte', entrada: 'Entradas', alojamiento: 'Alojamiento', otros: 'Otros'};
  let bote = null, editando = null;

  const dinero = valor => new Intl.NumberFormat('es-MX', {style: 'currency', currency: 'MXN'}).format(Number(valor));
  function nodo(tag, texto, clase) {
    const el = document.createElement(tag);
    if (texto) el.textContent = texto;
    if (clase) el.className = clase;
    return el;
  }
  function boton(texto, accion) {
    const el = nodo('button', texto);
    el.type = 'button';
    el.addEventListener('click', accion);
    return el;
  }
  function opciones(select, pares, vacia) {
    const actual = select.value;
    select.replaceChildren();
    if (vacia) { const op = nodo('option', vacia); op.value = ''; select.append(op); }
    pares.forEach(([valor, texto]) => { const op = nodo('option', texto); op.value = valor; select.append(op); });
    if ([...select.options].some(op => op.value === actual)) select.value = actual;
  }
  const nombreDe = id => bote.participantes.find(persona => persona.id === id)?.nombre || '';

  function mostrarPersonas() {
    const lista = document.getElementById('bote-personas');
    lista.replaceChildren();
    bote.participantes.forEach(persona => {
      const fila = nodo('div', null, 'trip-actions');
      const saldo = Number(persona.saldo);
      const texto = saldo > 0 ? `le deben ${dinero(saldo)}` : saldo < 0 ? `debe ${dinero(-saldo)}` : 'a mano';
      fila.append(nodo('span', `${persona.nombre}${persona.es_yo ? ' (tú)' : ''}${persona.es_organizador ? ' · organiza' : ''}: ${texto}`));
      if (!persona.es_organizador && (bote.es_organizador || persona.es_yo)) {
        fila.append(boton(persona.es_yo ? 'Salir del bote' : 'Quitar', async () => {
          if (!confirm(persona.es_yo ? '¿Salir de este bote?' : `¿Quitar a ${persona.nombre} del bote?`)) return;
          try {
            await InfoTrip.api(`${api}participantes/${persona.id}/`, {method: 'DELETE'});
            if (persona.es_yo) location.href = '/mis-viajes/';
            else await cargar();
          } catch (error) { estado.textContent = error.message; }
        }));
      }
      lista.append(fila);
    });
  }
  function mostrarTransferencias() {
    const lista = document.getElementById('bote-transferencias');
    lista.replaceChildren();
    if (!bote.transferencias.length) lista.append(nodo('p', bote.gastos.length ? 'Están a mano: nadie le debe a nadie.' : 'Anoten el primer gasto para ver las cuentas.'));
    bote.transferencias.forEach(pago => lista.append(nodo('p', `${pago.de} le paga ${dinero(pago.monto)} a ${pago.a}`, 'bote-pago')));
  }
  function mostrarGastos() {
    const lista = document.getElementById('bote-gastos');
    lista.replaceChildren();
    if (!bote.gastos.length) lista.append(nodo('p', 'Todavía no hay gastos.'));
    bote.gastos.forEach(gasto => {
      const tarjeta = nodo('article', null, 'bote-gasto');
      tarjeta.append(nodo('h3', `${gasto.descripcion} · ${dinero(gasto.monto)}`));
      const reparto = gasto.entre.length === bote.participantes.length ? 'todos' : gasto.entre.map(nombreDe).join(', ');
      tarjeta.append(nodo('p', `${conceptos[gasto.concepto]} · ${gasto.fecha} · pagó ${nombreDe(gasto.pagado_por)} · entre ${reparto}`));
      if (gasto.publicado) tarjeta.append(nodo('p', 'Enviado a revisión para otros viajeros', 'community-note'));
      if (gasto.puede_editar) {
        const acciones = nodo('div', null, 'trip-actions');
        acciones.append(boton('Editar', () => editar(gasto)), boton('Eliminar', async () => {
          if (!confirm(`¿Eliminar «${gasto.descripcion}»?`)) return;
          try { await InfoTrip.api(`${api}gastos/${gasto.id}/`, {method: 'DELETE'}); await cargar(); }
          catch (error) { estado.textContent = error.message; }
        }));
        tarjeta.append(acciones);
      }
      lista.append(tarjeta);
    });
  }
  function mostrarFormulario() {
    opciones(form.elements.pagado_por, bote.participantes.map(persona => [persona.id, persona.nombre]));
    if (!editando) form.elements.pagado_por.value = bote.participantes.find(persona => persona.es_yo)?.id ?? '';
    opciones(form.elements.destino, bote.lugares.map(lugar => [lugar.id, lugar.nombre]), 'Sin lugar del catálogo');
    if (!editando && bote.lugares.length === 1) form.elements.destino.value = bote.lugares[0].id;
    const entre = document.getElementById('bote-entre');
    const marcados = editando ? new Set(editando.entre) : new Set(bote.participantes.map(persona => persona.id));
    entre.replaceChildren();
    bote.participantes.forEach(persona => {
      const etiqueta = nodo('label', persona.nombre), casilla = nodo('input');
      casilla.type = 'checkbox';
      casilla.name = 'entre';
      casilla.value = persona.id;
      casilla.checked = marcados.has(persona.id);
      etiqueta.prepend(casilla);
      entre.append(etiqueta);
    });
  }
  function sincronizarNoches() {
    const alojamiento = form.elements.concepto.value === 'alojamiento';
    document.getElementById('bote-noches').hidden = !alojamiento;
    if (!alojamiento) form.elements.noches.value = 1;
  }
  function limpiar() {
    editando = null;
    form.reset();
    form.elements.fecha.value = new Date().toLocaleDateString('en-CA');
    document.getElementById('bote-form-titulo').textContent = 'Anotar un gasto';
    document.getElementById('bote-cancelar').hidden = true;
    sincronizarNoches();
    mostrarFormulario();
  }
  function editar(gasto) {
    editando = gasto;
    ['descripcion', 'concepto', 'monto', 'fecha', 'noches', 'pagado_por'].forEach(campo => { form.elements[campo].value = gasto[campo]; });
    mostrarFormulario();
    form.elements.pagado_por.value = gasto.pagado_por;
    form.elements.destino.value = gasto.destino ?? '';
    sincronizarNoches();
    document.getElementById('bote-form-titulo').textContent = 'Editar gasto';
    document.getElementById('bote-cancelar').hidden = false;
    form.elements.descripcion.focus();
  }
  function mostrar() {
    document.getElementById('bote-nombre').textContent = bote.nombre;
    document.getElementById('bote-total').textContent = dinero(bote.total);
    document.getElementById('bote-invitar').hidden = !bote.es_organizador;
    document.getElementById('bote-publicar').hidden = !bote.es_organizador;
    document.getElementById('bote-revocar').hidden = !bote.enlace_invitacion;
    document.getElementById('bote-compartir').textContent = bote.enlace_invitacion ? 'Copiar invitación' : 'Crear otra invitación';
    mostrarPersonas();
    mostrarTransferencias();
    mostrarGastos();
    mostrarFormulario();
    document.getElementById('bote-contenido').hidden = false;
  }
  async function cargar() {
    try {
      bote = await InfoTrip.api(api);
      estado.textContent = '';
      mostrar();
    } catch (error) {
      document.getElementById('bote-nombre').textContent = 'Bote de la escapada';
      estado.textContent = error.message;
    }
  }

  form.elements.concepto.addEventListener('change', sincronizarNoches);
  document.getElementById('bote-cancelar').addEventListener('click', limpiar);
  form.addEventListener('submit', event => {
    event.preventDefault();
    InfoTrip.submit(form, async aviso => {
      const entre = [...form.querySelectorAll('[name="entre"]:checked')].map(casilla => Number(casilla.value));
      if (!entre.length) { aviso.textContent = 'Elige al menos a una persona para repartir el gasto.'; return; }
      const cuerpo = {
        descripcion: form.elements.descripcion.value, concepto: form.elements.concepto.value, monto: form.elements.monto.value,
        fecha: form.elements.fecha.value, noches: Number(form.elements.noches.value) || 1,
        destino: form.elements.destino.value ? Number(form.elements.destino.value) : null,
        pagado_por: Number(form.elements.pagado_por.value), entre,
      };
      await InfoTrip.api(editando ? `${api}gastos/${editando.id}/` : `${api}gastos/`, {method: editando ? 'PATCH' : 'POST', body: cuerpo});
      await cargar();
      limpiar();
      aviso.textContent = 'Gasto guardado.';
    });
  });
  document.getElementById('bote-compartir').addEventListener('click', async () => {
    try {
      if (!bote.enlace_invitacion) bote = await InfoTrip.api(api, {method: 'POST'});
      mostrar();
      const aviso = await InfoTrip.share(`Únete al bote de ${bote.nombre}`, `${location.origin}/botes/${bote.enlace_invitacion}/`);
      if (aviso) estado.textContent = aviso;
    } catch (error) { estado.textContent = error.message; }
  });
  document.getElementById('bote-revocar').addEventListener('click', async () => {
    try {
      await InfoTrip.api(api, {method: 'DELETE'});
      bote.enlace_invitacion = null;
      mostrar();
      estado.textContent = 'La invitación anterior ya no funciona. Quienes ya se unieron siguen en el bote.';
    } catch (error) { estado.textContent = error.message; }
  });
  document.getElementById('bote-publicar-boton').addEventListener('click', async event => {
    const aviso = document.getElementById('bote-publicar-estado');
    event.target.disabled = true;
    try {
      const {publicados, omitidos} = await InfoTrip.api(`${api}publicar/`, {method: 'POST'});
      aviso.textContent = `${publicados} gasto${publicados === 1 ? '' : 's'} enviado${publicados === 1 ? '' : 's'} a revisión.${omitidos ? ` ${omitidos} sin publicar: no tienen un lugar del catálogo o son de tipo "Otros".` : ''}`;
      await cargar();
    } catch (error) { aviso.textContent = error.message; }
    finally { event.target.disabled = false; }
  });

  if (!InfoTrip.hasSession()) {
    document.getElementById('bote-nombre').textContent = 'Bote de la escapada';
    document.getElementById('bote-login').hidden = false;
  } else {
    cargar().then(() => { if (bote) limpiar(); });
  }
})();
