(() => {
  const params = new URLSearchParams(location.search);
  const uid = params.get('uid'), token = params.get('token');
  const recovery = document.getElementById('recovery-form'), reset = document.getElementById('reset-form');
  if (uid && token) {
    recovery.hidden = true; reset.hidden = false;
    history.replaceState(null, '', '/recuperar/');
  }
  recovery.addEventListener('submit', event => {
    event.preventDefault();
    InfoTrip.submit(recovery, async status => {
      const data = await InfoTrip.api('/api/v1/auth/recuperar/', {method:'POST',auth:false,body:{email:recovery.elements.email.value}});
      status.textContent = data.mensaje + (data.modo_prueba ? ' Modo de prueba: el enlace se muestra en la terminal del servidor; no se envía correo real.' : '');
    });
  });
  reset.addEventListener('submit', event => {
    event.preventDefault();
    InfoTrip.submit(reset, async status => {
      const data = await InfoTrip.api('/api/v1/auth/restablecer/', {method:'POST',auth:false,body:{uid,token,password:reset.elements.password.value,password2:reset.elements.password2.value}});
      InfoTrip.clear(); reset.reset(); status.textContent = data.mensaje;
    });
  });
})();
