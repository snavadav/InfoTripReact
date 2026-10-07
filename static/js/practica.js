(() => {
  const root = document.getElementById('practical-info');
  if (!root) return;
  const slug = encodeURIComponent(root.dataset.slug), toggle = document.getElementById('favorite-toggle'), status = document.getElementById('favorite-status');
  let favorite = false;
  function display(){toggle.textContent=favorite?'Quitar de favoritos':'Guardar lugar';toggle.setAttribute('aria-pressed',String(favorite));}
  async function initial(){
    try{if(localStorage.getItem('access_token')){favorite=(await InfoTrip.api(`/api/v1/favoritos/${slug}/`)).favorito;display();}}
    catch(error){status.textContent=error.message;}
    finally{toggle.disabled=false;}
  }
  toggle.addEventListener('click',async()=>{
    if(!window.InfoTripSession?.authenticated){
      status.replaceChildren(document.createTextNode('Entra para guardar este lugar. '));
      const link=document.createElement('a');link.href='/login/';link.textContent='Iniciar sesión';status.append(link);link.focus();return;
    }
    toggle.disabled=true;
    try{await InfoTrip.api(`/api/v1/favoritos/${slug}/`,{method:favorite?'DELETE':'PUT'});favorite=!favorite;display();status.textContent=favorite?'Guardado en tus favoritos.':'Quitado de tus favoritos.';}
    catch(error){status.textContent=error.message;}
    finally{toggle.disabled=false;}
  });
  document.querySelectorAll('.collaboration-form').forEach(form=>form.addEventListener('submit',event=>{
    event.preventDefault();InfoTrip.submit(form,async feedback=>{
      const body=Object.fromEntries(new FormData(form));body.tipo=form.dataset.type;
      if(form.dataset.question)body.pregunta=Number(form.dataset.question);
      await InfoTrip.api(`/api/v1/destinos/${slug}/colaboraciones/`,{method:'POST',body});
      form.reset();feedback.textContent='Gracias. Tu aporte quedó pendiente de revisión; aparecerá cuando sea publicado.';
    });
  }));
  initial();
})();
