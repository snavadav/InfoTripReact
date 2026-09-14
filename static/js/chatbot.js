(() => {
  'use strict';
  const root = document.getElementById('trip-chat');
  if (!root) return;
  const panel = document.getElementById('trip-chat-panel');
  const toggle = document.getElementById('trip-chat-toggle');
  const close = document.getElementById('trip-chat-close');
  const log = document.getElementById('trip-chat-log');
  const options = document.getElementById('trip-chat-options');
  const links = document.getElementById('trip-chat-links').dataset;
  const menu = [
    ['Crear y guardar una escapada', 'trips'],
    ['Planear una salida', 'plan'], ['Preparar mi presupuesto', 'budget'],
    ['Explorar destinos', 'explore'], ['Compartir mi experiencia', 'contribute'],
    ['¿Qué tan confiables son los datos?', 'trust'], ['Ayuda con mi cuenta', 'account']
  ];
  // Respuestas editoriales: no representan precios, disponibilidad ni visitas verificadas.
  const flows = {
    trips: { text: 'En Mis viajes puedes crear una escapada, introducir tus propios gastos y calcular el total del grupo y el reparto por persona. Inicia sesión para guardar el plan. Los importes son estimaciones tuyas, no cotizaciones.', links: [['Crear mi escapada →', 'trips']], choices: [['Preparar presupuesto', 'budget']] },
    home: { text: '¡Hola! Soy el asistente de InfoTrip. Te ayudo a preparar una escapada por Jalisco y a usar la app. Por ahora respondo mediante estas opciones. ¿Por dónde empezamos?', choices: menu },
    plan: { text: 'Empecemos por el tiempo que tienes. Esta guía es general: confirma horarios y condiciones con cada lugar antes de salir. ¿Qué tipo de salida estás preparando?', choices: [['Un día', 'day'], ['Un fin de semana', 'weekend'], ['Todavía no sé', 'explore']] },
    day: { text: 'Para una salida de un día:\n• Elige una actividad principal.\n• Considera el traslado de ida y vuelta.\n• Aparta tiempo y presupuesto para comer.\n• Confirma el horario de regreso de tu transporte.\n\nPuedes explorar el catálogo para elegir tu destino.', choices: [['Ver qué llevar', 'packing'], ['Preparar presupuesto', 'budget']], links: [['Explorar catálogo →', 'catalog']] },
    weekend: { text: 'Para un fin de semana, organiza primero transporte y alojamiento. Después elige una actividad principal por día y deja tiempo libre. Confirma horarios, precio total del hospedaje y condiciones de cancelación directamente con el prestador.', choices: [['Preparar presupuesto', 'budget'], ['Ver qué llevar', 'packing']], links: [['Explorar catálogo →', 'catalog']] },
    packing: { text: 'Lista básica para preparar tu salida:\n• Agua y protección solar.\n• Calzado adecuado para la actividad.\n• Teléfono cargado y batería de respaldo, si tienes.\n• Identificación y contactos importantes.\n• Confirmaciones de transporte o alojamiento.\n\nRevisa el pronóstico y consulta si el lugar requiere equipo especial o acepta tarjeta.', choices: [['Preparar presupuesto', 'budget'], ['Explorar destinos', 'explore']] },
    budget: { links: [['Crear mi escapada →', 'trips']], text: 'Separa tu presupuesto en transporte de ida y vuelta, entradas, comida y alojamiento si te quedas a dormir. Añade un margen para imprevistos.\n\nTodavía no tengo datos suficientes para cotizar tu viaje. Sí puedo explicarte cómo calcularlo.', choices: [['Viajo solo', 'solo'], ['Vamos varias personas', 'group'], ['Consultar gastos reportados', 'prices']] },
    solo: { text: 'Suma tu transporte de ida y vuelta + entradas + comidas + alojamiento + un margen para imprevistos. Revisa si cada tarifa es por persona, por noche o por servicio. Los gastos reportados son orientativos, no una cotización.', choices: [['Consultar gastos reportados', 'prices'], ['Planear una salida', 'plan']] },
    group: { text: 'Primero suma los gastos individuales de cada viajero. Después añade una sola vez los gastos compartidos, como una habitación o el combustible, y acuerden cómo repartirlos.\n\nNo multipliquen una habitación por el número de personas si la tarifa ya cubre al grupo. Confirmen capacidad y cargos adicionales.', choices: [['Consultar gastos reportados', 'prices'], ['Planear una salida', 'plan']] },
    prices: { text: 'En Explorar destinos puedes filtrar por concepto y precio máximo. En el detalle encontrarás gastos publicados cuando existan aportes.\n\nRevisa la fecha de visita y si el importe es por persona o por noche. Si no hay datos, no significa que sea gratis. Confirma el precio vigente con el lugar.', links: [['Consultar destinos y gastos →', 'catalog']], choices: [['Cómo se revisan los aportes', 'trust']] },
    explore: { text: 'En el catálogo puedes buscar un destino o municipio y usar los filtros disponibles. Abre una ficha para consultar su ubicación, servicios y aportes publicados.\n\nNuestra información todavía está creciendo: no puedo confirmar horarios, disponibilidad ni recomendar lugares según datos que aún no tenemos.', links: [['Explorar destinos →', 'catalog']], choices: [['Planear una salida', 'plan'], ['Preparar presupuesto', 'budget']] },
    contribute: { text: 'Para compartir tu experiencia:\n1. Crea una cuenta e inicia sesión.\n2. Abre la ficha de un destino.\n3. En «Compartir mi experiencia», elige reseña, fotografía o gasto.\n4. Incluye la fecha de tu visita y envía tu aporte.\n\nLos aportes pasan por moderación antes de publicarse. Puedes gestionarlos desde Mi perfil.', links: [['Explorar destinos →', 'catalog'], ['Crear cuenta →', 'register'], ['Mi perfil →', 'profile']], choices: [['Cómo se revisan los aportes', 'trust']] },
    trust: { text: 'Los aportes se revisan antes de publicarse, pero la moderación y el correo confirmado no prueban que alguien haya visitado un lugar. Los gastos son reportes de viajeros y pueden cambiar.\n\nConsulta fechas y varias experiencias. Puedes reportar un aporte desde el destino si detectas un problema.', choices: [['Compartir mi experiencia', 'contribute'], ['Consultar gastos reportados', 'prices']] },
    account: { text: 'Desde Mi perfil puedes editar tus datos y gestionar tus aportes después de iniciar sesión. Si olvidaste tu contraseña, usa la opción de recuperación en la pantalla de acceso.\n\nNunca compartas contraseñas ni códigos de acceso en una conversación.', links: [['Ir a Mi perfil →', 'profile'], ['Crear cuenta →', 'register']], choices: [['Compartir mi experiencia', 'contribute']] }
  };
  function message(text, user = false) {
    const bubble = document.createElement('p');
    bubble.className = 'trip-chat-message' + (user ? ' trip-chat-message-user' : '');
    bubble.textContent = text;
    log.appendChild(bubble);
    while (log.children.length > 40) log.firstElementChild.remove();
    log.scrollTop = log.scrollHeight;
  }
  function show(id, focus = false) {
    const flow = flows[id] || flows.home;
    message(flow.text);
    options.replaceChildren();
    (flow.choices || []).forEach(([label, next]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.addEventListener('click', () => { message(label, true); show(next, true); });
      options.appendChild(button);
    });
    (flow.links || []).forEach(([label, key]) => {
      const link = document.createElement('a');
      link.textContent = label;
      link.href = links[key];
      options.appendChild(link);
    });
    if (focus) options.firstElementChild?.focus({ preventScroll: true });
  }
  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    if (open) {
      if (!log.children.length) show('home');
      close.focus({ preventScroll: true });
      log.scrollTop = log.scrollHeight;
    } else toggle.focus({ preventScroll: true });
  }
  toggle.addEventListener('click', () => setOpen(panel.hidden));
  close.addEventListener('click', () => setOpen(false));
  root.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) { event.preventDefault(); setOpen(false); }
  });
  document.getElementById('trip-chat-reset').addEventListener('click', () => {
    log.replaceChildren();
    show('home', true);
  });
  root.hidden = false;
})();
