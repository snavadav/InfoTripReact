(() => {
  'use strict';
  // Lo usan el pasaporte propio y el compartido. El compartido llega completo del servidor (sin fechas):
  // aquí solo se anima cada sello al aparecer. En el propio se añaden sellos, fechas, fotos y distancias.
  const reducir = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const observador = !reducir && 'IntersectionObserver' in window ? new IntersectionObserver(entradas => {
    entradas.forEach(entrada => {
      if (!entrada.isIntersecting) return;
      entrada.target.classList.replace('sello--espera', 'sello--estampar');
      observador.unobserve(entrada.target);
    });
  }, {threshold: .4}) : null;

  function mostrarSello(sello) {
    sello.hidden = false;
    if (!observador) return;
    sello.classList.add('sello--espera');
    observador.observe(sello);
  }
  document.querySelectorAll('.pagina--sellada [data-sello]').forEach(mostrarSello);

  const progreso = document.getElementById('pasaporte-progreso');
  if (!progreso || !window.InfoTrip) return;

  const seccion = document.getElementById('pasaporte-compartir');
  const compartir = document.getElementById('pasaporte-enlace');
  const retirar = document.getElementById('pasaporte-retirar');
  const estado = document.getElementById('pasaporte-estado');
  const plantillaFoto = document.getElementById('plantilla-mi-foto');

  // Las fechas llegan como AAAA-MM-DD; se leen en UTC para que la zona horaria no cambie el día.
  function fecha(texto) {
    const [anio, mes, dia] = texto.split('-').map(Number);
    return new Date(Date.UTC(anio, mes - 1, dia));
  }
  const largo = new Intl.DateTimeFormat('es-MX', {day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'});
  const corto = new Intl.DateTimeFormat('es-MX', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
  function fechaDeSello(texto) {
    const partes = Object.fromEntries(corto.formatToParts(fecha(texto)).map(parte => [parte.type, parte.value]));
    return `${partes.day} ${partes.month.replace('.', '').toUpperCase()} ${partes.year}`;
  }

  function pagina(slug) { return document.getElementById(`pagina-${slug}`); }

  function texto(etiqueta, clase, contenido) {
    const elemento = document.createElement(etiqueta);
    if (clase) elemento.className = clase;
    if (contenido) elemento.textContent = contenido;
    return elemento;
  }

  function sellar(sello) {
    const hoja = pagina(sello.slug);
    const nombre = hoja.dataset.nombre;
    hoja.classList.add('pagina--sellada');
    hoja.querySelector('[data-estado]').textContent = 'Sellado';
    const marca = hoja.querySelector('[data-sello]');
    marca.querySelector('[data-sello-fecha]').textContent = fechaDeSello(sello.fecha);
    marca.setAttribute('aria-label', `${nombre}, visitado el ${largo.format(fecha(sello.fecha))}`);
    mostrarSello(marca);
    const indice = document.querySelector(`[data-indice="${sello.slug}"]`);
    indice.classList.add('indice--sellado');
    indice.querySelector('[data-indice-estado]').textContent = ', sellado';
    const acciones = hoja.querySelector('[data-acciones]');
    acciones.replaceChildren();
    if (sello.datos_que_faltan) {
      // Misiones: quien ya estuvo allí es quien mejor puede contar lo que falta.
      const mision = texto('p', 'pagina__mision', `Ya estuviste aquí: faltan ${sello.datos_que_faltan} datos prácticos. `);
      const enlace = texto('a', '', 'Cuenta lo que sabes');
      enlace.href = `/destinos/${sello.slug}/#sugerir-dato`;
      mision.append(enlace);
      acciones.append(mision);
    }
    acciones.append(controlesDeFoto(hoja, sello));
  }

  // ── Foto propia ──────────────────────────────────────────
  const ESTADOS_FOTO = {
    privada: 'Tu foto está en esta página. Solo la ves tú.',
    pendiente: 'Tu foto está en esta página. La revisaremos antes de mostrarla en tu pasaporte compartido.',
    publicado: 'Tu foto está en esta página y se ve en tu pasaporte compartido.',
    oculto: 'Tu foto está en esta página, pero no la aprobamos para el pasaporte compartido: solo la ves tú.',
  };
  function describirFoto(foto) {
    if (!foto) return 'Si subes una foto tuya, sustituye a la del catálogo en esta página.';
    if (!foto.mostrar) return ESTADOS_FOTO.privada;
    return ESTADOS_FOTO[foto.estado] || ESTADOS_FOTO.privada;
  }

  function leerComoDatos(archivo) {
    return new Promise((resolver, rechazar) => {
      const lector = new FileReader();
      lector.onload = () => resolver(lector.result);
      lector.onerror = () => rechazar(new Error('No pudimos mostrar tu foto.'));
      lector.readAsDataURL(archivo);
    });
  }

  async function ponerFoto(hoja, foto) {
    const lamina = hoja.querySelector('.pagina__lamina');
    const catalogo = lamina.querySelector('[data-foto-catalogo]');
    const credito = hoja.querySelector('[data-credito]');
    lamina.querySelector('[data-foto-propia]')?.remove();
    if (!foto) {
      if (catalogo) catalogo.hidden = false;
      if (credito) credito.hidden = false;
      return;
    }
    // La foto es privada: se pide con tu sesión y se muestra sin una dirección pública.
    const datos = await leerComoDatos(await InfoTrip.api(foto.url, {blob: true}));
    const imagen = document.createElement('img');
    imagen.className = 'pagina__foto';
    imagen.dataset.fotoPropia = '';
    imagen.alt = `Tu foto de ${hoja.dataset.nombre}`;
    imagen.width = 960;
    imagen.height = 640;
    imagen.src = datos;
    lamina.prepend(imagen);
    if (catalogo) catalogo.hidden = true;
    if (credito) credito.hidden = true;
  }

  function controlesDeFoto(hoja, sello) {
    const nodo = plantillaFoto.content.firstElementChild.cloneNode(true);
    const formulario = nodo.querySelector('form');
    const archivo = formulario.elements.imagen;
    const mostrar = formulario.elements.mostrar;
    const subir = formulario.querySelector('button[type="submit"]');
    const quitar = formulario.querySelector('[data-quitar]');
    const descripcion = formulario.querySelector('[data-foto-estado]');
    const aviso = formulario.querySelector('.form-status');
    const id = `mi-foto-${sello.slug}`;
    archivo.id = `${id}-archivo`;
    mostrar.id = `${id}-mostrar`;
    let foto = sello.foto;

    function actualizar() {
      descripcion.textContent = describirFoto(foto);
      mostrar.checked = !!foto?.mostrar;
      subir.textContent = foto ? 'Cambiar foto' : 'Subir foto';
      quitar.hidden = !foto;
    }
    actualizar();
    if (foto) ponerFoto(hoja, foto).catch(error => { aviso.textContent = error.message; });

    formulario.addEventListener('submit', event => {
      event.preventDefault();
      if (!archivo.files.length) { aviso.textContent = 'Elige una foto.'; archivo.focus(); return; }
      InfoTrip.submit(formulario, async status => {
        const datos = new FormData();
        datos.append('imagen', archivo.files[0]);
        datos.append('mostrar', mostrar.checked ? 'true' : 'false');
        foto = await InfoTrip.api(`/api/v1/mi-pasaporte/${sello.slug}/foto/`, {method: 'POST', body: datos});
        archivo.value = '';
        await ponerFoto(hoja, foto);
        actualizar();
        status.textContent = 'Listo: tu foto ya está en esta página.';
      });
    });
    mostrar.addEventListener('change', async () => {
      if (!foto) return;
      try {
        foto = await InfoTrip.api(`/api/v1/mi-pasaporte/${sello.slug}/foto/`, {method: 'PATCH', body: {mostrar: mostrar.checked}});
        actualizar();
        aviso.textContent = foto.mostrar ? 'Guardado: la revisaremos para tu pasaporte compartido.' : 'Guardado: solo la ves tú.';
      } catch (error) {
        mostrar.checked = !mostrar.checked;
        aviso.textContent = error.message;
      }
    });
    quitar.addEventListener('click', async () => {
      if (!window.confirm('¿Quitar tu foto de esta página? Se borra y vuelve la del catálogo.')) return;
      try {
        await InfoTrip.api(`/api/v1/mi-pasaporte/${sello.slug}/foto/`, {method: 'DELETE'});
        foto = null;
        await ponerFoto(hoja, null);
        actualizar();
        aviso.textContent = 'Quitamos tu foto.';
        subir.focus();
      } catch (error) { aviso.textContent = error.message; }
    });
    return nodo;
  }

  // ── Distancias: solo si el navegador ya tiene permiso. No se pide la ubicación para esto. ──
  function km(lat1, lon1, lat2, lon2) {
    const rad = grados => grados * Math.PI / 180;
    const a = Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lon2 - lon1) / 2) ** 2;
    return 6371 * 2 * Math.asin(Math.sqrt(a));
  }
  async function distancias() {
    if (!navigator.permissions || !navigator.geolocation) return;
    let permiso;
    try { permiso = await navigator.permissions.query({name: 'geolocation'}); } catch { return; }
    if (permiso.state !== 'granted') return;
    navigator.geolocation.getCurrentPosition(posicion => {
      const {latitude, longitude} = posicion.coords;
      document.querySelectorAll('.pagina:not(.pagina--sellada):not(.pagina--sin-ficha)').forEach(hoja => {
        const distancia = km(latitude, longitude, Number(hoja.dataset.latitud), Number(hoja.dataset.longitud));
        const estadoPagina = hoja.querySelector('[data-estado]');
        estadoPagina.querySelector('.pagina__distancia')?.remove();
        const frase = distancia <= 5 ? '· Estás cerca: abre su ficha' : `· Te faltan ${Math.round(distancia)} km`;
        estadoPagina.append(texto('span', 'pagina__distancia', frase));
      });
      const aviso = document.getElementById('pasaporte-distancias');
      aviso.textContent = 'Distancias en línea recta desde donde estás ahora. Tu ubicación no se envía ni se guarda.';
      aviso.hidden = false;
    }, () => {}, {maximumAge: 10 * 60 * 1000, timeout: 10000});
  }

  // ── Datos de la persona ──────────────────────────────────
  function mostrarProgreso(total, de) {
    progreso.replaceChildren(texto('strong', '', String(total)), ` de ${de} destinos sellados`);
  }
  function mostrarRegiones(regiones) {
    regiones.forEach(region => {
      const fila = document.querySelector(`[data-region="${region.slug}"]`);
      if (!fila) return;
      fila.querySelector('[data-cuenta]').textContent = `${region.sellados} de ${region.total}`;
      fila.querySelector('[data-barra]').style.width = `${Math.round(100 * region.sellados / region.total)}%`;
    });
  }

  async function cargar() {
    try {
      const datos = await InfoTrip.api('/api/v1/mi-pasaporte/');
      document.getElementById('pasaporte-nombre').textContent = datos.nombre;
      mostrarProgreso(datos.total, datos.de);
      mostrarRegiones(datos.regiones);
      datos.sellos.filter(sello => sello.sello).forEach(sellar);
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

  (InfoTrip.hasSession() ? cargar() : Promise.resolve()).then(distancias);
})();
