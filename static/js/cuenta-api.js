(() => {
  // El access token solo vive en memoria: un script ajeno no puede leerlo de localStorage y se pierde
  // al cambiar de página. La sesión real es una cookie HttpOnly; `usuario` solo sirve para la interfaz.
  let access = null;
  let renewing;
  function clear() { access = null; localStorage.removeItem('usuario'); }
  function hasSession() { return !!localStorage.getItem('usuario'); }
  function csrfToken() {
    const cookie = document.cookie.split('; ').find(item => item.startsWith('csrftoken='));
    return cookie ? decodeURIComponent(cookie.slice('csrftoken='.length)) : '';
  }
  // Nombres legibles para los campos que devuelve la API; un campo sin nombre conocido muestra solo el mensaje.
  const fieldNames = {
    nombre: 'Nombre', apellido: 'Apellido', email: 'Correo', password: 'Contraseña', password2: 'Confirmación',
    password_actual: 'Contraseña actual', password_nuevo: 'Contraseña nueva', password_nuevo2: 'Confirmación',
    ciudad_origen: 'Ciudad de origen', bio: 'Sobre mí', foto_perfil: 'Foto de perfil', texto: 'Descripción',
    fecha_visita: 'Fecha de visita', calificacion: 'Calificación', imagen: 'Fotografía', monto: 'Monto',
    concepto: 'Concepto', tipo: 'Tipo', motivo: 'Motivo', campo: 'Dato', fuente: 'Fuente',
    fecha_dato: 'Fecha de consulta', pregunta: 'Pregunta', destino: 'Destino', fecha_inicio: 'Salida',
    fecha_fin: 'Regreso', personas: 'Viajeros', presupuesto: 'Presupuesto', gastos: 'Gastos',
    actividades: 'Actividades', pendientes: 'Pendientes', notas: 'Notas', lugares: 'Lugares',
  };
  function message(data) {
    if (typeof data === 'string') return data;
    if (Array.isArray(data)) return data.map(message).join('\n');
    return Object.entries(data || {}).map(([key, value]) => `${fieldNames[key] ? fieldNames[key] + ': ' : ''}${message(value)}`).join('\n');
  }
  async function requestAccess() {
    let response;
    try {response = await fetch('/api/v1/auth/token/refresh/', {method:'POST', headers:{'X-CSRFToken':csrfToken()}});}
    catch {throw new Error('No pudimos conectar. Revisa tu conexión.');}
    if (response.status === 401 || response.status === 403) {clear(); throw new Error('Tu sesión terminó. Inicia sesión nuevamente.');}
    if (!response.ok) throw new Error('No pudimos continuar tu sesión. Intenta de nuevo.');
    access = (await response.json()).access;
  }
  async function renew() {
    // El cerrojo evita que dos pestañas renueven a la vez el día que cambia el refresh token.
    if (!renewing) renewing = (navigator.locks ? navigator.locks.request('infotrip-sesion', requestAccess) : requestAccess())
      .finally(() => {renewing = null;});
    return renewing;
  }
  async function api(url, {method='GET', body, auth=true} = {}, retry=true) {
    const headers = {};
    if (auth) {
      if (!hasSession()) throw new Error('Inicia sesión y confirma tu correo para continuar.');
      if (!access) await renew();
      headers.Authorization = 'Bearer ' + access;
    }
    if (body && !(body instanceof FormData)) {headers['Content-Type']='application/json'; body=JSON.stringify(body);}
    let response;
    try {response = await fetch(url, {method, headers, body});} catch {throw new Error('No pudimos conectar. Revisa tu conexión.');}
    if (response.status === 401 && auth && retry) {
      access = null;
      await renew();
      return api(url, {method, body:headers['Content-Type'] ? JSON.parse(body || 'null') : body, auth}, false);
    }
    const data = response.status === 204 ? null : await response.json().catch(() => ({detail:'No pudimos completar la solicitud.'}));
    if (!response.ok) throw new Error(message(data));
    return data;
  }
  async function submit(form, operation) {
    const button = form.querySelector('button[type="submit"],button:not([type])');
    if (button?.disabled) return;
    if (button) button.disabled=true;
    const status = form.querySelector('.form-status'); status.textContent='Procesando…';
    try {await operation(status);} catch(error) {status.textContent=error.message;} finally {if(button) button.disabled=false;}
  }
  function loginUrl() { return `/login/?next=${encodeURIComponent(location.pathname + location.search + location.hash)}`; }
  // Comparte con el menú del dispositivo o copia el enlace. Devuelve qué decirle a la persona ('' si canceló).
  async function share(title, url, destino = '') {
    try {
      if (navigator.share) await navigator.share({title, url});
      else await navigator.clipboard.writeText(url);
    } catch (error) {
      if (error.name === 'AbortError') return '';
      return `Copia este enlace: ${url}`;
    }
    window.InfoTripMedicion?.send('enlace_compartido', destino);
    return navigator.share ? 'Enlace compartido.' : 'Enlace copiado.';
  }
  window.InfoTrip = {api, clear, hasSession, loginUrl, share, submit};
})();
