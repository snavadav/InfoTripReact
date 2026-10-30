(() => {
  const form = document.getElementById('loginForm');
  const codeForm = document.getElementById('codeForm');
  const notice = document.getElementById('loginNotice');
  const error = document.getElementById('formError');
  const resend = document.getElementById('resendBtn');
  const back = document.getElementById('backBtn');
  const verify = document.getElementById('verifyBtn');
  const submit = document.getElementById('submitBtn');
  let credentials = null;
  let challenge = null;
  let timer;
  let busy = false;
  let resendAt = 0;
  const params = new URLSearchParams(location.search);
  // A dónde volver tras entrar: solo rutas de este sitio.
  const nextPath = (() => {
    const candidate = params.get('next');
    if (!candidate) return '/';
    const url = new URL(candidate, location.origin);
    return url.origin === location.origin && !/^\/(login|registro)\//.test(url.pathname)
      ? url.pathname + url.search + url.hash : '/';
  })();
  const signup = document.querySelector('a[href="/registro/"]');
  if (signup && nextPath !== '/') signup.href = `/registro/?next=${encodeURIComponent(nextPath)}`;
  if (params.has('registro')) {
    notice.textContent = 'Registro recibido. Inicia sesión para verificar tu correo.';
  }
  function showError(message) {
    error.textContent = message;
    error.classList.add('show');
  }
  function clearError() { error.textContent = ''; error.classList.remove('show'); }
  function updateResend() {
    const seconds = Math.max(0, Math.ceil((resendAt - Date.now()) / 1000));
    resend.disabled = busy || seconds > 0;
    resend.textContent = seconds ? `Reenviar en ${seconds} s` : 'Reenviar código';
  }
  function setBusy(value) {
    busy = value;
    submit.disabled = value;
    verify.disabled = value;
    back.disabled = value;
    updateResend();
    document.getElementById('btnText').textContent = value ? 'Enviando código…' : 'Iniciar sesión';
    verify.textContent = value ? 'Verificando…' : 'Verificar e iniciar sesión';
  }
  async function post(url, body) {
    const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 429) {
        resendAt = Date.now() + Number(response.headers.get('Retry-After') || 60) * 1000;
      }
      const first = Object.values(data)[0];
      throw new Error(data.detail || (Array.isArray(first) ? first[0] : 'No se pudo completar la solicitud.'));
    }
    return data;
  }
  // Recién registrada: el código ya se envió, así que se va directo a escribirlo.
  function showPendingCode() {
    let pending = null;
    try { pending = JSON.parse(sessionStorage.getItem('infotrip_desafio')); } catch { /* Se usa el formulario normal. */ }
    sessionStorage.removeItem('infotrip_desafio');
    if (!pending || !params.has('registro')) return;
    challenge = pending.desafio;
    form.hidden = true;
    codeForm.hidden = false;
    resend.hidden = true;
    notice.textContent = pending.modo_prueba
      ? 'Modo de prueba: el correo y su código se muestran en la terminal del servidor. No se envió un correo real.'
      : `Enviamos un código a ${pending.email}. Revisa también la carpeta de spam. Si ya tenías cuenta, te avisamos por correo.`;
    document.getElementById('loginCode').focus();
  }
  async function sendCode() {
    if (busy) return;
    clearError();
    setBusy(true);
    try {
      const data = await post('/api/v1/auth/login/', credentials);
      if (data.access) {
        // Dispositivo recordado: la contraseña basta y no hace falta código.
        localStorage.setItem('usuario', JSON.stringify(data.usuario));
        window.location.assign(nextPath);
        return;
      }
      challenge = data.desafio;
      form.hidden = true;
      codeForm.hidden = false;
      notice.textContent = data.modo_prueba
        ? 'Modo de prueba: el correo y su código se muestran en la terminal del servidor. No se envió un correo real.'
        : `Enviamos un código a ${credentials.email}. Revisa también la carpeta de spam.`;
      resendAt = Date.now() + data.reenviar_en * 1000;
      clearInterval(timer);
      timer = setInterval(updateResend, 1000);
      document.getElementById('loginCode').value = '';
      document.getElementById('loginCode').focus();
    } catch (err) { showError(err.message || 'No pudimos conectar. Intenta de nuevo.'); }
    finally { setBusy(false); }
  }
  form.addEventListener('submit', event => {
    event.preventDefault();
    credentials = {email: document.getElementById('email').value.trim(), password: document.getElementById('password').value};
    sendCode();
  });
  resend.addEventListener('click', sendCode);
  showPendingCode();
  back.addEventListener('click', () => {
    resend.hidden = false;
    clearInterval(timer);
    credentials = null;
    challenge = null;
    document.getElementById('password').value = '';
    codeForm.hidden = true;
    form.hidden = false;
    notice.textContent = '';
    clearError();
    document.getElementById('email').focus();
  });
  codeForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    clearError();
    setBusy(true);
    try {
      const data = await post('/api/v1/auth/verificar-codigo/', {desafio: challenge, codigo: document.getElementById('loginCode').value.trim(), recordar: document.getElementById('rememberDevice').checked});
      // El refresh token llega como cookie HttpOnly; el access token se pide de nuevo en cada página.
      localStorage.setItem('usuario', JSON.stringify(data.usuario));
      credentials = null;
      document.getElementById('password').value = '';
      window.location.assign(nextPath);
    } catch (err) { showError(err.message || 'No pudimos conectar. Intenta de nuevo.'); }
    finally { setBusy(false); }
  });
})();
