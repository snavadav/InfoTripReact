// ── Menú móvil ──
const hamburger = document.getElementById('hamburger');
const mobileMenu = document.getElementById('mobileMenu');
function setMobileMenu(open) {
  mobileMenu.classList.toggle('open', open);
  hamburger.setAttribute('aria-expanded', String(open));
  hamburger.setAttribute('aria-label', open ? 'Cerrar menú' : 'Abrir menú');
}
hamburger.addEventListener('click', () => setMobileMenu(!mobileMenu.classList.contains('open')));
mobileMenu.querySelectorAll('a').forEach(link => link.addEventListener('click', () => setMobileMenu(false)));

// ── Menú de cuenta ──
const accountToggle = document.getElementById('account-toggle');
const accountMenu = document.getElementById('account-menu');
function setAccountMenu(open) {
  accountMenu.hidden = !open;
  accountToggle.setAttribute('aria-expanded', String(open));
}
accountToggle.addEventListener('click', () => setAccountMenu(accountMenu.hidden));
document.addEventListener('click', event => {
  if (!accountMenu.hidden && !document.getElementById('nav-user').contains(event.target)) setAccountMenu(false);
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if (!accountMenu.hidden) { setAccountMenu(false); accountToggle.focus(); }
  if (mobileMenu.classList.contains('open')) { setMobileMenu(false); hamburger.focus(); }
});

// ── Página actual y destino del enlace "Saltar al contenido" ──
document.addEventListener('DOMContentLoaded', () => {
  const path = location.pathname;
  document.querySelectorAll('.nav-links a, .mobile-menu > a').forEach(link => {
    const target = link.getAttribute('href');
    if (target !== '/' && path.startsWith(target)) link.setAttribute('aria-current', 'page');
  });
  const main = document.querySelector('main');
  if (main && !main.id) main.id = 'contenido';
  if (main && !main.hasAttribute('tabindex')) main.setAttribute('tabindex', '-1');
  // Algunas páginas ya nombran su <main> (p. ej. #pasaporte): el enlace apunta a ese id y no a uno inexistente.
  const salto = document.querySelector('.skip-link');
  if (main && salto) salto.setAttribute('href', `#${main.id}`);
});

// ── Sesión ──
// Las sesiones anteriores a la cookie HttpOnly guardaban los tokens aquí: se retiran y se vuelve a iniciar sesión.
if (localStorage.getItem('refresh_token')) ['access_token', 'refresh_token', 'usuario'].forEach(key => localStorage.removeItem(key));

let usuario = null;
try {usuario = JSON.parse(localStorage.getItem('usuario') || 'null');} catch {}
if (!usuario || typeof usuario.nombre !== 'string' || typeof usuario.apellido !== 'string') usuario = null;

if (usuario) {
  const inicial = usuario.nombre.charAt(0).toUpperCase();
  const nombreCompleto = usuario.nombre + ' ' + usuario.apellido;

  // Escritorio
  document.getElementById('nav-guest').style.display = 'none';
  document.getElementById('nav-user').style.display = 'block';
  document.getElementById('userAvatar').textContent = inicial;
  document.getElementById('userName').textContent = usuario.nombre;
  accountToggle.setAttribute('aria-label', `Cuenta de ${nombreCompleto}`);

  // Móvil
  document.getElementById('mobileUserInfo').style.display = 'flex';
  document.getElementById('mobileUserAvatar').textContent = inicial;
  document.getElementById('mobileUserName').textContent = nombreCompleto;
  document.getElementById('mobile-guest').hidden = true;
  document.getElementById('mobile-auth').hidden = false;
}

// ── Logout ──
function doLogout(event) {
  event?.preventDefault();
  fetch('/api/v1/auth/logout/', {
    method: 'POST',
    headers: { 'X-CSRFToken': getCookie('csrftoken') },
  }).finally(() => {
    localStorage.removeItem('usuario');
    localStorage.removeItem('infotrip_borrador_viaje');
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

// ── Foco completo en barras que se desplazan de lado ──
// En las barras de botones con desplazamiento horizontal (filtros, lugares del mapa), Chromium solo desplaza
// lo justo y el botón enfocado con Tab puede quedar recortado. Se lleva entero a la vista (WCAG 2.4.11).
document.addEventListener('focusin', event => {
  const barra = event.target.parentElement;
  if (!barra || !/auto|scroll/.test(getComputedStyle(barra).overflowX)) return;
  event.target.scrollIntoView({block: 'nearest', inline: 'nearest'});
});
