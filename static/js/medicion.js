(() => {
  // Eventos anónimos: sin cookies ni identificadores. Se respeta «No rastrear» y «Global Privacy Control».
  if (navigator.doNotTrack === '1' || navigator.globalPrivacyControl) return;
  function send(nombre, destino = '') {
    const body = new Blob([JSON.stringify({nombre, destino})], {type: 'application/json'});
    if (navigator.sendBeacon) navigator.sendBeacon('/api/v1/eventos/', body);
    else fetch('/api/v1/eventos/', {method: 'POST', body, keepalive: true}).catch(() => {});
  }
  window.InfoTripMedicion = {send};

  const ficha = document.getElementById('practical-info');
  const destino = ficha ? ficha.dataset.slug : '';
  if (ficha) {
    send('ficha_vista', destino);
    const datos = ficha.querySelector('.practical-grid .contribution-text');
    if (datos && 'IntersectionObserver' in window) {
      const observer = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting)) {
          observer.disconnect();
          send('dato_practico_visto', destino);
        }
      });
      observer.observe(datos);
    }
  }

  const costos = document.querySelector('[data-costos]');
  if (costos) send('costos_vista', costos.dataset.costos);
  if (document.querySelector('[data-misiones]')) send('misiones_vista');

  // Los enlaces compartidos y los de los correos de aviso llevan ?ref=…
  const ref = new URLSearchParams(location.search).get('ref');
  if (ref === 'compartido') send('visita_por_enlace', destino);
  if (ref === 'aviso') send('clic_en_aviso', destino);

  const registro = document.getElementById('registroForm');
  if (registro) registro.addEventListener('focusin', () => send('registro_iniciado'), {once: true});
})();
