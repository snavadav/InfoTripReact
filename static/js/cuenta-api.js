(() => {
  let renewing;
  function clear() { ['access_token', 'refresh_token', 'usuario'].forEach(key => localStorage.removeItem(key)); }
  function message(data) {
    if (typeof data === 'string') return data;
    if (Array.isArray(data)) return data.map(message).join('\n');
    return Object.entries(data || {}).map(([key, value]) => `${key === 'detail' || key === 'non_field_errors' ? '' : key + ': '}${message(value)}`).join('\n');
  }
  async function renew() {
    if (!renewing) renewing = (async () => {
      const token = localStorage.getItem('refresh_token');
      if (!token) throw new Error('Inicia sesión para continuar.');
      const response = await fetch('/api/v1/auth/token/refresh/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({refresh:token})});
      if (!response.ok) {clear(); throw new Error('Tu sesión terminó. Inicia sesión nuevamente.');}
      const data = await response.json();
      localStorage.setItem('access_token', data.access);
      if (data.refresh) localStorage.setItem('refresh_token', data.refresh);
    })().finally(() => {renewing = null;});
    return renewing;
  }
  async function api(url, {method='GET', body, auth=true} = {}, retry=true) {
    const headers = {};
    if (auth) {
      if (!localStorage.getItem('access_token')) throw new Error('Inicia sesión y confirma tu correo para continuar.');
      headers.Authorization = 'Bearer ' + localStorage.getItem('access_token');
    }
    if (body && !(body instanceof FormData)) {headers['Content-Type']='application/json'; body=JSON.stringify(body);}
    let response;
    try {response = await fetch(url, {method, headers, body});} catch {throw new Error('No pudimos conectar. Revisa tu conexión.');}
    if (response.status === 401 && auth && retry) {
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
  window.InfoTrip = {api, clear, submit};
})();
