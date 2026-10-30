(() => {
  // Presentation only. Each private API still authenticates and checks ownership.
  let authenticated = false;
  try {
    const user = JSON.parse(localStorage.getItem('usuario') || 'null');
    authenticated = !!(user && typeof user.nombre === 'string' && typeof user.apellido === 'string');
  } catch { /* Missing or damaged session data keeps the public navigation. */ }
  window.InfoTripSession = {authenticated};
  // Tras entrar o registrarse, la persona vuelve a la página en la que estaba.
  const here = location.pathname + location.search + location.hash;
  document.querySelectorAll('a[href="/login/"], a[href="/registro/"]').forEach(link => {
    link.href = `${link.getAttribute('href')}?next=${encodeURIComponent(here)}`;
  });
  document.querySelectorAll('[data-session-only]').forEach(el => {el.hidden = !authenticated;});
  document.querySelectorAll('[data-trip-label]').forEach(el => {el.textContent = authenticated ? 'Mis viajes' : 'Planear escapada';});
  if (document.getElementById('trip-form')) document.title = `${authenticated ? 'Mis viajes' : 'Planear escapada'} — InfoTrip`;
})();
