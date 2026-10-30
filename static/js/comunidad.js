(() => {
  const form = document.getElementById('contribution-form');
  if (form) {
    if (InfoTrip.hasSession()) document.getElementById('aporte-access-note').textContent='Tu aporte quedará pendiente de revisión. Puedes gestionarlo desde Mi perfil.';
    const tipo = form.elements.tipo;
    function sync() {
      form.querySelectorAll('[data-type]').forEach(label => {
        label.hidden = label.dataset.type !== tipo.value;
        const field = label.querySelector('input,select'); field.disabled = label.hidden; field.required = !label.hidden;
      });
    }
    tipo.addEventListener('change', sync); sync();
    form.addEventListener('submit', event => {
      event.preventDefault();
      InfoTrip.submit(form, async status => {
        await InfoTrip.api(`/api/v1/destinos/${form.dataset.destination}/aportes/`, {method:'POST',body:new FormData(form)});
        form.reset(); sync(); status.textContent='Aporte recibido. Quedó pendiente de moderación. Puedes verlo en Mi perfil.';
      });
    });
  }
  document.querySelectorAll('.report-form').forEach(form => form.addEventListener('submit', event => {
    event.preventDefault();
    InfoTrip.submit(form, async status => {
      await InfoTrip.api(form.dataset.url || `/api/v1/aportes/${form.dataset.id}/reportar/`, {method:'POST', body:{motivo:form.elements.motivo.value}});
      form.reset(); status.textContent='Reporte recibido. El equipo lo revisará.';
    });
  }));
})();
