// Axo, el asistente de InfoTrip. Sin IA generativa: entiende frases con reglas de palabras clave y solo
// muestra datos que existen en el catálogo (API propia). Si no sabe algo, lo dice en lugar de inventarlo.
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const root = $('trip-chat');
  if (!root) return;
  const panel = $('trip-chat-panel');
  const toggle = $('trip-chat-toggle');
  const close = $('trip-chat-close');
  const log = $('trip-chat-log');
  const options = $('trip-chat-options');
  const form = $('trip-chat-form');
  const input = $('trip-chat-input');
  const avatar = $('trip-chat-avatar');
  const links = $('trip-chat-links').dataset;
  // Mismo umbral que apps/comunidad/selectors.py (MINIMO_REPORTES).
  const MINIMO_REPORTES = 3;
  const MAXIMO_RESULTADOS = 5;

  const menu = [
    ['Planear mi escapada', 'plan'], ['Buscar un destino', 'search'], ['¿Qué hay cerca de mí?', 'nearby'],
    ['¿Cuánto cuesta?', 'costs'], ['Mis escapadas', 'trips'], ['¿De dónde salen los datos?', 'sources'],
    ['Ayuda con mi cuenta', 'account']
  ];
  // Respuestas editoriales: no representan precios, disponibilidad ni visitas verificadas.
  const flows = {
    home: { text: '¡Hola! Soy Axo, el ajolote viajero de InfoTrip. Te ayudo a planear una escapada por Jalisco con datos reales.\n\nEscríbeme un destino (por ejemplo «Tapalpa») o una pregunta, o elige una opción.', choices: menu },
    menu: { text: 'Esto es lo que sé hacer. ¿Qué te sirve?', choices: menu },
    search: { text: 'Escribe el nombre de un destino o municipio de Jalisco y lo busco en el catálogo.', focusInput: true, choices: [['¿Qué hay cerca de mí?', 'nearby'], ['Ver todo el catálogo', 'menu']], links: [['Explorar el catálogo →', 'catalog']] },
    plan: { text: 'El planeador arma el recorrido de un día con lugares reales del catálogo: eliges punto de partida, qué te gusta, tu horario y tu presupuesto, y te propone un orden de visita.\n\nConfirma horarios con cada lugar antes de salir.', links: [['Abrir el planeador →', 'planner']], choices: [['Qué llevar', 'packing'], ['¿Cuánto cuesta?', 'costs'], ['Guardar mi escapada', 'trips']] },
    costs: { text: `En Costos ves lo que pagaron otros viajeros por entrada, comida, hospedaje y transporte.\n\nSolo damos una cifra cuando un concepto tiene al menos ${MINIMO_REPORTES} reportes reales del último año: con menos, un solo dato raro podría engañarte. Si no hay cifra, no significa que sea gratis. Es una referencia, no una cotización.\n\nTip: escribe «costos de» y un destino, por ejemplo «costos de Tapalpa».`, links: [['Ver costos por destino →', 'costs']], choices: [['¿De dónde salen los datos?', 'sources'], ['Dividir gastos con amigos', 'trips']] },
    trips: { text: 'En Mis escapadas creas un plan con fechas, lugares y gastos, calculas el reparto por persona y lo compartes. Con el Bote del grupo cada quien anota lo que pagó.\n\nNecesitas iniciar sesión para guardarlas. Los importes son tus estimaciones, no cotizaciones.', links: [['Ir a Mis escapadas →', 'trips']], choices: [['Planear mi escapada', 'plan'], ['Ayuda con mi cuenta', 'account']] },
    nearby: { text: 'Puedo buscar lugares a tu alrededor (restaurantes, hospedaje, farmacias, cajeros…). Necesito tu permiso de ubicación una sola vez; no la guardamos.', choices: [['Buscar con mi ubicación', 'locate'], ['Mejor el mapa', 'menu']], links: [['Ver en el mapa →', 'nearby']] },
    sources: { text: 'Así obtengo lo que te muestro:\n• Negocios como restaurantes, hospedajes y tiendas: Directorio Estadístico Nacional de Unidades Económicas (INEGI, DENUE).\n• El mapa y muchos lugares: OpenStreetMap, hecho por voluntarios.\n• Horarios y costos de museos y zonas arqueológicas: Sistema de Información Cultural de la Secretaría de Cultura.\n• Reseñas, fotos y gastos: aportes de viajeros, revisados antes de publicarse.\n\nCada ficha cita su fuente. Si un dato no está, no lo invento. La información puede cambiar: confirma con el lugar antes de ir.', links: [['Créditos y fuentes →', 'credits']], choices: [['¿Cuánto cuesta?', 'costs'], ['Compartir mi experiencia', 'contribute']] },
    contribute: { text: 'Para compartir tu experiencia:\n1. Inicia sesión.\n2. Abre la ficha de un destino o lugar.\n3. Publica una reseña, una foto o un gasto, con la fecha de tu visita.\n\nLos aportes pasan por moderación antes de publicarse. La revisión no prueba que alguien haya visitado el lugar.', links: [['Explorar destinos →', 'catalog'], ['Crear cuenta →', 'register']], choices: [['¿De dónde salen los datos?', 'sources']] },
    account: { text: 'Te ayudo con tu cuenta:\n• ¿Olvidaste tu contraseña? Usa «Recuperar contraseña» y te llegará un código al correo.\n• En Mi perfil editas tus datos y gestionas tus aportes.\n\nNunca compartas contraseñas ni códigos en una conversación. Yo nunca te los voy a pedir.', links: [['Iniciar sesión →', 'login'], ['Crear cuenta →', 'register'], ['Recuperar contraseña →', 'recover'], ['Mi perfil →', 'profile']], choices: [['Mis escapadas', 'trips']] },
    packing: { text: 'Lista básica para tu salida:\n• Agua y protección solar.\n• Calzado adecuado para la actividad.\n• Teléfono cargado y batería de respaldo.\n• Identificación, efectivo y contactos importantes.\n• Confirmaciones de transporte o alojamiento.\n\nRevisa el pronóstico y si el lugar acepta tarjeta.', choices: [['¿Cuánto cuesta?', 'costs'], ['Planear mi escapada', 'plan']] },
    ai: { text: 'No soy una inteligencia artificial: soy un asistente con respuestas escritas por el equipo de InfoTrip. Reconozco palabras clave y busco en el catálogo real, así que no invento lugares, precios ni horarios.', choices: [['¿De dónde salen los datos?', 'sources'], ['Ver opciones', 'menu']] },
    thanks: { text: '¡Con gusto! Que tengas una gran escapada. Si necesitas algo más, aquí ando.', choices: [['Ver opciones', 'menu']] },
    bye: { text: '¡Buen viaje! Cuando quieras me encuentras en la esquina de la pantalla.', choices: [['Ver opciones', 'menu']] }
  };
  // Reglas en orden: gana la primera que coincide con el texto ya normalizado (minúsculas y sin acentos).
  const intents = [
    ['ai', /\b(eres (una |un )?(ia|robot|bot|humano|persona|maquina)|inteligencia artificial|chatgpt|gpt)\b/],
    ['account', /\b(cuenta|contrasena|password|clave|sesion|login|registr\w*|correo|perfil|codigo|verific\w*)\b/],
    ['costs', /\b(costos?|precios?|cuanto (cuesta|sale|cobran|gasto)|presupuesto|gastos?|caro|barato|dinero|pesos)\b/],
    ['sources', /\b(fuentes?|datos?|confiab\w*|confiar|inegi|denue|openstreetmap|osm|sic|cultura|de donde|inventa\w*)\b/],
    ['nearby', /\b(cerca|cercan\w*|alrededor|aqui|mi ubicacion|donde estoy)\b/],
    ['trips', /\b(mis escapadas|mis viajes|guardar|guardad\w*|bote|dividir|repartir|amigos)\b/],
    ['plan', /\b(planea\w*|planear|plan|itinerario|ruta|que (hago|hacer)|organiz\w*|recorrido|un dia|fin de semana)\b/],
    ['contribute', /\b(resenas?|opinion|aport\w*|compartir|fotos?|calific\w*|comentar)\b/],
    ['packing', /\b(llevar|empacar|maleta)\b/],
    ['thanks', /\b(gracias|grax|muy amable)\b/],
    ['bye', /\b(adios|bye|hasta luego|nos vemos)\b/],
    ['menu', /\b(ayuda|ayudame|que (puedes|sabes)|opciones|menu|inicio)\b/],
    ['home', /^(hola|holi|buenas|buenos dias|buenas tardes|buenas noches|que tal|hey)\b/]
  ];
  // «busca Tapalpa», «quiero ir a Mazamitla», «costos de Ajijic»: lo que sigue es el destino.
  const destinoEnFrase = /(?:busca(?:r|me)?|quiero (?:ir|conocer|visitar)(?: a)?|ir a|conoces|informaci[oó]n de|info de|qu[eé] hay en|c[oó]mo es|d[oó]nde queda|costos? (?:de|en|para)|cu[aá]nto cuesta(?: ir a)?|precios? (?:de|en))\s+(.{3,60})$/;

  const normalizar = texto => texto.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
  const limpiar = texto => texto.replace(/[¿?¡!.,;:"«»]/g, ' ').replace(/\s+/g, ' ').trim();

  function elemento(tag, clase, texto) {
    const nodo = document.createElement(tag);
    if (clase) nodo.className = clase;
    if (texto !== undefined) nodo.textContent = texto;
    return nodo;
  }
  function message(text, user = false) {
    const bubble = elemento('div', 'trip-chat-message' + (user ? ' trip-chat-message-user' : ''));
    if (user) bubble.append(elemento('span', 'sr-only', 'Tú: '));
    bubble.append(elemento('p', '', text));
    log.appendChild(bubble);
    while (log.children.length > 40) log.firstElementChild.remove();
    mostrar(bubble);
    return bubble;
  }
  // Una respuesta larga se muestra desde su inicio, no desde el final.
  function mostrar(bubble) {
    if (bubble.offsetHeight <= log.clientHeight - 16) { log.scrollTop = log.scrollHeight; return; }
    log.scrollTop += bubble.getBoundingClientRect().top - log.getBoundingClientRect().top - 8;
  }
  // Lista de enlaces a fichas reales dentro de un mensaje del asistente.
  function resultados(bubble, filas) {
    const lista = elemento('ul', 'trip-chat-results');
    filas.forEach(({ href, titulo, detalle }) => {
      const item = elemento('li');
      const enlace = elemento('a', '', titulo);
      enlace.href = href;
      item.append(enlace);
      if (detalle) item.append(elemento('span', 'trip-chat-result-detail', detalle));
      lista.append(item);
    });
    bubble.append(lista);
    mostrar(bubble);
  }
  function setChoices(choices = [], linkList = [], focus = false) {
    options.replaceChildren();
    choices.forEach(([label, next]) => {
      const button = elemento('button', '', label);
      button.type = 'button';
      button.addEventListener('click', () => { message(label, true); show(next, true); });
      options.appendChild(button);
    });
    linkList.filter(([, key]) => key !== 'profile' || window.InfoTripSession?.authenticated).forEach(([label, key]) => {
      const link = elemento('a', '', label);
      link.href = links[key] || key;
      options.appendChild(link);
    });
    if (focus) options.firstElementChild?.focus({ preventScroll: true });
  }
  function show(id, focus = false) {
    if (id === 'locate') { input.focus({ preventScroll: true }); buscarCerca(); return; }
    const flow = flows[id] || flows.menu;
    message(flow.text);
    setChoices(flow.choices, flow.links, focus && !flow.focusInput);
    if (flow.focusInput) input.focus({ preventScroll: true });
  }
  function pensando(activo) {
    avatar.classList.toggle('is-pensando', activo);
    log.setAttribute('aria-busy', String(activo));
  }

  async function buscarDestinos(texto, { costos = false } = {}) {
    pensando(true);
    try {
      const respuesta = await fetch('/api/v1/destinos/?' + new URLSearchParams({ q: texto }), { headers: { Accept: 'application/json' } });
      if (!respuesta.ok) throw new Error(String(respuesta.status));
      const datos = await respuesta.json();
      const lista = datos.results || [];
      const total = datos.count ?? lista.length;
      if (!lista.length) {
        message(`No encontré «${texto}» en el catálogo. No invento lugares: puede que todavía no lo tengamos.\n\nPrueba con el nombre del municipio o explora el mapa.`);
        setChoices([['Buscar otro destino', 'search'], ['¿Qué hay cerca de mí?', 'nearby']], [['Explorar el catálogo →', 'catalog']]);
        return;
      }
      const intro = costos
        ? `Esto encontré para «${texto}». En cada enlace ves los costos reportados (cifra con ${MINIMO_REPORTES} reportes o más):`
        : `Encontré ${total === 1 ? '1 destino' : `${total} destinos`} para «${texto}»:`;
      const bubble = message(intro);
      resultados(bubble, lista.slice(0, MAXIMO_RESULTADOS).map(destino => ({
        href: `${links.catalog}${encodeURIComponent(destino.slug)}/${costos ? 'costos/' : ''}`,
        titulo: destino.nombre,
        detalle: [destino.municipio?.nombre, destino.atribucion ? 'Fuente: OpenStreetMap' : ''].filter(Boolean).join(' · ')
      })));
      const extra = [];
      if (total > MAXIMO_RESULTADOS) extra.push([`Ver los ${total} resultados →`, `${links.catalog}?${new URLSearchParams({ q: texto })}`]);
      setChoices([['Buscar otro destino', 'search'], ['Planear mi escapada', 'plan']], extra);
    } catch {
      message('No pude consultar el catálogo en este momento. Intenta de nuevo en un rato.');
      setChoices([['Ver opciones', 'menu']], [['Explorar el catálogo →', 'catalog']]);
    } finally {
      pensando(false);
    }
  }

  function distancia(km) {
    if (km === null || km === undefined) return '';
    return km < 1 ? `a ${Math.round(km * 1000)} m` : `a ${km.toLocaleString('es-MX', { maximumFractionDigits: 1 })} km`;
  }
  async function pedirCercanos(latitud, longitud, radio) {
    const respuesta = await fetch('/api/v1/lugares/cerca/', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ latitud, longitud, radio_km: radio })
    });
    if (!respuesta.ok) throw new Error(String(respuesta.status));
    return respuesta.json();
  }
  function buscarCerca() {
    if (!navigator.geolocation) {
      message('Tu navegador no ofrece ubicación. Puedes buscar un destino por nombre o abrir el mapa.');
      setChoices([['Buscar un destino', 'search']], [['Ver el mapa →', 'catalog']]);
      return;
    }
    pensando(true);
    setChoices();
    message('Buscando lo más cercano a ti…');
    navigator.geolocation.getCurrentPosition(async ({ coords }) => {
      try {
        // En un pueblo puede no haber nada a 5 km: se amplía antes de responder que no hay.
        let datos = await pedirCercanos(coords.latitude, coords.longitude, 5);
        if (!datos.resultados.length) datos = await pedirCercanos(coords.latitude, coords.longitude, 25);
        if (!datos.resultados.length) {
          message(`No tengo lugares registrados a menos de ${datos.radio_km} km de ti. Prefiero decírtelo a inventar.`);
        } else {
          const bubble = message(`Lo más cercano que tengo registrado (a menos de ${datos.radio_km} km):`);
          resultados(bubble, datos.resultados.slice(0, MAXIMO_RESULTADOS).map(lugar => ({
            href: lugar.url,
            titulo: lugar.nombre,
            detalle: [lugar.subtipo_nombre || lugar.tipo_nombre, distancia(lugar.distancia_km),
              lugar.atribucion ? `Fuente: ${lugar.atribucion}` : ''].filter(Boolean).join(' · ')
          })));
        }
        setChoices([['Planear mi escapada', 'plan'], ['Buscar un destino', 'search']], [['Ver todo en el mapa →', 'nearby']]);
      } catch {
        message('No pude buscar lugares cercanos ahora. Intenta de nuevo en un rato.');
        setChoices([['Ver opciones', 'menu']], [['Ver el mapa →', 'nearby']]);
      } finally {
        pensando(false);
      }
    }, () => {
      pensando(false);
      message('No tengo permiso para usar tu ubicación, y está bien. Puedes escribirme el nombre de un destino o municipio.');
      setChoices([['Buscar un destino', 'search']], [['Ver el mapa →', 'catalog']]);
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
  }

  // Texto libre: primero las reglas; si nada coincide, se interpreta como el nombre de un destino.
  function responder(texto) {
    const original = limpiar(texto);
    const normal = normalizar(texto);
    if (!normal) return;
    // Se busca en minúsculas pero se conserva cómo lo escribió la persona.
    const frase = original.toLowerCase().match(destinoEnFrase);
    const lugar = frase && original.slice(original.length - frase[1].length).trim();
    const intent = intents.find(([, regla]) => regla.test(normal));
    if (intent?.[0] === 'costs' && lugar) { buscarDestinos(lugar, { costos: true }); return; }
    if (lugar && (!intent || intent[0] === 'plan')) { buscarDestinos(lugar); return; }
    if (intent) { show(intent[0]); return; }
    if (normal.split(' ').length > 6) {
      message('No entendí del todo. Respondo mejor a frases cortas: el nombre de un destino o palabras como «costos», «cerca de mí» o «planear».');
      setChoices(menu);
      return;
    }
    buscarDestinos(original);
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    const texto = input.value.trim().slice(0, 120);
    if (!texto) { input.focus(); return; }
    message(texto, true);
    input.value = '';
    responder(texto);
    input.focus({ preventScroll: true });
  });

  // Axo saluda con la mano; la clase se quita para poder repetir la animación.
  function saludar(figura) {
    figura.classList.remove('is-saludando');
    void figura.offsetWidth;
    figura.classList.add('is-saludando');
    setTimeout(() => figura.classList.remove('is-saludando'), 2000);
  }

  // Burbuja de bienvenida: una vez al día, se cierra sola y nunca roba el foco.
  const saludo = $('trip-chat-saludo');
  const CLAVE_SALUDO = 'infotrip_axo_saludo';
  let temporizador = null;
  function hoy() { return new Date().toLocaleDateString('en-CA'); }
  function yaSaludo() {
    try { return localStorage.getItem(CLAVE_SALUDO) === hoy(); } catch { return true; }
  }
  function ocultarSaludo() {
    clearTimeout(temporizador);
    saludo.hidden = true;
  }
  function mostrarSaludo() {
    if (!panel.hidden || yaSaludo()) return;
    // Sin almacenamiento no se puede limitar a una vez al día: mejor no insistir en cada página.
    try { localStorage.setItem(CLAVE_SALUDO, hoy()); } catch { return; }
    saludo.hidden = false;
    toggle.classList.add('is-asomando');
    saludar(toggle);
    temporizador = setTimeout(ocultarSaludo, 9000);
  }
  // Mientras el puntero o el foco están en la burbuja, no se cierra sola.
  saludo.addEventListener('pointerenter', () => clearTimeout(temporizador));
  saludo.addEventListener('focusin', () => clearTimeout(temporizador));
  saludo.addEventListener('pointerleave', () => { temporizador = setTimeout(ocultarSaludo, 4000); });
  $('trip-chat-saludo-abrir').addEventListener('click', () => setOpen(true));
  $('trip-chat-saludo-cerrar').addEventListener('click', () => {
    ocultarSaludo();
    toggle.focus({ preventScroll: true });
  });

  function setOpen(open) {
    ocultarSaludo();
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    if (open) {
      saludar(avatar);
      if (!log.children.length) show('home');
      (matchMedia('(pointer: fine)').matches ? input : close).focus({ preventScroll: true });
      log.scrollTop = log.scrollHeight;
    } else toggle.focus({ preventScroll: true });
  }
  toggle.addEventListener('click', () => setOpen(panel.hidden));
  close.addEventListener('click', () => setOpen(false));
  root.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !panel.hidden) { event.preventDefault(); setOpen(false); }
  });
  // La burbuja no toma el foco, así que Escape se escucha en toda la página mientras está visible.
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !saludo.hidden) ocultarSaludo();
  });
  $('trip-chat-reset').addEventListener('click', () => {
    log.replaceChildren();
    show('home', true);
  });
  root.hidden = false;
  setTimeout(mostrarSaludo, 1500);
})();
