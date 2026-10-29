// ── Scroll shadow ──
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
  navbar.classList.toggle('scrolled', window.scrollY > 10);
});

// ── Hamburger ──
const hamburger = document.getElementById('hamburger');
const mobileMenu = document.getElementById('mobileMenu');
hamburger.addEventListener('click', () => {
  hamburger.classList.toggle('open');
  mobileMenu.classList.toggle('open');
});
mobileMenu.querySelectorAll('a').forEach(link => {
  link.addEventListener('click', () => {
    hamburger.classList.remove('open');
    mobileMenu.classList.remove('open');
  });
});

// ── Sesión ──
let usuario = null;
try {usuario = JSON.parse(localStorage.getItem('usuario') || 'null');} catch {}
if (!usuario || typeof usuario.nombre !== 'string' || typeof usuario.apellido !== 'string' || !localStorage.getItem('access_token')) usuario = null;

if (usuario) {
  const inicial = usuario.nombre.charAt(0).toUpperCase();
  const nombreCompleto = usuario.nombre + ' ' + usuario.apellido;

  // Desktop
  document.getElementById('nav-guest').style.display = 'none';
  const navUser = document.getElementById('nav-user');
  navUser.style.display = 'flex';
  document.getElementById('userAvatar').textContent = inicial;
  document.getElementById('userName').textContent   = nombreCompleto;

  // Móvil
  const mobileUserInfo = document.getElementById('mobileUserInfo');
  mobileUserInfo.style.display = 'flex';
  document.getElementById('mobileUserAvatar').textContent = inicial;
  document.getElementById('mobileUserName').textContent   = nombreCompleto;
  document.getElementById('mobile-guest').style.display   = 'none';
  document.getElementById('mobile-auth').style.display    = 'block';
}

const profileLink = document.createElement('a');
profileLink.href = '/perfil/'; profileLink.textContent = 'Mi perfil';
document.getElementById('nav-user').prepend(profileLink);

// ── Logout ──
function doLogout() {
  const refresh = localStorage.getItem('refresh_token');
  fetch('/api/v1/auth/logout/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + localStorage.getItem('access_token'), 'X-CSRFToken': getCookie('csrftoken') },
    body: JSON.stringify({ refresh })
  }).finally(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('usuario');
    window.location.href = '/';
  });
}

document.getElementById('logoutBtn')?.addEventListener('click', doLogout);
document.getElementById('mobileLogoutBtn')?.addEventListener('click', doLogout);

// ── CSRF ──
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
}
