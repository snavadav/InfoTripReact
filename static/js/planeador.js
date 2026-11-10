(() => {
  'use strict';
  const form = document.getElementById('ruta-form');
  const estado = form.querySelector('.planeador-estado');
  const botonEnviar = form.querySelector('.planeador-enviar');
  const resultado = document.getElementById('ruta-resultado');
  const vacio = document.getElementById('ruta-vacio');
  const tarjetas = document.getElementById('ruta-dias');
  const detalle = document.getElementById('ruta-detalle');
  const botonUbicacion = document.getElementById('ruta-ubicacion');
  const estadoUbicacion = document.getElementById('ruta-ubicacion-estado');
  const selectMunicipio = document.getElementById('ruta-municipio');
  const campoFecha = form.elements.fecha;
  const campoPersonas = form.elements.personas;
  const botonGuardar = document.getElementById('ruta-guardar');
  const estadoGuardar = document.getElementById('ruta-guardar-estado');
  const botonCompartir = document.getElementById('ruta-compartir');
  const estadoCompartir = document.getElementById('ruta-compartir-estado');
  const panelCompartir = document.getElementById('ruta-compartir-panel');
  const campoDestino = document.getElementById('ruta-destino');
  const valorDestino = document.getElementById('ruta-destino-valor');
  const explicaModo = document.getElementById('ruta-modo-explica');
  const advertencia = document.getElementById('ruta-advertencia');
  const DIAS_SEMANA = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
  const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const COLORES = 3;
  const MINIMO_MINUTOS = 180;
  const LARGO_DESCRIPCION = 320;
  const pesos = new Intl.NumberFormat('es-MX', {style: 'currency', currency: 'MXN', maximumFractionDigits: 0});
  const sinMovimiento = window.matchMedia('(prefers-reduced-motion: reduce)');
  let ubicacion = null, ultimoPlan = null, ultimaPeticion = null, mapa = null, capa = null;
  let diaElegido = 0, capasDia = [], extras = {}, origenMapa = null, destinoElegido = null;
  const EXPLICA_MODO = {
    circulo: 'Recorremos alrededor de donde sales y vuelves ahí.',
    ida_vuelta: 'Vas al destino con paradas en el camino y alrededor, y regresas a donde saliste.',
    ida: 'Vas al destino con paradas en el camino; el viaje termina ahí.',
    base: 'El día 1 llegas con paradas en el camino; desde el día 2 sales a pasear y vuelves a dormir al destino.',
  };
  // Igual que el servidor (apps/rutas/optimizador.py): línea recta × 1.35, 30 km/h en ciudad y 70 en carretera.
  const FACTOR_CARRETERA = 1.35;
  function minutosDeManejo(km) {
    if (km < 0.3) return 0;
    return Math.round(km / (km < 15 ? 30 : 70) * 60) + 10;
  }
  function kmEnLinea(a, b) {
    const rad = Math.PI / 180;
    const h = Math.sin((b.lat - a.lat) * rad / 2) ** 2 +
      Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin((b.lng - a.lng) * rad / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  }

  // ── Utilidades de DOM ───────────────────────────────────
  function elemento(etiqueta, texto, clase) {
    const nodo = document.createElement(etiqueta);
    if (texto !== undefined && texto !== null) nodo.textContent = texto;
    if (clase) nodo.className = clase;
    return nodo;
  }
  function enlace(texto, url, clase) {
    const a = elemento('a', texto, clase);
    a.href = url;
    return a;
  }
  function externo(texto, url, clase, aviso = ' (se abre en otra pestaña)') {
    const a = enlace(texto, url, clase);
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.append(elemento('span', aviso, 'sr-only'));
    return a;
  }
  function duracion(minutos) {
    const h = Math.floor(minutos / 60), m = minutos % 60;
    return h ? `${h} h${m ? ` ${m} min` : ''}` : `${m} min`;
  }
  function minutos(hora) {
    const [h, m] = (hora || '').split(':').map(Number);
    return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : NaN;
  }
  function fechaCorta(iso) {
    const [anio, mes, dia] = iso.split('-').map(Number);
    return {dia, mes: MESES[mes - 1], anio};
  }
  function fechaDia(dia) {
    const {dia: numero, mes} = fechaCorta(dia.fecha);
    return `${DIAS_SEMANA[dia.dia_semana]} ${numero} ${mes}`;
  }
  function precioTexto(precio) {
    if (precio === null) return 'Precio de entrada desconocido';
    return +precio ? `Entrada: ${pesos.format(+precio)} por persona` : 'Entrada libre';
  }
  function desplazar(nodo) {
    nodo.scrollIntoView({behavior: sinMovimiento.matches ? 'auto' : 'smooth', block: 'start'});
  }
  function plural(n, uno, varios) { return `${n} ${n === 1 ? uno : varios}`; }

  // ── Formulario: atajos, contador y ubicación ────────────
  function marcarAtajos(selector, coincide) {
    form.querySelectorAll(selector).forEach(boton => boton.setAttribute('aria-pressed', String(coincide(boton))));
  }
  const atajosFecha = () => marcarAtajos('[data-fecha]', b => b.dataset.fecha === campoFecha.value);
  const atajosHorario = () => marcarAtajos('[data-inicio]', b => b.dataset.inicio === form.elements.hora_inicio.value &&
    b.dataset.fin === form.elements.hora_fin.value);
  form.querySelectorAll('[data-fecha]').forEach(boton => boton.addEventListener('click', () => {
    campoFecha.value = boton.dataset.fecha;
    atajosFecha();
    limpiarError('cuando');
  }));
  form.querySelectorAll('[data-inicio]').forEach(boton => boton.addEventListener('click', () => {
    form.elements.hora_inicio.value = boton.dataset.inicio;
    form.elements.hora_fin.value = boton.dataset.fin;
    atajosHorario();
    limpiarError('cuando');
  }));
  campoFecha.addEventListener('input', atajosFecha);
  form.elements.hora_inicio.addEventListener('input', atajosHorario);
  form.elements.hora_fin.addEventListener('input', atajosHorario);
  form.querySelectorAll('[data-paso]').forEach(boton => boton.addEventListener('click', () => {
    const actual = parseInt(campoPersonas.value, 10) || 1;
    campoPersonas.value = Math.min(20, Math.max(1, actual + Number(boton.dataset.paso)));
    limpiarError('personas');
  }));
  form.querySelectorAll('[name="intereses"]').forEach(casilla => casilla.addEventListener('change', () => limpiarError('intereses')));

  botonUbicacion.addEventListener('click', () => {
    if (ubicacion) {
      ubicacion = null;
      selectMunicipio.disabled = false;
      botonUbicacion.textContent = 'Salir desde mi ubicación';
      botonUbicacion.setAttribute('aria-pressed', 'false');
      estadoUbicacion.textContent = '';
      revisarTiempo();
      return;
    }
    if (!navigator.geolocation) { estadoUbicacion.textContent = 'Tu navegador no ofrece ubicación. Elige un municipio.'; return; }
    estadoUbicacion.textContent = 'Esperando tu ubicación…';
    navigator.geolocation.getCurrentPosition(posicion => {
      ubicacion = {latitud: +posicion.coords.latitude.toFixed(5), longitud: +posicion.coords.longitude.toFixed(5)};
      selectMunicipio.disabled = true;
      botonUbicacion.textContent = 'Usar un municipio';
      botonUbicacion.setAttribute('aria-pressed', 'true');
      // Solo se usa para calcular esta ruta; no se guarda.
      estadoUbicacion.textContent = 'Saldremos desde donde estás. No guardamos tu ubicación.';
      revisarTiempo();
    }, () => { estadoUbicacion.textContent = 'No pudimos obtener tu ubicación. Elige un municipio de la lista.'; },
    {timeout: 15000, maximumAge: 60000});
  });

  // ── A dónde vas y tipo de viaje ─────────────────────────
  const modoElegido = () => form.querySelector('[name="modo"]:checked').value;
  function puntoDeSalida() {
    if (ubicacion) return {lat: ubicacion.latitud, lng: ubicacion.longitud, nombre: 'tu ubicación'};
    const opcion = selectMunicipio.selectedOptions[0];
    return opcion ? {lat: +opcion.dataset.lat, lng: +opcion.dataset.lng, nombre: opcion.textContent} : null;
  }
  // Aviso antes de calcular: si el puro trayecto no cabe en el horario, sugerimos más días. No impide armarla.
  function revisarTiempo() {
    const modo = modoElegido(), salida = puntoDeSalida();
    const inicio = minutos(form.elements.hora_inicio.value), fin = minutos(form.elements.hora_fin.value);
    const dias = +new FormData(form).get('dias');
    advertencia.textContent = '';
    if (modo === 'circulo' || !destinoElegido || !salida || !(fin > inicio)) return;
    const directo = minutosDeManejo(kmEnLinea(salida, destinoElegido) * FACTOR_CARRETERA);
    const porDia = fin - inicio;
    const [necesario, disponible, como] = modo === 'ida_vuelta' ? [2 * directo, porDia * dias, 'ida y vuelta']
      : modo === 'base' ? [directo, porDia, 'el primer día'] : [directo, porDia * dias, 'de ida'];
    if (necesario <= disponible) return;
    const sugerencia = modo === 'base' ? 'Empieza más temprano el primer día o termina más tarde.'
      : dias < 3 ? 'Prueba con más días o con un horario más amplio.' : 'Prueba con un horario más amplio o con un destino más cercano.';
    advertencia.textContent = `Solo manejar de ${salida.nombre} a ${destinoElegido.nombre} ${como} toma unas ${duracion(necesario)} (estimado, sin paradas) y tu horario da ${duracion(disponible)}. ${sugerencia}`;
  }
  function cambiarModo() {
    const modo = modoElegido();
    explicaModo.textContent = EXPLICA_MODO[modo];
    form.elements.regresar.disabled = modo !== 'circulo';
    document.getElementById('ruta-regresar-nota').hidden = modo === 'circulo';
    limpiarError('destino');
    revisarTiempo();
  }
  function marcarModo(valor) {
    form.querySelector(`[name="modo"][value="${valor}"]`).checked = true;
    cambiarModo();
  }
  campoDestino.addEventListener('buscador:elegido', evento => {
    const elegido = evento.detail;
    destinoElegido = {nombre: elegido.nombre, lat: elegido.latitud, lng: elegido.longitud};
    valorDestino.value = `${elegido.tipo}:${elegido.slug}`;
    if (modoElegido() === 'circulo') marcarModo('ida_vuelta');
    else { limpiarError('destino'); revisarTiempo(); }
  });
  campoDestino.addEventListener('input', () => {
    // Lo escrito ya no es lo que se eligió: hay que elegir de nuevo.
    if (destinoElegido && campoDestino.value.trim() !== destinoElegido.nombre) {
      destinoElegido = null;
      valorDestino.value = '';
      revisarTiempo();
    }
    if (!campoDestino.value.trim() && modoElegido() !== 'circulo') marcarModo('circulo');
  });
  // Intro en el buscador elige una sugerencia (buscador.js); sin elegir, no debe enviar el formulario a medias.
  campoDestino.addEventListener('keydown', evento => {
    if (evento.key === 'Enter') evento.preventDefault();
  });
  form.querySelectorAll('[name="modo"]').forEach(radio => radio.addEventListener('change', cambiarModo));
  [selectMunicipio, form.elements.hora_inicio, form.elements.hora_fin, ...form.querySelectorAll('[name="dias"]')]
    .forEach(campo => campo.addEventListener('change', revisarTiempo));
  form.querySelectorAll('[data-inicio]').forEach(boton => boton.addEventListener('click', revisarTiempo));
  cambiarModo();

  // ── Validación con mensajes junto a cada paso ───────────
  function limpiarError(paso) {
    const caja = document.getElementById(`ruta-error-${paso}`);
    caja.hidden = true;
    caja.textContent = '';
    document.getElementById(`ruta-paso-${paso}`).removeAttribute('aria-invalid');
    document.getElementById(`ruta-paso-${paso}`).querySelectorAll('[aria-invalid]').forEach(c => c.removeAttribute('aria-invalid'));
  }
  function validar(cuerpo) {
    const errores = [];
    const agregar = (paso, texto, campo) => errores.push({paso, texto, campo});
    if (!cuerpo.fecha || cuerpo.fecha < campoFecha.min) agregar('cuando', 'Elige una fecha de hoy en adelante.', campoFecha);
    else if (campoFecha.max && cuerpo.fecha > campoFecha.max) agregar('cuando', 'Elige una fecha dentro del próximo año.', campoFecha);
    const inicio = minutos(cuerpo.hora_inicio), fin = minutos(cuerpo.hora_fin);
    if (Number.isNaN(inicio) || Number.isNaN(fin)) {
      agregar('cuando', 'Indica a qué hora empiezas y a qué hora terminas.', form.elements.hora_inicio);
    } else if (fin <= inicio) {
      agregar('cuando', 'La hora de terminar debe ser después de la de empezar.', form.elements.hora_fin);
    } else if (fin - inicio < MINIMO_MINUTOS) {
      agregar('cuando', 'Deja al menos 3 horas entre que empiezas y terminas, para que dé tiempo de visitar algo.', form.elements.hora_fin);
    }
    if (cuerpo.modo !== 'circulo' && !cuerpo.destino) {
      agregar('destino', campoDestino.value.trim() ? 'Elige el destino de la lista de sugerencias.' : 'Escribe a dónde vas o elige «Sin destino».', campoDestino);
    } else if (cuerpo.modo === 'base' && cuerpo.dias < 2) {
      agregar('destino', 'Para quedarte en el destino elige al menos 2 días.', form.querySelector('[name="modo"]:checked'));
    }
    if (!cuerpo.intereses.length) {
      agregar('intereses', 'Elige al menos una cosa que te guste.', form.querySelector('[name="intereses"]'));
    }
    if (!Number.isInteger(cuerpo.personas) || cuerpo.personas < 1 || cuerpo.personas > 20) {
      agregar('personas', 'Indica entre 1 y 20 personas.', campoPersonas);
    }
    if (cuerpo.presupuesto !== null && !(+cuerpo.presupuesto >= 0)) {
      agregar('personas', 'El presupuesto debe ser una cantidad en pesos, sin signos.', form.elements.presupuesto);
    }
    return errores;
  }
  function mostrarErrores(errores) {
    ['destino', 'cuando', 'intereses', 'personas'].forEach(limpiarError);
    errores.forEach(({paso, texto, campo}) => {
      const caja = document.getElementById(`ruta-error-${paso}`);
      caja.textContent = caja.textContent ? `${caja.textContent} ${texto}` : texto;
      caja.hidden = false;
      document.getElementById(`ruta-paso-${paso}`).setAttribute('aria-invalid', 'true');
      if (campo && campo.type !== 'checkbox') campo.setAttribute('aria-invalid', 'true');
    });
    if (errores.length) {
      if (errores[0].campo?.closest('details')) errores[0].campo.closest('details').open = true;
      errores[0].campo?.focus();
    }
  }
  function avisar(texto, esError = false) {
    estado.textContent = texto;
    estado.classList.toggle('es-error', esError);
  }

  function peticion() {
    const datos = new FormData(form);
    const cuerpo = {
      fecha: datos.get('fecha'), dias: +datos.get('dias'), hora_inicio: datos.get('hora_inicio'),
      hora_fin: datos.get('hora_fin'), intereses: datos.getAll('intereses'), ritmo: datos.get('ritmo') || 'normal',
      personas: Number(datos.get('personas')), presupuesto: datos.get('presupuesto') || null,
      regresar: datos.get('regresar') === 'on', modo: datos.get('modo') || 'circulo',
    };
    // Sin destino se envía lo mismo de siempre, más el modo.
    if (cuerpo.modo !== 'circulo') {
      cuerpo.destino = datos.get('destino') || '';
      cuerpo.regresar = cuerpo.modo === 'ida_vuelta';
    }
    return ubicacion ? {...cuerpo, ...ubicacion} : {...cuerpo, municipio: datos.get('municipio')};
  }

  form.addEventListener('submit', async evento => {
    evento.preventDefault();
    if (botonEnviar.disabled) return;
    const cuerpo = peticion();
    const errores = validar(cuerpo);
    mostrarErrores(errores);
    if (errores.length) {
      avisar(errores.length === 1 ? 'Revisa el dato marcado.' : 'Revisa los datos marcados.', true);
      return;
    }
    botonEnviar.disabled = true;
    avisar('Armando tu ruta… puede tardar unos segundos.');
    try {
      const plan = await InfoTrip.api('/api/v1/rutas/planear/', {method: 'POST', body: cuerpo, auth: InfoTrip.hasSession()});
      ultimaPeticion = cuerpo;
      mostrar(plan);
      const sitios = plan.totales.sitios;
      avisar(sitios ? `Listo: ${plural(sitios, 'sitio', 'sitios')} en ${plural(plan.dias.length, 'día', 'días')}.` : 'No encontramos sitios que quepan. Mira las sugerencias.');
      desplazar(resultado);
    } catch (error) {
      avisar(`No pudimos armar la ruta. ${error.message}`, true);
    } finally {
      botonEnviar.disabled = false;
    }
  });

  // ── Mapa ────────────────────────────────────────────────
  function prepararMapa() {
    if (mapa || !window.L || !window.InfoTripMapa) {
      if (!window.L || !window.InfoTripMapa) document.getElementById('ruta-mapa').textContent = 'No se pudo cargar el mapa. El itinerario se muestra abajo.';
      return;
    }
    mapa = InfoTripMapa.crear('ruta-mapa');
    mapa.setView(InfoTripMapa.CENTRO_JALISCO, InfoTripMapa.ZOOM_JALISCO);
    capa = L.featureGroup().addTo(mapa);
  }
  function numerado(numero, dia) {
    return L.divIcon({
      className: 'pin-envoltura',
      html: `<span class="pin-ruta dia-${dia % COLORES}">${numero}</span>`,
      iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -14],
    });
  }
  function popup(texto, url) {
    const caja = elemento('div');
    caja.append(enlace(texto, url));
    return caja;
  }
  function dibujarMapa(plan) {
    if (!mapa) return;
    mapa.invalidateSize();
    capa.clearLayers();
    capasDia = [];
    origenMapa = [plan.origen.latitud, plan.origen.longitud];
    L.marker(origenMapa, {icon: InfoTripMapa.icono({}, true), title: plan.origen.nombre, alt: plan.origen.nombre})
      .bindPopup(elemento('strong', `Salida: ${plan.origen.nombre}`)).addTo(capa);
    const viaje = plan.viaje || {modo: 'circulo'};
    const puntoDestino = viaje.destino ? [viaje.destino.latitud, viaje.destino.longitud] : null;
    const final = puntoDestino && ['ida', 'base'].includes(viaje.modo) ? puntoDestino : null;
    if (puntoDestino) {
      L.marker(puntoDestino, {icon: InfoTripMapa.icono({}, true), title: viaje.destino.nombre, alt: `Destino: ${viaje.destino.nombre}`})
        .bindPopup(popup(`Destino: ${viaje.destino.nombre}`, viaje.destino.url)).addTo(capa);
    }
    let anterior = origenMapa;
    plan.dias.forEach((dia, numero) => {
      if (viaje.modo === 'base' && numero) anterior = final;
      const grupo = {marcadores: [], linea: null, puntos: [anterior]};
      dia.paradas.forEach((parada, indice) => {
        const punto = [parada.destino.latitud, parada.destino.longitud];
        grupo.puntos.push(punto);
        grupo.marcadores.push(L.marker(punto, {icon: numerado(indice + 1, numero), title: parada.destino.nombre,
          alt: `Día ${numero + 1}, parada ${indice + 1}: ${parada.destino.nombre}`})
          .bindPopup(popup(`Día ${numero + 1} · ${indice + 1}. ${parada.destino.nombre}`, parada.destino.url)).addTo(capa));
        if (parada.comida) {
          grupo.marcadores.push(L.marker([parada.comida.latitud, parada.comida.longitud], {icon: InfoTripMapa.iconoLugar('comer'),
            title: parada.comida.nombre, alt: parada.comida.nombre}).bindPopup(popup(parada.comida.nombre, parada.comida.url)).addTo(capa));
        }
      });
      if (dia.dormir) {
        grupo.marcadores.push(L.marker([dia.dormir.latitud, dia.dormir.longitud], {icon: InfoTripMapa.iconoLugar('dormir'),
          title: dia.dormir.nombre, alt: dia.dormir.nombre}).bindPopup(popup(dia.dormir.nombre, dia.dormir.url)).addTo(capa));
      }
      const trazo = [...grupo.puntos];
      const ultimo = numero === plan.dias.length - 1;
      if (final && (viaje.modo === 'base' || ultimo)) trazo.push(final);
      else if (ultimo && ultimaPeticion.regresar && dia.paradas.length) trazo.push(origenMapa);
      // Líneas rectas entre paradas: indican el orden, no el camino por carretera.
      if (trazo.length > 1) {
        grupo.linea = L.polyline(trazo, {className: `ruta-linea dia-${numero % COLORES}`, color: colorDia(numero),
          weight: 3, opacity: .85, dashArray: '6 6'}).addTo(capa);
      }
      if (dia.paradas.length) anterior = grupo.puntos[grupo.puntos.length - 1];
      capasDia.push(grupo);
    });
  }
  function colorDia(numero) {
    return getComputedStyle(document.querySelector('.planeador')).getPropertyValue(`--dia-${numero % COLORES}`).trim() || '#0A7564';
  }
  function resaltarEnMapa(numero) {
    if (!mapa) return;
    capasDia.forEach((grupo, i) => {
      const activo = i === numero;
      grupo.marcadores.forEach(marcador => {
        marcador.setZIndexOffset(activo ? 1000 : 0);
        marcador.setOpacity(activo ? 1 : 0.55);
      });
      grupo.linea?.setStyle({weight: activo ? 5 : 2, opacity: activo ? .95 : .35});
      if (activo) grupo.linea?.bringToFront();
    });
    const puntos = capasDia[numero]?.puntos || [];
    const limites = puntos.length > 1 ? L.latLngBounds(puntos) : capa.getBounds();
    if (limites.isValid()) mapa.fitBounds(limites.pad(0.15), {maxZoom: 14, animate: !sinMovimiento.matches});
  }

  // ── Resumen y tarjetas de día ───────────────────────────
  function mostrar(plan) {
    ultimoPlan = plan;
    extras = {};
    vacio.hidden = true;
    resultado.hidden = false;
    prepararMapa();
    const t = plan.totales;
    document.getElementById('ruta-resumen').replaceChildren(
      elemento('strong', `${plural(t.sitios, 'sitio', 'sitios')} en ${plural(plan.dias.length, 'día', 'días')}`),
      elemento('span', `${t.km} km de recorrido`),
      elemento('span', `${duracion(t.manejo_min)} al volante`),
      elemento('span', `Entradas: ${pesos.format(+t.costo_entradas)} para ${plural(t.personas, 'persona', 'personas')}`),
    );
    document.getElementById('ruta-avisos').replaceChildren(...plan.avisos.map(texto => elemento('li', texto)));
    dibujarTarjetas(plan);
    dibujarMapa(plan);
    const m = plan.metodo;
    const comparacion = m.voraz.puntaje > 0
      ? ` Un método simple, que siempre va al sitio que más rinde en ese momento, logra ${m.voraz.sitios} sitios y un puntaje de ${m.voraz.puntaje}; esta ruta logra ${m.puntaje}.`
      : '';
    document.getElementById('ruta-metodo').textContent =
      `Revisamos ${m.candidatos} sitios cercanos y afines a tus intereses. Un algoritmo genético probó miles de órdenes de visita durante ${m.generaciones} generaciones (${m.segundos} s) y se quedó con el que suma más de lo que te interesa sin pasarse de horarios, del día ni del presupuesto.${comparacion}`;
    botonGuardar.hidden = !t.sitios;
    estadoGuardar.textContent = '';
    botonCompartir.hidden = !t.sitios;
    estadoCompartir.textContent = '';
    panelCompartir.hidden = true;
    elegirDia(0);
    cargarExtras(plan);
  }

  function dibujarTarjetas(plan) {
    tarjetas.replaceChildren(...plan.dias.map((dia, numero) => {
      const boton = elemento('button', '', `planeador-dia-tarjeta dia-${numero % COLORES}`);
      boton.type = 'button';
      boton.dataset.dia = numero;
      boton.setAttribute('aria-controls', 'ruta-detalle');
      boton.setAttribute('aria-pressed', 'false');
      const datos = elemento('span', '', 'dia-datos');
      if (dia.paradas.length) {
        const km = dia.paradas.reduce((suma, p) => suma + p.km, 0);
        datos.append(elemento('span', plural(dia.paradas.length, 'parada', 'paradas')),
          elemento('span', `${Math.round(km * 10) / 10} km`),
          elemento('span', `${dia.paradas[0].llegada}–${dia.paradas[dia.paradas.length - 1].salida}`));
      } else {
        datos.append(elemento('span', 'Sin paradas este día'));
      }
      boton.append(elemento('span', `Día ${numero + 1}`, 'dia-titulo'), elemento('span', fechaDia(dia), 'dia-fecha'),
        datos, elemento('span', '', 'dia-estado'));
      boton.addEventListener('click', () => elegirDia(numero));
      return boton;
    }));
  }

  function elegirDia(numero) {
    diaElegido = numero;
    tarjetas.querySelectorAll('.planeador-dia-tarjeta').forEach((boton, i) => {
      boton.setAttribute('aria-pressed', String(i === numero));
      boton.querySelector('.dia-estado').textContent = i === numero ? '✓ Viendo este día' : 'Ver paradas';
    });
    dibujarDetalle(ultimoPlan, numero);
    resaltarEnMapa(numero);
  }

  // ── Detalle del día: paradas, comida y dónde dormir ─────
  function lugarUtil(titulo, lugar) {
    const fila = elemento('li', '', 'planeador-util');
    fila.append(elemento('strong', titulo));
    if (lugar) {
      fila.append(enlace(lugar.nombre, lugar.url), elemento('span', `${lugar.subtipo} · a ${lugar.distancia}`));
    } else {
      fila.append(elemento('span', 'no tenemos un lugar registrado cerca.'));
    }
    return fila;
  }

  function dibujarDetalle(plan, numero) {
    const dia = plan.dias[numero];
    const titulo = elemento('h3', `Día ${numero + 1} · ${fechaDia(dia)}`);
    detalle.className = `planeador-detalle dia-${numero % COLORES}`;
    detalle.setAttribute('aria-label', `Paradas del día ${numero + 1}`);
    if (!dia.paradas.length) {
      detalle.replaceChildren(titulo, elemento('p', 'Este día no cabe ninguna visita con esos datos. Prueba con más horas o más intereses.'));
      return;
    }
    const lista = elemento('ol', '', 'planeador-paradas');
    dia.paradas.forEach((parada, indice) => {
      lista.append(dibujarParada(parada, indice));
      if (parada.comida_despues) lista.append(lugarUtil('Hora de comer:', parada.comida));
    });
    if (dia.dormir !== null) lista.append(lugarUtil('Dormir:', dia.dormir));
    detalle.replaceChildren(titulo, elemento('p', 'Horas estimadas. Toca el nombre de un lugar para ver su ficha completa.'),
      enlaceDelDia(dia, numero), lista);
  }

  // Todo el día en Google Maps, con sus paradas en orden.
  function enlaceDelDia(dia, numero) {
    const caja = elemento('p', '', 'parada-acciones planeador-dia-mapa');
    if (!dia.google_maps) return caja;
    caja.append(externo(`Abrir el día ${numero + 1} en Google Maps`, dia.google_maps.url, '', ' (se abre en otra pestaña)'));
    const {incluidas, total} = dia.google_maps;
    if (incluidas < total) caja.append(elemento('span', `Incluye las primeras ${incluidas} de ${total} paradas.`, 'planeador-ayuda'));
    return caja;
  }

  function hora(etiqueta, valor) {
    const fila = elemento('div');
    fila.append(elemento('dt', etiqueta), elemento('dd', valor));
    return fila;
  }

  function dibujarParada(parada, indice) {
    const d = parada.destino;
    const item = elemento('li', '', 'parada');
    item.dataset.destino = d.id;
    const cuerpo = elemento('div', '', 'parada-cuerpo');
    const cabeza = elemento('div');
    const nombre = elemento('h4');
    nombre.append(enlace(d.nombre, d.url));
    cabeza.append(nombre, elemento('span', d.municipio, 'parada-municipio'));
    const horas = elemento('dl', '', 'parada-horas');
    horas.append(hora('Llegas', parada.llegada), hora(parada.llegada === parada.inicio ? 'Visita' : 'Abre', parada.inicio),
      hora('Sales', parada.salida));
    const meta = elemento('p', '', 'parada-meta');
    meta.append(elemento('span', `Visita de ${duracion(parada.visita_min)}`), elemento('span', precioTexto(parada.precio)));
    if (parada.manejo_min) meta.append(elemento('span', `${duracion(parada.manejo_min)} de camino (${parada.km} km)`));
    cuerpo.append(cabeza, horas, meta);
    const notas = [];
    if (parada.llegada !== parada.inicio) notas.push(`Llegas a las ${parada.llegada} y abre a las ${parada.inicio}.`);
    if (parada.guiado) notas.push('Solo con recorrido guiado: llega a la hora de una salida.');
    if (!parada.horario_confirmado) notas.push('Horario no confirmado: supusimos uno habitual. Confírmalo antes de ir.');
    if (notas.length) cuerpo.append(elemento('p', notas.join(' '), 'parada-nota'));
    const extra = elemento('div', '', 'parada-extra');
    extra.dataset.extra = d.id;
    llenarExtra(extra, d);
    const acciones = elemento('div', '', 'parada-acciones');
    acciones.append(enlace('Ver ficha', d.url, 'principal'),
      externo('Cómo llegar', `https://www.google.com/maps/dir/?api=1&destination=${d.latitud},${d.longitud}`, '',
        ' (abre Google Maps en otra pestaña)'));
    cuerpo.append(extra, acciones);
    item.append(elemento('span', String(indice + 1), 'parada-num'), cuerpo);
    item.firstChild.setAttribute('aria-hidden', 'true');
    return item;
  }

  // ── Descripción, horario y precio con fuente, y reseñas ─
  async function cargarExtras(plan) {
    const claves = [...new Set(plan.dias.flatMap(d => d.paradas.map(p => p.destino.id)))];
    if (!claves.length) return;
    const pedido = plan;
    const lotes = [];
    for (let i = 0; i < claves.length; i += 30) lotes.push(claves.slice(i, i + 30));
    try {
      const respuestas = await Promise.all(lotes.map(lote =>
        InfoTrip.api(`/api/v1/rutas/paradas/?destinos=${lote.join(',')}`, {auth: false})));
      if (pedido !== ultimoPlan) return;
      respuestas.forEach(r => r.destinos.forEach(info => { extras[info.id] = info; }));
    } catch {
      if (pedido !== ultimoPlan) return;
      claves.forEach(clave => { extras[clave] = {error: true}; });
    }
    detalle.querySelectorAll('[data-extra]').forEach(caja => {
      const destino = ultimoPlan.dias.flatMap(d => d.paradas).find(p => String(p.destino.id) === caja.dataset.extra)?.destino;
      if (destino) llenarExtra(caja, destino);
    });
  }

  function textoConEnlaces(texto) {
    const fragmento = document.createDocumentFragment();
    texto.split(/(https?:\/\/[^\s]+)/).forEach((parte, i) => {
      if (!parte) return;
      fragmento.append(i % 2 ? externo(parte.replace(/^https?:\/\//, '').split('/')[0], parte) : document.createTextNode(parte));
    });
    return fragmento;
  }
  function fechaLarga(iso) {
    if (!iso) return '';
    const {dia, mes, anio} = fechaCorta(iso);
    return `${dia} ${mes} ${anio}`;
  }
  function bloque(titulo) {
    const caja = elemento('section', '', 'parada-bloque');
    caja.append(elemento('h5', titulo));
    return caja;
  }

  function llenarExtra(caja, destino) {
    const info = extras[destino.id];
    if (!info) {
      caja.replaceChildren(elemento('p', 'Cargando qué hacer, horarios y reseñas…', 'parada-cargando'));
      return;
    }
    if (info.error) {
      const aviso = elemento('p', 'No pudimos cargar la descripción ni las reseñas. ', 'parada-cargando');
      aviso.append(enlace('Míralas en la ficha', destino.url));
      caja.replaceChildren(aviso);
      return;
    }
    caja.replaceChildren(bloqueQueHacer(info), bloquePractico(info, destino), bloqueResenas(info, destino));
  }

  function bloqueQueHacer(info) {
    const caja = bloque('Qué hacer');
    const texto = (info.descripcion || '').trim();
    if (!texto) {
      caja.append(elemento('p', 'Aún no tenemos una descripción de este lugar.'));
      return caja;
    }
    const parrafo = elemento('p', texto);
    caja.append(parrafo);
    if (texto.length > LARGO_DESCRIPCION) {
      parrafo.classList.add('parada-texto-corto');
      parrafo.id = `parada-texto-${info.id}-${diaElegido}`;
      const boton = elemento('button', 'Leer más', 'planeador-chip');
      boton.type = 'button';
      boton.setAttribute('aria-expanded', 'false');
      boton.setAttribute('aria-controls', parrafo.id);
      boton.addEventListener('click', () => {
        const abierto = parrafo.classList.toggle('parada-texto-corto') === false;
        boton.setAttribute('aria-expanded', String(abierto));
        boton.textContent = abierto ? 'Leer menos' : 'Leer más';
      });
      caja.append(boton);
    }
    return caja;
  }

  function bloquePractico(info, destino) {
    const caja = bloque('Horario y precio');
    if (!info.practicos.length) {
      const nada = elemento('p', 'Aún no hay horario ni precio publicados con su fuente. ');
      nada.append(enlace('¿Los conoces? Compártelos', `${destino.url}#reportar-gasto`));
      caja.append(nada);
      return caja;
    }
    info.practicos.forEach(dato => {
      const fila = elemento('div', '', 'parada-dato');
      fila.append(elemento('strong', dato.nombre), elemento('span', dato.texto));
      if (dato.fuente || dato.fecha_dato) {
        const fuente = elemento('span', '', 'parada-fuente');
        if (dato.fuente) fuente.append(document.createTextNode('Fuente: '), textoConEnlaces(dato.fuente));
        if (dato.fecha_dato) fuente.append(document.createTextNode(`${dato.fuente ? ' · ' : ''}consultado el ${fechaLarga(dato.fecha_dato)}`));
        fila.append(fuente);
      }
      caja.append(fila);
    });
    return caja;
  }

  function estrellas(calificacion) {
    const caja = elemento('span', '', 'resena-estrellas');
    const visibles = elemento('span', '★'.repeat(calificacion) + '☆'.repeat(5 - calificacion));
    visibles.setAttribute('aria-hidden', 'true');
    caja.append(visibles, elemento('span', `${calificacion} de 5 estrellas`, 'sr-only'));
    return caja;
  }

  function bloqueResenas(info, destino) {
    const caja = bloque(info.total_resenas ? `Reseñas · ${info.promedio} de 5 (${plural(info.total_resenas, 'reseña', 'reseñas')})` : 'Reseñas');
    if (!info.resenas.length) {
      const vacio = elemento('p', 'Aún no hay reseñas de este lugar. ¿Ya fuiste? Cuéntanos cómo te fue: ', 'parada-sin-resenas');
      vacio.append(enlace('Compartir mi experiencia', `${destino.url}#reportar-gasto`));
      caja.append(vacio);
      return caja;
    }
    const lista = elemento('ul', '', 'parada-resenas');
    info.resenas.forEach(resena => {
      const item = elemento('li', '', 'parada-resena');
      const autor = [resena.autor_nombre];
      if (resena.fecha_visita) {
        const {mes, anio} = fechaCorta(resena.fecha_visita);
        autor.push(`visitó en ${mes} ${anio}`);
      }
      if (resena.visita_comprobada) autor.push('visita comprobada');
      const texto = elemento('p', resena.texto, 'parada-texto-corto');
      item.append(estrellas(resena.calificacion), texto, elemento('span', autor.join(' · '), 'resena-autor'));
      lista.append(item);
    });
    caja.append(lista);
    const todas = elemento('p');
    todas.append(enlace(info.total_resenas > info.resenas.length ? `Ver las ${info.total_resenas} reseñas` : 'Ver reseñas en la ficha',
      `${destino.url}#community-title`));
    caja.append(todas);
    return caja;
  }

  // ── Compartir por enlace ────────────────────────────────
  botonCompartir.addEventListener('click', async () => {
    if (botonCompartir.disabled || !ultimaPeticion) return;
    const plan = ultimoPlan;
    botonCompartir.disabled = true;
    estadoCompartir.textContent = 'Creando el enlace…';
    try {
      const ruta = await InfoTrip.api('/api/v1/rutas/compartidas/', {method: 'POST', body: ultimaPeticion, auth: InfoTrip.hasSession()});
      if (plan !== ultimoPlan) return;
      const url = location.origin + ruta.url;
      InfoTripCompartirRuta.conectar(panelCompartir, ruta.titulo, url);
      document.getElementById('ruta-ics').href = `${ruta.url}calendario.ics`;
      document.getElementById('ruta-ver').href = ruta.url;
      const notas = [];
      if (ultimaPeticion.latitud !== undefined) notas.push(`No guardamos tu ubicación: la ruta dice «${ruta.titulo.split(' desde ').pop()}».`);
      notas.push(InfoTrip.hasSession()
        ? 'Queda en tu perfil, donde puedes borrarla cuando quieras.'
        : `Cualquiera con el enlace puede verla hasta el ${new Date(ruta.caduca).toLocaleDateString('es-MX', {day: 'numeric', month: 'long', year: 'numeric'})}.`);
      panelCompartir.querySelector('[data-compartir-nota]').textContent = notas.join(' ');
      panelCompartir.hidden = false;
      estadoCompartir.textContent = 'Listo: tu ruta ya tiene enlace.';
      const campo = document.getElementById('ruta-enlace');
      campo.focus();
      campo.select();
    } catch (error) {
      estadoCompartir.textContent = `No pudimos crear el enlace. ${error.message}`;
    } finally {
      botonCompartir.disabled = false;
    }
  });

  // ── Guardar en Mis viajes ───────────────────────────────
  function comoViaje(plan, cuerpo) {
    const actividades = [];
    plan.dias.forEach((dia, numero) => {
      dia.paradas.forEach(parada => {
        const precio = parada.precio === null ? 'precio desconocido' : `${pesos.format(+parada.precio)} por persona`;
        actividades.push({dia: numero + 1, hora: parada.inicio, titulo: parada.destino.nombre.slice(0, 150),
          notas: `Visita de ${duracion(parada.visita_min)} · ${precio}${parada.horario_confirmado ? '' : ' · horario no confirmado'}`});
        if (parada.comida_despues) {
          actividades.push({dia: numero + 1, hora: parada.salida,
            titulo: parada.comida ? `Comer: ${parada.comida.nombre}`.slice(0, 150) : 'Comer', notas: ''});
        }
      });
      if (dia.dormir) actividades.push({dia: numero + 1, hora: '', titulo: `Dormir: ${dia.dormir.nombre}`.slice(0, 150), notas: ''});
    });
    const municipios = [...new Set(plan.dias.flatMap(d => d.paradas.map(p => p.destino.municipio)))];
    const ultimo = plan.dias[plan.dias.length - 1].fecha;
    return {
      nombre: `Ruta desde ${plan.origen.nombre}`.slice(0, 120), destino: municipios.join(', ').slice(0, 200),
      fecha_inicio: plan.dias[0].fecha, fecha_fin: ultimo, personas: cuerpo.personas,
      presupuesto: cuerpo.presupuesto || plan.totales.costo_entradas, gastos: [], actividades,
      lugares: [...new Set(plan.dias.flatMap(d => d.paradas.map(p => p.destino.id)))],
      notas: 'Armada con el planeador de InfoTrip. Horarios y tiempos de manejo son estimados: confírmalos antes de ir.',
    };
  }

  botonGuardar.addEventListener('click', async () => {
    if (!InfoTrip.hasSession()) {
      estadoGuardar.replaceChildren(document.createTextNode('Para guardarla, '), enlace('inicia sesión', InfoTrip.loginUrl()),
        document.createTextNode(' y vuelve a armarla.'));
      return;
    }
    botonGuardar.disabled = true;
    estadoGuardar.textContent = 'Guardando…';
    try {
      await InfoTrip.api('/api/v1/mis-viajes/', {method: 'POST', body: comoViaje(ultimoPlan, ultimaPeticion)});
      estadoGuardar.replaceChildren(document.createTextNode('Guardada. '), enlace('Ver en Mis viajes', '/mis-viajes/'));
    } catch (error) {
      estadoGuardar.textContent = error.message;
    } finally {
      botonGuardar.disabled = false;
    }
  });
})();
