(() => {
  // Presentation only. Each private API still authenticates and checks ownership.
  let authenticated = false;
  try {
    const user = JSON.parse(localStorage.getItem('usuario') || 'null');
    authenticated = !!(user && typeof user.nombre === 'string' && typeof user.apellido === 'string');
  } catch { /* Missing or damaged session data keeps the public navigation. */ }
  window.InfoTripSession = {authenticated};
  document.querySelectorAll('[data-session-only]').forEach(el => {el.hidden = !authenticated;});
  document.querySelectorAll('[data-trip-label]').forEach(el => {el.textContent = authenticated ? 'Mis viajes' : 'Planear escapada';});
  if (document.getElementById('trip-form')) document.title = `${authenticated ? 'Mis viajes' : 'Planear escapada'} — InfoTrip`;
})();
