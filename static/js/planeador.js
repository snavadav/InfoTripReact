(() => {
  'use strict';
  const form = document.getElementById('ruta-form');
  const resultado = document.getElementById('ruta-resultado');
  const botonUbicacion = document.getElementById('ruta-ubicacion');
  const estadoUbicacion = document.getElementById('ruta-ubicacion-estado');
  const selectMunicipio = document.getElementById('ruta-municipio');
  const botonGuardar = document.getElementById('ruta-guardar');
  const estadoGuardar = document.getElementById('ruta-guardar-estado');
  const DIAS_SEMANA = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
  // Un color por día; se distinguen en tema claro y oscuro.
  const COLORES = ['#0A7564', '#D2440C', '#5B5BD6'];
  const pesos = new Intl.NumberFormat('es-MX', {style: 'currency', currency: 'MXN', maximumFractionDigits: 0});
  let ubicacion = null, ultimoPlan = null, ultimaPeticion = null, mapa = null, capa = null;

  if (window.L && window.InfoTripMapa) {
    mapa = InfoTripMapa.crear('ruta-mapa');
    mapa.setView(InfoTripMapa.CENTRO_JALISCO, InfoTripMapa.ZOOM_JALISCO);
    capa = L.featureGroup().addTo(mapa);
  } else {
    document.getElementById('ruta-mapa').textContent = 'No se pudo cargar el mapa. El itinerario se muestra abajo.';
  }

  botonUbicacion.addEventListener('click', () => {
    if (ubicacion) {
      ubicacion = null;
      selectMunicipio.disabled = false;
      botonUbicacion.textContent = 'Salir desde mi ubicación';
      estadoUbicacion.textContent = '';
      return;
    }
    if (!navigator.geolocation) { estadoUbicacion.textContent = 'Tu navegador no ofrece ubicación.'; return; }
    estadoUbicacion.textContent = 'Esperando tu ubicación…';
    navigator.geolocation.getCurrentPosition(posicion => {
      ubicacion = {latitud: +posicion.coords.latitude.toFixed(5), longitud: +posicion.coords.longitude.toFixed(5)};
      selectMunicipio.disabled = true;
      botonUbicacion.textContent = 'Salir de un municipio';
      // Solo se usa para calcular esta ruta; no se guarda.
      estadoUbicacion.textContent = 'Saldremos desde donde estás. No guardamos tu ubicación.';
    }, () => { estadoUbicacion.textContent = 'No pudimos obtener tu ubicación. Elige un municipio.'; },
    {timeout: 15000, maximumAge: 60000});
  });

  function peticion() {
    const datos = new FormData(form);
    const cuerpo = {
      fecha: datos.get('fecha'), dias: +datos.get('dias'), hora_inicio: datos.get('hora_inicio'),
      hora_fin: datos.get('hora_fin'), intereses: datos.getAll('intereses'), ritmo: datos.get('ritmo'),
      personas: +datos.get('personas'), presupuesto: datos.get('presupuesto') || null,
      regresar: datos.get('regresar') === 'on',
    };
    return ubicacion ? {...cuerpo, ...ubicacion} : {...cuerpo, municipio: datos.get('municipio')};
  }

  function elemento(etiqueta, texto, clase) {
    const nodo = document.createElement(etiqueta);
    if (texto !== undefined) nodo.textContent = texto;
    if (clase) nodo.className = clase;
    return nodo;
  }
  function enlace(texto, url) {
    const a = elemento('a', texto);
    a.href = url;
    return a;
  }
  function duracion(minutos) {
    const h = Math.floor(minutos / 60), m = minutos % 60;
    return h ? `${h} h${m ? ` ${m} min` : ''}` : `${m} min`;
  }
  function fechaLegible(iso, diaSemana) {
    const [, mes, dia] = iso.split('-');
    return `${DIAS_SEMANA[diaSemana]} ${+dia}/${+mes}`;
  }

  function lugarUtil(titulo, lugar) {
    const fila = elemento('li', '', 'planeador-util');
    fila.append(elemento('span', titulo + ': '));
    if (lugar) {
      fila.append(enlace(lugar.nombre, lugar.url), elemento('small', ` · ${lugar.subtipo} · a ${lugar.distancia}`));
    } else {
      fila.append(elemento('span', 'no tenemos un lugar registrado cerca.'));
    }
    return fila;
  }

  function mostrarDias(plan) {
    const contenedor = document.getElementById('ruta-dias');
    contenedor.replaceChildren();
    plan.dias.forEach((dia, numero) => {
      const bloque = elemento('section', '', 'community-box planeador-dia');
      const titulo = elemento('h2', `Día ${numero + 1} · ${fechaLegible(dia.fecha, dia.dia_semana)}`);
      titulo.style.setProperty('--color-dia', COLORES[numero % COLORES.length]);
      bloque.append(titulo);
      if (!dia.paradas.length) bloque.append(elemento('p', 'Este día no cabe ninguna visita con esos datos.'));
      const lista = elemento('ol', '', 'planeador-paradas');
      dia.paradas.forEach(parada => {
        const fila = elemento('li');
        const cabeza = elemento('div', '', 'planeador-parada');
        cabeza.append(elemento('span', `${parada.inicio}–${parada.salida}`, 'planeador-hora'),
          enlace(parada.destino.nombre, parada.destino.url));
        fila.append(cabeza);
        const detalles = [parada.destino.municipio, `visita de ${duracion(parada.visita_min)}`];
        detalles.push(parada.precio === null ? 'precio desconocido' : +parada.precio ? `${pesos.format(+parada.precio)} por persona` : 'entrada libre');
        if (parada.manejo_min) detalles.push(`${duracion(parada.manejo_min)} de camino (${parada.km} km)`);
        fila.append(elemento('small', detalles.join(' · ')));
        const notas = [];
        if (!parada.horario_confirmado) notas.push('horario no confirmado');
        if (parada.guiado) notas.push('solo con recorrido guiado: llega a la hora de una salida');
        if (parada.llegada !== parada.inicio) notas.push(`llegas a las ${parada.llegada} y abre después`);
        if (notas.length) fila.append(elemento('small', notas.join(' · '), 'planeador-nota'));
        lista.append(fila);
        if (parada.comida_despues) lista.append(lugarUtil('Comer', parada.comida));
      });
      bloque.append(lista);
      if (dia.paradas.length && dia.dormir !== null) {
        const dormir = elemento('ul', '', 'planeador-paradas');
        dormir.append(lugarUtil('Dormir', dia.dormir));
        bloque.append(dormir);
      }
      contenedor.append(bloque);
    });
  }

  function numerado(numero, color) {
    return L.divIcon({
      className: 'pin-envoltura',
      html: `<span class="pin-ruta" style="--color-dia:${color}">${numero}</span>`,
      iconSize: [28, 28], iconAnchor: [14, 14], popupAnchor: [0, -12],
    });
  }
  function popup(texto, url) {
    const caja = elemento('div');
    caja.append(enlace(texto, url));
    return caja;
  }

  function mostrarMapa(plan) {
    if (!mapa) return;
    capa.clearLayers();
    const origen = [plan.origen.latitud, plan.origen.longitud];
    L.marker(origen, {icon: InfoTripMapa.icono({}, true), title: plan.origen.nombre, alt: plan.origen.nombre})
      .bindPopup(elemento('strong', `Salida: ${plan.origen.nombre}`)).addTo(capa);
    let anterior = origen, contador = 0;
    plan.dias.forEach((dia, numero) => {
      const color = COLORES[numero % COLORES.length];
      const trazo = [anterior];
      dia.paradas.forEach(parada => {
        contador += 1;
        const punto = [parada.destino.latitud, parada.destino.longitud];
        trazo.push(punto);
        L.marker(punto, {icon: numerado(contador, color), title: parada.destino.nombre, alt: parada.destino.nombre})
          .bindPopup(popup(`${contador}. ${parada.destino.nombre}`, parada.destino.url)).addTo(capa);
        if (parada.comida) {
          L.marker([parada.comida.latitud, parada.comida.longitud], {icon: InfoTripMapa.iconoLugar('comer'), title: parada.comida.nombre, alt: parada.comida.nombre})
            .bindPopup(popup(parada.comida.nombre, parada.comida.url)).addTo(capa);
        }
      });
      if (dia.dormir) {
        L.marker([dia.dormir.latitud, dia.dormir.longitud], {icon: InfoTripMapa.iconoLugar('dormir'), title: dia.dormir.nombre, alt: dia.dormir.nombre})
          .bindPopup(popup(dia.dormir.nombre, dia.dormir.url)).addTo(capa);
      }
      if (numero === plan.dias.length - 1 && ultimaPeticion.regresar && dia.paradas.length) trazo.push(origen);
      // Líneas rectas entre paradas: indican el orden, no el camino por carretera.
      if (trazo.length > 1) L.polyline(trazo, {color, weight: 3, opacity: .85, dashArray: '6 6'}).addTo(capa);
      if (dia.paradas.length) anterior = trazo[dia.paradas.length];
    });
    mapa.fitBounds(capa.getBounds().pad(0.15), {maxZoom: 13});
  }

  function mostrar(plan) {
    ultimoPlan = plan;
    const t = plan.totales;
    const resumen = document.getElementById('ruta-resumen');
    resumen.replaceChildren(
      elemento('strong', `${t.sitios} ${t.sitios === 1 ? 'sitio' : 'sitios'}`),
      elemento('span', `${t.km} km de recorrido`),
      elemento('span', `${duracion(t.manejo_min)} al volante`),
      elemento('span', `Entradas: ${pesos.format(+t.costo_entradas)} para ${t.personas} ${t.personas === 1 ? 'persona' : 'personas'}`),
    );
    const avisos = document.getElementById('ruta-avisos');
    avisos.replaceChildren(...plan.avisos.map(texto => elemento('li', texto)));
    mostrarDias(plan);
    mostrarMapa(plan);
    const m = plan.metodo;
    const comparacion = m.voraz.puntaje > 0
      ? ` Un método simple, que siempre va al sitio que más rinde en ese momento, logra ${m.voraz.sitios} sitios y un puntaje de ${m.voraz.puntaje}; esta ruta logra ${m.puntaje}.`
      : '';
    document.getElementById('ruta-metodo').textContent =
      `Revisamos ${m.candidatos} sitios cercanos y afines a tus intereses. Un algoritmo genético probó miles de órdenes de visita durante ${m.generaciones} generaciones (${m.segundos} s) y se quedó con el que suma más de lo que te interesa sin pasarse de horarios, del día ni del presupuesto.${comparacion}`;
    botonGuardar.hidden = !t.sitios;
    estadoGuardar.textContent = '';
    resultado.hidden = false;
  }

  form.addEventListener('submit', evento => {
    evento.preventDefault();
    InfoTrip.submit(form, async aviso => {
      const cuerpo = peticion();
      if (!cuerpo.intereses.length) { aviso.textContent = 'Elige al menos un interés.'; return; }
      aviso.textContent = 'Armando tu ruta…';
      const plan = await InfoTrip.api('/api/v1/rutas/planear/', {method: 'POST', body: cuerpo, auth: InfoTrip.hasSession()});
      ultimaPeticion = cuerpo;
      mostrar(plan);
      aviso.textContent = '';
      resultado.scrollIntoView({behavior: 'smooth', block: 'start'});
    });
  });

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
      const viaje = await InfoTrip.api('/api/v1/mis-viajes/', {method: 'POST', body: comoViaje(ultimoPlan, ultimaPeticion)});
      estadoGuardar.replaceChildren(document.createTextNode('Guardada. '), enlace('Ver en Mis viajes', '/mis-viajes/'));
    } catch (error) {
      estadoGuardar.textContent = error.message;
    } finally {
      botonGuardar.disabled = false;
    }
  });
})();
