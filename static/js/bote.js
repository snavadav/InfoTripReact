(() => {
  'use strict';
  const raiz = document.getElementById('bote');
  const api = `/api/v1/mis-viajes/${raiz.dataset.viaje}/bote/`;
  const form = document.getElementById('bote-form');
  const estado = document.getElementById('bote-estado');
  const conceptos = {comida: 'Comida', transporte: 'Transporte', entrada: 'Entradas', alojamiento: 'Alojamiento', otros: 'Otros'};
  let bote = null, editando = null, esperaDonde = null, consultaDonde = 0;

  const fechaLegible = fecha => new Date(`${fecha}T00:00:00`).toLocaleDateString('es-MX');
  const dinero = valor => new Intl.NumberFormat('es-MX', {style: 'currency', currency: 'MXN'}).format(Number(valor));
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
  function opciones(select, pares, vacia) {
    const actual = select.value;
    select.replaceChildren();
    if (vacia) { const op = nodo('option', vacia); op.value = ''; select.append(op); }
    pares.forEach(([valor, texto]) => { const op = nodo('option', texto); op.value = valor; select.append(op); });
    if ([...select.options].some(op => op.value === actual)) select.value = actual;
  }
  const persona = id => bote.participantes.find(p => p.id === id);
  const nombreDe = id => persona(id)?.nombre || '';
  const conArroba = p => `${p.nombre}${p.username ? ` (@${p.username})` : ''}`;
  async function accion(promesa, mensaje) {
    try {
      const nuevo = await promesa;
      if (nuevo && nuevo.participantes) { bote = nuevo; mostrar(); } else await cargar();
      estado.textContent = mensaje;
    } catch (error) { estado.textContent = error.message; }
  }

  // Pestañas accesibles: flechas, Inicio y Fin; la URL recuerda la pestaña (#cuentas).
  const pestanas = [...document.querySelectorAll('[role="tab"]')];
  function elegirPestana(pestana, foco = false) {
    pestanas.forEach(otra => {
      const activa = otra === pestana;
      otra.setAttribute('aria-selected', String(activa));
      otra.tabIndex = activa ? 0 : -1;
      document.getElementById(otra.getAttribute('aria-controls')).hidden = !activa;
    });
    if (foco) pestana.focus();
    history.replaceState(null, '', pestana.id === 'pestana-cuentas' ? '#cuentas' : location.pathname);
  }
  pestanas.forEach((pestana, indice) => {
    pestana.addEventListener('click', () => elegirPestana(pestana));
    pestana.addEventListener('keydown', event => {
      const destino = {ArrowRight: indice + 1, ArrowLeft: indice - 1, Home: 0, End: pestanas.length - 1}[event.key];
      if (destino === undefined) return;
      event.preventDefault();
      elegirPestana(pestanas[(destino + pestanas.length) % pestanas.length], true);
    });
  });

  function mostrarAmigos() {
    const caja = document.getElementById('bote-amigos');
    caja.hidden = !bote.es_organizador;
    const lista = document.getElementById('bote-amigos-lista');
    lista.replaceChildren();
    const boton = document.querySelector('#bote-amigos-form button[type="submit"]');
    boton.hidden = !bote.amigos_invitables.length;
    if (!bote.amigos_invitables.length) lista.append(nodo('p', 'Todos tus amigos ya están en el bote, o aún no tienes amigos en InfoTrip.', 'community-note'));
    bote.amigos_invitables.forEach(amigo => {
      const etiqueta = nodo('label', `${amigo.nombre} (@${amigo.username})`), casilla = nodo('input');
      casilla.type = 'checkbox';
      casilla.name = 'amigo';
      casilla.value = amigo.username;
      etiqueta.prepend(casilla);
      lista.append(etiqueta);
    });
  }
  function mostrarCuentas() {
    const conGastos = bote.gastos.length > 0;
    document.getElementById('bote-a-mano').hidden = !(bote.a_mano && conGastos);
    const sugeridos = document.getElementById('bote-transferencias');
    sugeridos.replaceChildren();
    if (!bote.transferencias.length) sugeridos.append(nodo('p', conGastos ? 'No falta ningún pago: nadie le debe a nadie.' : 'Anoten el primer gasto para ver las cuentas.'));
    bote.transferencias.forEach(pago => {
      const fila = nodo('div', null, 'trip-actions bote-sugerido');
      fila.append(nodo('p', `${pago.de} le paga ${dinero(pago.monto)} a ${pago.a}`, 'bote-pago'));
      if (pago.de_id === bote.yo && !pago.pendiente) {
        fila.append(boton('Ya pagué', () => {
          if (!confirm(`¿Ya le pagaste ${dinero(pago.monto)} a ${pago.a}? Le pediremos que lo confirme.`)) return null;
          return accion(InfoTrip.api(`${api}pagos/`, {method: 'POST', body: {para: pago.a_id, monto: pago.monto}}),
            `Avisamos a ${pago.a}. Cuenta cuando lo confirme.`);
        }, `Ya le pagué ${dinero(pago.monto)} a ${pago.a}`));
      } else if (pago.pendiente && pago.a_id === bote.yo) {
        fila.append(boton('Confirmar recibido', () => accion(InfoTrip.api(`${api}pagos/${pago.pendiente}/confirmar/`, {method: 'POST'}),
          'Pago confirmado.'), `Confirmar que recibí el pago de ${pago.de}`));
      } else if (pago.pendiente) {
        fila.append(nodo('span', `Falta que ${pago.a} confirme que lo recibió.`, 'community-note'));
      }
      sugeridos.append(fila);
    });

    const cuerpo = document.getElementById('bote-personas');
    cuerpo.replaceChildren();
    bote.participantes.forEach(p => {
      const fila = nodo('tr');
      const quien = nodo('th', `${conArroba(p)}${p.es_yo ? ' (tú)' : ''}${p.es_organizador ? ' · organiza' : ''}`);
      quien.scope = 'row';
      const saldo = Number(p.saldo);
      const texto = saldo > 0 ? `le deben ${dinero(saldo)}` : saldo < 0 ? `debe ${dinero(-saldo)}` : 'a mano';
      const columnas = [['Pagó', dinero(p.pago)], ['Le tocaba', dinero(p.le_tocaba)], ['Pagos enviados', dinero(p.enviados)],
        ['Pagos recibidos', dinero(p.recibidos)], ['Diferencia', texto]];
      fila.append(quien, ...columnas.map(([etiqueta, valor]) => {
        const celda = nodo('td', valor);
        celda.dataset.etiqueta = etiqueta;
        return celda;
      }));
      cuerpo.append(fila);
    });
    const salidas = document.getElementById('bote-salidas');
    salidas.replaceChildren();
    bote.participantes.filter(p => p.puede_salir).forEach(p => {
      const fila = nodo('div', null, 'trip-actions');
      fila.append(boton(p.es_yo ? 'Salir del bote' : `Quitar a ${p.nombre}`, async () => {
        if (!confirm(p.es_yo ? '¿Salir de este bote?' : `¿Quitar a ${p.nombre} del bote?`)) return;
        try {
          await InfoTrip.api(`${api}participantes/${p.id}/`, {method: 'DELETE'});
          if (p.es_yo) location.href = '/mis-viajes/';
          else await cargar();
        } catch (error) { estado.textContent = error.message; }
      }));
      salidas.append(fila);
    });

    const historial = document.getElementById('bote-historial');
    historial.replaceChildren();
    if (!bote.pagos.length) historial.append(nodo('li', 'Todavía no hay pagos entre ustedes.', 'amigos-vacio'));
    bote.pagos.forEach(pago => {
      const li = nodo('li', null, 'amigos-fila');
      const texto = nodo('span', `${pago.de} → ${pago.a} · ${dinero(pago.monto)}`);
      texto.append(nodo('small', `${fechaLegible(pago.fecha)} · ${pago.confirmado ? '✓ Confirmado' : 'Esperando confirmación'}`));
      li.append(texto);
      const botones = nodo('div', null, 'amigos-acciones');
      if (pago.puede_confirmar) botones.append(boton('Confirmar recibido', () => accion(InfoTrip.api(`${api}pagos/${pago.id}/confirmar/`, {method: 'POST'}), 'Pago confirmado.')));
      if (pago.puede_cancelar) botones.append(boton('Cancelar', () => accion(InfoTrip.api(`${api}pagos/${pago.id}/`, {method: 'DELETE'}), 'Pago cancelado.')));
      li.append(botones);
      historial.append(li);
    });
  }
  function mostrarGastos() {
    const lista = document.getElementById('bote-gastos');
    lista.replaceChildren();
    if (!bote.gastos.length) lista.append(nodo('p', 'Todavía no hay gastos.'));
    bote.gastos.forEach(gasto => {
      const tarjeta = nodo('article', null, 'bote-gasto');
      tarjeta.append(nodo('h3', `${gasto.descripcion} · ${dinero(gasto.monto)}`));
      const reparto = gasto.entre.length === bote.participantes.length ? 'todos' : gasto.entre.map(nombreDe).join(', ');
      const donde = gasto.lugar_nombre && gasto.lugar_nombre !== gasto.descripcion ? ` · en ${gasto.lugar_nombre}` : '';
      tarjeta.append(nodo('p', `${conceptos[gasto.concepto]}${donde} · ${fechaLegible(gasto.fecha)} · pagó ${nombreDe(gasto.pagado_por)} · entre ${reparto}`));
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
    opciones(form.elements.pagado_por, bote.participantes.map(p => [p.id, p.nombre]));
    if (!editando) form.elements.pagado_por.value = bote.yo;
    opciones(form.elements.destino, bote.lugares.map(lugar => [lugar.id, lugar.nombre]), 'Sin lugar del catálogo');
    if (!editando && bote.lugares.length === 1) form.elements.destino.value = bote.lugares[0].id;
    const entre = document.getElementById('bote-entre');
    const marcados = editando ? new Set(editando.entre) : new Set(bote.participantes.map(p => p.id));
    entre.replaceChildren();
    bote.participantes.forEach(p => {
      const etiqueta = nodo('label', p.nombre), casilla = nodo('input');
      casilla.type = 'checkbox';
      casilla.name = 'entre';
      casilla.value = p.id;
      casilla.checked = marcados.has(p.id);
      etiqueta.prepend(casilla);
      entre.append(etiqueta);
    });
  }
  function elegirDonde(lugar) {
    form.elements.lugar.value = lugar ? lugar.id : '';
    document.getElementById('bote-donde-resultados').replaceChildren();
    const elegido = document.getElementById('bote-donde-elegido');
    elegido.replaceChildren();
    if (!lugar) return;
    elegido.append(`Dónde: ${lugar.nombre}. `);
    const quitar = nodo('button', 'Quitar');
    quitar.type = 'button';
    quitar.className = 'enlace-boton';
    quitar.addEventListener('click', () => { elegirDonde(null); document.getElementById('bote-donde').focus(); });
    elegido.append(quitar);
    document.getElementById('bote-donde').value = '';
  }
  async function buscarDonde() {
    const texto = document.getElementById('bote-donde').value.trim();
    const lista = document.getElementById('bote-donde-resultados');
    if (texto.length < 2) { lista.replaceChildren(); return; }
    const propia = ++consultaDonde;
    try {
      const lugares = await InfoTrip.api(`${api}lugares/?q=${encodeURIComponent(texto)}`);
      if (propia !== consultaDonde) return;
      lista.replaceChildren();
      if (!lugares.length) lista.append(nodo('li', 'Sin coincidencias cerca de la escapada. Puedes dejarlo vacío y escribir la descripción.', 'amigos-vacio'));
      lugares.forEach(lugar => {
        const li = nodo('li', null, 'amigos-fila');
        const texto_ = nodo('span', lugar.nombre);
        texto_.append(nodo('small', [lugar.tipo, lugar.municipio].filter(Boolean).join(' · ')));
        li.append(texto_, boton('Elegir', () => elegirDonde(lugar), `Elegir ${lugar.nombre}`));
        lista.append(li);
      });
    } catch (error) { if (propia === consultaDonde) estado.textContent = error.message; }
  }
  function sincronizarNoches() {
    const alojamiento = form.elements.concepto.value === 'alojamiento';
    document.getElementById('bote-noches').hidden = !alojamiento;
    if (!alojamiento) form.elements.noches.value = 1;
  }
  function limpiar() {
    editando = null;
    form.reset();
    elegirDonde(null);
    form.elements.fecha.value = new Date().toLocaleDateString('en-CA');
    document.getElementById('bote-form-titulo').textContent = '+ Yo pagué';
    document.getElementById('bote-cancelar').hidden = true;
    sincronizarNoches();
    mostrarFormulario();
  }
  function editar(gasto) {
    editando = gasto;
    ['descripcion', 'concepto', 'monto', 'fecha', 'noches'].forEach(campo => { form.elements[campo].value = gasto[campo]; });
    mostrarFormulario();
    form.elements.pagado_por.value = gasto.pagado_por;
    form.elements.destino.value = gasto.destino ?? '';
    elegirDonde(gasto.lugar ? {id: gasto.lugar, nombre: gasto.lugar_nombre} : null);
    sincronizarNoches();
    document.getElementById('bote-form-titulo').textContent = 'Editar gasto';
    document.getElementById('bote-cancelar').hidden = false;
    form.elements.monto.focus();
  }
  function mostrar() {
    document.getElementById('bote-nombre').textContent = bote.nombre;
    document.getElementById('bote-total').textContent = dinero(bote.total);
    document.getElementById('bote-invitar').hidden = !bote.es_organizador;
    document.getElementById('bote-publicar').hidden = !bote.es_organizador;
    document.getElementById('bote-revocar').hidden = !bote.enlace_invitacion;
    document.getElementById('bote-compartir').textContent = bote.enlace_invitacion ? 'Copiar invitación' : 'Crear invitación';
    mostrarAmigos();
    mostrarCuentas();
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
  document.getElementById('bote-donde').addEventListener('input', () => {
    clearTimeout(esperaDonde);
    esperaDonde = setTimeout(buscarDonde, 300);
  });
  document.getElementById('bote-donde').addEventListener('keydown', event => {
    // Enter busca en vez de enviar el gasto a medias.
    if (event.key === 'Enter') { event.preventDefault(); clearTimeout(esperaDonde); buscarDonde(); }
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    InfoTrip.submit(form, async aviso => {
      const entre = [...form.querySelectorAll('[name="entre"]:checked')].map(casilla => Number(casilla.value));
      if (!entre.length) { aviso.textContent = 'Elige al menos a una persona para dividir el gasto.'; return; }
      const cuerpo = {
        descripcion: form.elements.descripcion.value, concepto: form.elements.concepto.value, monto: form.elements.monto.value,
        fecha: form.elements.fecha.value, noches: Number(form.elements.noches.value) || 1,
        destino: form.elements.destino.value ? Number(form.elements.destino.value) : null,
        lugar: form.elements.lugar.value ? Number(form.elements.lugar.value) : null,
        pagado_por: Number(form.elements.pagado_por.value), entre,
      };
      await InfoTrip.api(editando ? `${api}gastos/${editando.id}/` : `${api}gastos/`, {method: editando ? 'PATCH' : 'POST', body: cuerpo});
      await cargar();
      limpiar();
      aviso.textContent = 'Gasto guardado. Revisa la pestaña Cuentas.';
    });
  });
  document.getElementById('bote-amigos-form').addEventListener('submit', event => {
    event.preventDefault();
    const amigosForm = event.target;
    InfoTrip.submit(amigosForm, async aviso => {
      const usernames = [...amigosForm.querySelectorAll('[name="amigo"]:checked')].map(casilla => casilla.value);
      if (!usernames.length) { aviso.textContent = 'Marca al menos a un amigo.'; return; }
      bote = await InfoTrip.api(`${api}invitar/`, {method: 'POST', body: {usernames}});
      mostrar();
      aviso.textContent = `${usernames.length === 1 ? 'Agregaste a 1 amigo' : `Agregaste a ${usernames.length} amigos`} al bote.`;
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

  if (location.hash === '#cuentas') elegirPestana(document.getElementById('pestana-cuentas'));
  if (!InfoTrip.hasSession()) {
    document.getElementById('bote-nombre').textContent = 'Bote de la escapada';
    document.getElementById('bote-login').hidden = false;
  } else {
    cargar().then(() => {
      if (!bote) return;
      limpiar();
      // Desde "Invitar amigos" en Mis viajes: la sección aparece al cargar, así que el ancla se sigue aquí.
      if (location.hash === '#bote-amigos' && bote.es_organizador) {
        const seccion = document.getElementById('bote-amigos');
        seccion.scrollIntoView({block: 'start'});
        (seccion.querySelector('input') || seccion.querySelector('a')).focus({preventScroll: true});
      }
    });
  }
})();
