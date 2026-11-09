// Botones para compartir una ruta guardada: WhatsApp, menú del dispositivo y copiar el enlace.
// Lo usan el planeador (tras guardar) y la página pública de la ruta. Requiere cuenta-api.js.
window.InfoTripCompartirRuta = (() => {
  'use strict';
  // Sin datos personales: solo el título de la ruta (que ya no lleva la ubicación) y el enlace.
  function textoWhatsApp(titulo, url) {
    return `${titulo}, armada con InfoTrip: ${url}`;
  }

  async function copiar(url, campo) {
    try {
      await navigator.clipboard.writeText(url);
      return 'Enlace copiado.';
    } catch {
      if (campo) { campo.focus(); campo.select(); }
      return `Copia este enlace: ${url}`;
    }
  }

  // Se puede llamar otra vez con otra ruta: actualiza el enlace sin duplicar los botones.
  function conectar(caja, titulo, url) {
    const estado = caja.querySelector('[data-compartir-estado]');
    const campo = caja.querySelector('[data-enlace]');
    Object.assign(caja.dataset, {titulo, url});
    if (campo) campo.value = url;
    estado.textContent = '';
    caja.querySelector('[data-whatsapp]').href = `https://wa.me/?text=${encodeURIComponent(textoWhatsApp(titulo, url))}`;
    if (caja.dataset.conectada) return;
    caja.dataset.conectada = 'si';
    const nativo = caja.querySelector('[data-compartir]');
    if (nativo && navigator.share) {
      nativo.hidden = false;
      nativo.addEventListener('click', async () => {
        const aviso = await InfoTrip.share(caja.dataset.titulo, caja.dataset.url);
        if (aviso) estado.textContent = aviso;
      });
    }
    caja.querySelector('[data-copiar]').addEventListener('click', async () => {
      estado.textContent = await copiar(caja.dataset.url, campo);
    });
  }

  return {conectar, textoWhatsApp};
})();
