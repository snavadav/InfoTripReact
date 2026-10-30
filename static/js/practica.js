(() => {
  const root = document.getElementById('practical-info');
  if (!root) return;
  const slug = encodeURIComponent(root.dataset.slug), toggle = document.getElementById('favorite-toggle'), status = document.getElementById('favorite-status');
  let favorite = false;
  function display(){toggle.textContent=favorite?'Quitar de favoritos':'Guardar lugar';toggle.setAttribute('aria-pressed',String(favorite));}
  async function initial(){
    try{if(InfoTrip.hasSession()){favorite=(await InfoTrip.api(`/api/v1/favoritos/${slug}/`)).favorito;display();}}
    catch(error){status.textContent=error.message;}
    finally{toggle.disabled=false;}
  }
  toggle.addEventListener('click',async()=>{
    if(!window.InfoTripSession?.authenticated){
      status.replaceChildren(document.createTextNode('Entra para guardar este lugar. '));
      const link=document.createElement('a');link.href=InfoTrip.loginUrl();link.textContent='Iniciar sesión';status.append(link);link.focus();return;
    }
    toggle.disabled=true;
    try{await InfoTrip.api(`/api/v1/favoritos/${slug}/`,{method:favorite?'DELETE':'PUT'});favorite=!favorite;display();status.textContent=favorite?'Guardado en tus favoritos.':'Quitado de tus favoritos.';}
    catch(error){status.textContent=error.message;}
    finally{toggle.disabled=false;}
  });
  document.getElementById('share-place').addEventListener('click',async()=>{
    const feedback=await InfoTrip.share(document.title,`${location.origin}${location.pathname}?ref=compartido`,root.dataset.slug);
    if(feedback)status.textContent=feedback;
  });
  document.querySelectorAll('.collaboration-form').forEach(form=>form.addEventListener('submit',event=>{
    event.preventDefault();InfoTrip.submit(form,async feedback=>{
      const body=Object.fromEntries(new FormData(form));body.tipo=form.dataset.type;
      if(form.dataset.question)body.pregunta=Number(form.dataset.question);
      await InfoTrip.api(`/api/v1/destinos/${slug}/colaboraciones/`,{method:'POST',body});
      form.reset();feedback.textContent='Gracias. Tu aporte quedó pendiente de revisión; aparecerá cuando sea publicado.';
    });
  }));
  // "¿Sigue vigente?": confirmar renueva la fecha de vigencia del dato sin pasar por moderación.
  document.querySelectorAll('.confirm-data').forEach(button=>button.addEventListener('click',async()=>{
    const feedback=button.parentElement.nextElementSibling;
    if(!window.InfoTripSession?.authenticated){
      feedback.replaceChildren(document.createTextNode('Entra para confirmar este dato. '));
      const link=document.createElement('a');link.href=InfoTrip.loginUrl();link.textContent='Iniciar sesión';feedback.append(link);return;
    }
    button.disabled=true;
    try{
      const data=await InfoTrip.api(`/api/v1/colaboraciones/${button.dataset.dato}/confirmar/`,{method:'POST'});
      feedback.textContent=`Gracias. Confirmaste que sigue vigente (${data.confirmaciones} confirmación${data.confirmaciones===1?'':'es'}).`;
    }catch(error){feedback.textContent=error.message;button.disabled=false;}
  }));
  initial();
})();
