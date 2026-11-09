// Perfil: las rutas del planeador que la persona compartió con su cuenta, con la opción de borrarlas.
(() => {
  'use strict';
  const lista = document.getElementById('my-shared-routes');
  const estado = document.getElementById('shared-routes-status');
  if (!lista || !InfoTrip.hasSession()) return;

  function nodo(etiqueta, texto, clase) {
    const elemento = document.createElement(etiqueta);
    if (texto) elemento.textContent = texto;
    if (clase) elemento.className = clase;
    return elemento;
  }
  function fecha(iso) {
    const [anio, mes, dia] = iso.split('-').map(Number);
    return new Date(anio, mes - 1, dia).toLocaleDateString('es-MX', {day: 'numeric', month: 'long', year: 'numeric'});
  }
  function vacio() {
    lista.replaceChildren(nodo('p', 'Aún no has compartido rutas. Arma una en el planeador y pulsa «Compartir ruta».'));
  }

  function fila(ruta) {
    const articulo = nodo('article', '', 'community-box');
    const titulo = nodo('h3');
    const enlace = nodo('a', ruta.titulo);
    enlace.href = ruta.url;
    titulo.append(enlace);
    const borrar = nodo('button', 'Borrar');
    borrar.type = 'button';
    borrar.setAttribute('aria-label', `Borrar ${ruta.titulo}`);
    borrar.addEventListener('click', async () => {
      if (!confirm('¿Borrar esta ruta? Su enlace dejará de funcionar para quien lo tenga.')) return;
      borrar.disabled = true;
      try {
        await InfoTrip.api(`/api/v1/rutas/compartidas/${ruta.enlace}/`, {method: 'DELETE'});
        articulo.remove();
        estado.textContent = 'Ruta borrada.';
        if (!lista.children.length) vacio();
      } catch (error) {
        estado.textContent = error.message;
        borrar.disabled = false;
      }
    });
    articulo.append(titulo, nodo('p', `Sale el ${fecha(ruta.fecha)} · ${ruta.sitios} sitio${ruta.sitios === 1 ? '' : 's'}`), borrar);
    return articulo;
  }

  InfoTrip.api('/api/v1/rutas/compartidas/').then(({rutas}) => {
    if (!rutas.length) vacio();
    else lista.replaceChildren(...rutas.map(fila));
  }).catch(error => { estado.textContent = error.message; });
})();
