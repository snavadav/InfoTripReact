(() => {
  'use strict';
  const form = document.getElementById('propuesta-form');
  const estadoForm = form.querySelector('.form-status');
  const punto = document.getElementById('propuesta-punto');
  const parecidos = document.getElementById('propuesta-parecidos');
  const lista = document.getElementById('propuesta-parecidos-lista');
  const botonUbicacion = document.getElementById('propuesta-ubicacion');
  let marcador = null, mapa = null;

  document.getElementById('propuesta-acceso').hidden = InfoTrip.hasSession();

  function colocar(latlng) {
    if (marcador) marcador.setLatLng(latlng);
    else {
      marcador = L.marker(latlng, {icon: InfoTripMapa.icono({}, true), draggable: true, title: 'Lugar propuesto', alt: 'Lugar propuesto'}).addTo(mapa);
      marcador.on('dragend', () => { mostrarPunto(); parecidos.hidden = true; });
    }
    mostrarPunto();
    parecidos.hidden = true;
  }
  function mostrarPunto() {
    const {lat, lng} = marcador.getLatLng();
    punto.textContent = `${InfoTripMapa.formatoCoordenadas(lat, lng)}. Arrastra el marcador para ajustarlo.`;
  }

  if (window.L && window.InfoTripMapa) {
    mapa = InfoTripMapa.crear('propuesta-mapa');
    mapa.setView(InfoTripMapa.CENTRO_JALISCO, InfoTripMapa.ZOOM_JALISCO);
    mapa.on('click', evento => colocar(evento.latlng));
  } else {
    punto.textContent = 'No se pudo cargar el mapa. Revisa tu conexión y recarga la página.';
    botonUbicacion.disabled = true;
  }

  botonUbicacion.addEventListener('click', () => {
    if (!navigator.geolocation) { punto.textContent = 'Tu navegador no ofrece ubicación. Pulsa el mapa.'; return; }
    botonUbicacion.disabled = true;
    punto.textContent = 'Esperando tu ubicación…';
    navigator.geolocation.getCurrentPosition(posicion => {
      botonUbicacion.disabled = false;
      const latlng = [posicion.coords.latitude, posicion.coords.longitude];
      colocar(L.latLng(latlng));
      mapa.setView(latlng, 17);
    }, () => {
      botonUbicacion.disabled = false;
      punto.textContent = 'No pudimos obtener tu ubicación. Pulsa el mapa donde está el lugar.';
    }, {timeout: 15000, maximumAge: 60000});
  });

  function mostrarParecidos(encontrados) {
    lista.replaceChildren();
    encontrados.forEach(lugar => {
      const fila = document.createElement('li');
      const enlace = document.createElement('a');
      enlace.href = lugar.url;
      enlace.textContent = lugar.nombre;
      fila.append(enlace);
      lista.append(fila);
    });
    parecidos.hidden = false;
  }
  async function enviar(aviso, confirmarDistinto) {
    if (!InfoTrip.hasSession()) {
      aviso.replaceChildren(document.createTextNode('Entra para enviar tu propuesta. '));
      const enlace = document.createElement('a');
      enlace.href = InfoTrip.loginUrl();
      enlace.textContent = 'Iniciar sesión';
      aviso.append(enlace);
      return;
    }
    if (!marcador) { aviso.textContent = 'Pulsa el mapa para marcar dónde está el lugar.'; return; }
    const {lat, lng} = marcador.getLatLng();
    const cuerpo = {
      ...Object.fromEntries(new FormData(form)), latitud: lat.toFixed(6), longitud: lng.toFixed(6),
      confirmar_distinto: confirmarDistinto,
    };
    let respuesta;
    try {
      respuesta = await InfoTrip.api('/api/v1/lugares/propuestas/', {method: 'POST', body: cuerpo});
    } catch (error) {
      if (!error.parecidos) throw error;
      mostrarParecidos(error.parecidos);
      aviso.textContent = '';
      return;
    }
    form.reset();
    mapa.removeLayer(marcador);
    marcador = null;
    parecidos.hidden = true;
    punto.textContent = 'Pulsa el mapa donde está el lugar.';
    aviso.replaceChildren(document.createTextNode(`Recibimos «${respuesta.nombre}». Te avisaremos cuando lo revisemos. `));
    const enlace = document.createElement('a');
    enlace.href = '/perfil/';
    enlace.textContent = 'Ver mis propuestas';
    aviso.append(enlace);
  }
  form.addEventListener('submit', evento => {
    evento.preventDefault();
    InfoTrip.submit(form, aviso => enviar(aviso, false));
  });
  document.getElementById('propuesta-distinto').addEventListener('click', () => {
    if (!form.reportValidity()) return;
    InfoTrip.submit(form, aviso => enviar(aviso, true));
  });
})();
