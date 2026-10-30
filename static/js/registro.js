// Indicador de fortaleza de contraseña
const pwdInput     = document.getElementById('password');
const strengthWrap = document.getElementById('strengthWrap');
const strengthFill = document.getElementById('strengthFill');
const strengthText = document.getElementById('strengthText');

pwdInput.addEventListener('input', () => {
  const val = pwdInput.value;
  if (!val) { strengthWrap.classList.remove('show'); return; }
  strengthWrap.classList.add('show');

  let score = 0;
  if (val.length >= 8)  score++;
  if (/[A-Z]/.test(val)) score++;
  if (/[0-9]/.test(val)) score++;
  if (/[^A-Za-z0-9]/.test(val)) score++;

  const levels = [
    { w: '25%', color: '#D94141', text: 'Muy débil' },
    { w: '50%', color: '#F76707', text: 'Débil' },
    { w: '75%', color: '#F59E0B', text: 'Buena' },
    { w: '100%', color: '#2D9B47', text: 'Muy fuerte' },
  ];
  const lvl = levels[score - 1] || levels[0];
  strengthFill.style.width = lvl.w;
  strengthFill.style.background = lvl.color;
  strengthText.textContent = lvl.text;
  strengthText.style.color = lvl.color;
});

// Submit
const form      = document.getElementById('registroForm');
const submitBtn = document.getElementById('submitBtn');
const spinner   = document.getElementById('spinner');
const btnIcon   = document.getElementById('btnIcon');
const btnText   = document.getElementById('btnText');
const formError = document.getElementById('formError');

function showError(msg) { formError.textContent = msg; formError.classList.add('show'); }
function hideError() { formError.classList.remove('show'); }
function clearFieldErrors() {
  document.querySelectorAll('.field-error').forEach(el => { el.textContent = ''; el.classList.remove('show'); });
  document.querySelectorAll('.form-input').forEach(el => el.classList.remove('error'));
}
function showFieldError(field, msg) {
  const el = document.getElementById(field + 'Error');
  const input = document.getElementById(field);
  if (el) { el.textContent = msg; el.classList.add('show'); }
  if (input) input.classList.add('error');
}
function setLoading(loading) {
  submitBtn.disabled = loading;
  spinner.style.display = loading ? 'block' : 'none';
  btnIcon.style.display = loading ? 'none' : 'block';
  btnText.textContent = loading ? 'Creando cuenta...' : 'Crear cuenta gratis';
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  hideError();
  clearFieldErrors();

  const pwd  = document.getElementById('password').value;
  const pwd2 = document.getElementById('password2').value;
  if (pwd !== pwd2) { showFieldError('password2', 'Las contraseñas no coinciden.'); return; }

  setLoading(true);

  const body = {
    nombre:        document.getElementById('nombre').value,
    apellido:      document.getElementById('apellido').value,
    email:         document.getElementById('email').value,
    ciudad_origen: document.getElementById('ciudad_origen').value,
    password:      pwd,
    password2:     pwd2,
  };

  try {
    const res  = await fetch('/api/v1/auth/registro/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
      body: JSON.stringify(body)
    });
    const data = await res.json();

    if (res.ok) {
      const next = new URLSearchParams(location.search).get('next');
      window.location.href = `/login/?registro=1${next ? `&next=${encodeURIComponent(next)}` : ''}`;
    } else {
      // Errores por campo
      Object.entries(data).forEach(([key, val]) => {
        const msg = Array.isArray(val) ? val[0] : val;
        showFieldError(key, msg);
      });
      if (data.non_field_errors) showError(data.non_field_errors[0]);
    }
  } catch {
    showError('Error de conexión. Intenta de nuevo.');
  } finally {
    setLoading(false);
  }
});

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
}
