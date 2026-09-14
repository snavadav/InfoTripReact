(() => {
  const form = document.getElementById('profile-form');
  const status = document.getElementById('profile-status');
  const list = document.getElementById('my-contributions');
  const more = document.getElementById('more-contributions');
  let next = '/api/v1/mis-aportes/';
  const labels = {resena:'Reseña',foto:'Fotografía',gasto:'Gasto'};
  function node(tag, text, className) {const el=document.createElement(tag);if(text)el.textContent=text;if(className)el.className=className;return el;}
  function field(form, label, name, type, value) {
    const wrap=node('label',label), input=node(type==='textarea'?'textarea':'input');
    input.name=name; if(type!=='textarea') input.type=type;
    input.value=value ?? ''; input.required=true;
    if(type==='textarea') {input.maxLength=2000;input.rows=3;}
    if(type==='date') input.max=new Date().toLocaleDateString('en-CA');
    wrap.append(input);form.append(wrap); return input;
  }
  function render(item) {
    const article=node('article',null,'community-box');
    const heading=node('h3',`${labels[item.tipo]} · ${item.destino_nombre}`);
    const state=node('p',item.estado_nombre);
    const text=node('p',item.texto);
    article.append(heading,state,text);
    if(item.tipo==='foto' && item.imagen) {const image=node('img');image.src=item.imagen;image.alt=item.texto;image.className='community-photo';article.append(image);}
    if(item.tipo==='resena') article.append(node('p',`${item.calificacion} / 5 · ${item.fecha_visita}`));
    if(item.tipo==='gasto') article.append(node('p',`$${item.monto} MXN · ${item.concepto} · ${item.fecha_visita}`));
    const details=node('details'), summary=node('summary','Editar aporte'), edit=node('form',null,'community-form');
    details.append(summary,edit);
    field(edit,'Descripción','texto','textarea',item.texto);
    field(edit,'Fecha de visita','fecha_visita','date',item.fecha_visita);
    if(item.tipo==='resena') {const rating=field(edit,'Calificación (1–5)','calificacion','number',item.calificacion);rating.min=1;rating.max=5;rating.step=1;}
    if(item.tipo==='gasto') {
      const amount=field(edit,'Monto en MXN','monto','number',item.monto); amount.min=0;amount.max=9999999.99;amount.step='.01';
      const label=node('label','Concepto'), select=node('select'); select.name='concepto';
      Object.entries({entrada:'Entrada por persona',comida:'Comida por persona',alojamiento:'Alojamiento por noche',transporte:'Transporte por persona'}).forEach(([value,text])=>{const option=node('option',text);option.value=value;select.append(option);});
      select.value=item.concepto;label.append(select);edit.append(label);
    }
    if(item.tipo==='foto') {const image=field(edit,'Reemplazar imagen (opcional, hasta 5 MB)','imagen','file'); image.required=false;image.accept='image/jpeg,image/png,image/webp';}
    const save=node('button','Guardar y enviar a revisión');save.type='submit';const feedback=node('p',null,'form-status');feedback.setAttribute('role','status');edit.append(save,feedback);
    edit.addEventListener('submit', event=>{event.preventDefault();InfoTrip.submit(edit,async message=>{
      const body=new FormData(edit);if(item.tipo==='foto'&&!edit.elements.imagen.files.length)body.delete('imagen');
      const updated=await InfoTrip.api(`/api/v1/aportes/${item.id}/`,{method:'PATCH',body});
      const replacement=render(updated);article.replaceWith(replacement);replacement.querySelector('details').open=true;replacement.querySelector('.form-status').textContent='Guardado. El aporte volvió a revisión.';
    });});
    const actions=node('div',null,'contribution-actions');const remove=node('button','Retirar aporte');remove.type='button';
    remove.addEventListener('click',async()=>{
      if(!confirm('¿Retirar este aporte de la página?'))return;
      remove.disabled=true;
      try{await InfoTrip.api(`/api/v1/aportes/${item.id}/`,{method:'DELETE'});article.remove();if(!list.children.length)list.append(node('p','No tienes más aportes en esta página.'));}
      catch(error){feedback.textContent=error.message;details.open=true;remove.disabled=false;}
    });
    actions.append(remove);article.append(details,actions);list.append(article);return article;
  }
  async function load() {
    more.disabled=true;
    try {
      const data=await InfoTrip.api(next);data.results.forEach(render);
      next=data.next;more.hidden=!next;
      if(!list.children.length)list.append(node('p','Todavía no has compartido aportes. Abre un destino para comenzar.'));
    } catch(error){status.textContent=error.message;}finally{more.disabled=false;}
  }
  more.addEventListener('click',load);
  form.addEventListener('submit',event=>{event.preventDefault();InfoTrip.submit(form,async feedback=>{
    const body=new FormData(form);if(!form.elements.foto_perfil.files.length)body.delete('foto_perfil');
    const user=await InfoTrip.api('/api/v1/auth/perfil/',{method:'PATCH',body});localStorage.setItem('usuario',JSON.stringify(user));
    feedback.textContent='Perfil guardado.';if(user.foto_perfil){const image=document.getElementById('profile-photo');image.src=user.foto_perfil;image.hidden=false;}
  });});
  const password=document.getElementById('password-form');
  password.addEventListener('submit',event=>{event.preventDefault();InfoTrip.submit(password,async feedback=>{
    await InfoTrip.api('/api/v1/auth/cambiar-password/',{method:'POST',body:Object.fromEntries(new FormData(password))});
    InfoTrip.clear();password.reset();feedback.textContent='Contraseña actualizada. Vuelve a iniciar sesión.';
    document.getElementById('profile-login').hidden=false;
  });});
  (async()=>{
    try {
      const user=await InfoTrip.api('/api/v1/auth/perfil/');
      for(const name of ['nombre','apellido','ciudad_origen','bio'])form.elements[name].value=user[name]||'';
      document.getElementById('profile-email').textContent=`${user.email} · ${user.es_verificado?'Correo confirmado':'Correo pendiente'}`;
      if(user.foto_perfil){const image=document.getElementById('profile-photo');image.src=user.foto_perfil;image.hidden=false;}
      document.getElementById('profile-content').hidden=false;status.textContent='';await load();
    }catch(error){status.textContent=error.message;document.getElementById('profile-login').hidden=false;}
  })();
})();
