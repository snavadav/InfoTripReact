(() => {
  'use strict';
  const form = document.getElementById('trip-form');
  const expenses = document.getElementById('trip-expenses');
  const activities = document.getElementById('trip-activities');
  const tasks = document.getElementById('trip-tasks');
  let places = [];
  const list = document.getElementById('saved-trips');
  const status = document.getElementById('trip-status');
  const more = document.getElementById('more-trips');
  let current = null, dirty = false, next = null, saving = false;
  const money = cents => new Intl.NumberFormat('es-MX', {style:'currency', currency:'MXN'}).format(cents / 100);
  const cents = value => Math.round(Number(value || 0) * 100);
  function node(tag, text) { const el = document.createElement(tag); if(text) el.textContent = text; return el; }
  function button(text, action) { const el = node('button', text); el.type = 'button'; el.addEventListener('click', action); return el; }
  function field(row, title, name, value, choices) {
    const label = node('label', title), input = node(choices ? 'select' : 'input');
    input.name = name;
    if(choices) Object.entries(choices).forEach(([key,text]) => { const option = node('option',text); option.value = key; input.append(option); });
    else if(['monto','cantidad'].includes(name)) {input.type='number'; input.min=name==='monto'?'0':'1'; input.max=name==='monto'?'9999999.99':'365'; input.step=name==='monto'?'.01':'1';}
    else input.maxLength=120;
    input.value=value; input.required=true; label.append(input); row.append(label);
  }
  function addExpense(data={concepto:'transporte', descripcion:'', monto:'0.00', cantidad:1, reparto:'compartido'}) {
    if(expenses.children.length>=100) return;
    const row=node('fieldset'); row.className='trip-expense'; row.append(node('legend','Gasto estimado por ti'));
    field(row,'Concepto','concepto',data.concepto,{transporte:'Transporte',comida:'Comida',entradas:'Entradas',alojamiento:'Alojamiento',otros:'Otros'});
    field(row,'Descripción','descripcion',data.descripcion);
    field(row,'Importe unitario (MXN)','monto',data.monto);
    field(row,'Cantidad','cantidad',data.cantidad);
    field(row,'Cómo se reparte','reparto',data.reparto,{individual:'Por persona',compartido:'Compartido entre todos'});
    row.append(button('Quitar gasto',()=>{row.remove();dirty=true;calculate();document.getElementById('add-expense').focus();}));
    expenses.append(row); calculate();
  }
  function addActivity(data={dia:1,hora:'',titulo:'',notas:''}) {
    if(activities.children.length>=150)return;
    const row=node('fieldset');row.className='trip-expense';row.append(node('legend','Actividad'));
    [['Día del viaje','dia','number',data.dia],['Horario (opcional)','hora','time',data.hora],['Actividad','titulo','text',data.titulo],['Notas (opcional)','notas_actividad','text',data.notas]].forEach(([title,name,type,value])=>{
      const label=node('label',title),input=node('input');input.name=name;input.type=type;input.value=value;input.required=['dia','titulo'].includes(name);
      if(name==='dia'){input.min=1;input.max=366;input.step=1;}else input.maxLength=name==='titulo'?150:500;
      label.append(input);row.append(label);
    });
    row.append(button('Quitar actividad',()=>{row.remove();dirty=true;document.getElementById('add-activity').disabled=false;}));activities.append(row);
    document.getElementById('add-activity').disabled=activities.children.length>=150;
  }
  function addTask(data={texto:'',hecho:false}) {
    if(tasks.children.length>=100)return;
    const row=node('div');row.className='trip-task';
    const label=node('label','Completado'),check=node('input');check.type='checkbox';check.checked=data.hecho;check.name='hecho';label.prepend(check);
    const description=node('label','Pendiente'),input=node('input');input.name='texto';input.value=data.texto;input.maxLength=200;input.required=true;description.append(input);
    row.append(label,description,button('Quitar pendiente',()=>{row.remove();dirty=true;document.getElementById('add-task').disabled=false;}));tasks.append(row);
    document.getElementById('add-task').disabled=tasks.children.length>=100;
  }
  function agendaPayload(){return {
    actividades:[...activities.children].map(row=>({dia:Number(row.querySelector('[name="dia"]').value),hora:row.querySelector('[name="hora"]').value,titulo:row.querySelector('[name="titulo"]').value,notas:row.querySelector('[name="notas_actividad"]').value})),
    pendientes:[...tasks.children].map(row=>({texto:row.querySelector('[name="texto"]').value,hecho:row.querySelector('[name="hecho"]').checked})),
    notas:form.elements.notas.value,lugares:places.map(p=>p.id)
  };}
  function showPlaces(){
    const target=document.getElementById('trip-places');target.replaceChildren();
    if(!places.length)target.append(node('p','Aún no has vinculado lugares del catálogo.'));
    places.forEach(place=>{const row=node('div');row.className='trip-actions';const title=node(place.activo?'a':'span',place.nombre+(place.activo?'':' (no disponible)'));if(place.activo)title.href=`/destinos/${encodeURIComponent(place.slug)}/`;row.append(title,button('Quitar del plan',()=>{places=places.filter(p=>p.id!==place.id);dirty=true;showPlaces();}));target.append(row);});
  }
  function readExpenses() { return [...expenses.children].map(row=>Object.fromEntries(['concepto','descripcion','monto','cantidad','reparto'].map(key=>[key,key==='cantidad'?Number(row.querySelector(`[name="${key}"]`).value):row.querySelector(`[name="${key}"]`).value]))); }
  function calculate() {
    const people=Number(form.elements.personas.value);
    const total=readExpenses().reduce((sum,g)=>sum+cents(g.monto)*g.cantidad*(g.reparto==='individual'?people:1),0);
    const remaining=cents(form.elements.presupuesto.value)-total;
    const target=document.getElementById('trip-totals'); target.replaceChildren();
    if(!Number.isInteger(people)||people<1||people>100||!Number.isFinite(total)){target.textContent='Completa los viajeros y los importes para calcular.';return;}
    [ `Total estimado del grupo: ${money(total)}`, `Por persona (reparto igual): ${money(Math.round(total/people))}`, remaining>=0?`Presupuesto restante: ${money(remaining)}`:`Excede el presupuesto por: ${money(-remaining)}` ].forEach(text=>target.append(node('p',text)));
    document.getElementById('add-expense').disabled=expenses.children.length>=100;
  }
  function mayLeave(){if(saving){status.textContent='Espera a que termine el guardado.';return false;}return !dirty||confirm('Tienes cambios sin guardar. ¿Quieres descartarlos?');}
  function edit(item=null, duplicate=false) {
    if(!mayLeave())return;
    form.reset();expenses.replaceChildren();activities.replaceChildren();tasks.replaceChildren();places=[];document.getElementById('add-activity').disabled=false;document.getElementById('add-task').disabled=false;current=duplicate?null:item?.id||null;
    form.elements.fecha_fin.min='';
    if(item){['nombre','destino','fecha_inicio','fecha_fin','personas','presupuesto'].forEach(key=>form.elements[key].value=item[key]); if(duplicate)form.elements.nombre.value=('Copia de '+item.nombre).slice(0,120);item.gastos.forEach(addExpense);(item.actividades||[]).forEach(addActivity);(item.pendientes||[]).forEach(addTask);form.elements.notas.value=item.notas||'';places=item.lugares_detalle||[];}
    showPlaces();
    document.getElementById('editor-title').textContent=current?'Editar escapada':'Nueva escapada';
    form.querySelector('.form-status').textContent=''; dirty=duplicate;calculate();form.elements.nombre.focus();
  }
  function render(item) {
    const card=node('article');card.className='trip-card';card.append(node('h3',item.nombre),node('p',item.destino),node('p',`${item.fecha_inicio} → ${item.fecha_fin} · ${item.personas} viajeros`),node('p',`Estimado: ${money(cents(item.resumen.total))}`));
    const actions=node('div');actions.className='trip-actions';
    actions.append(button('Editar',()=>edit(item)),button('Duplicar',()=>edit(item,true)));
    const remove=button('Eliminar',async()=>{
      if(saving)return;
      if(!confirm(`¿Eliminar la escapada «${item.nombre}»?`))return;
      if(current===item.id&&!mayLeave())return;
      remove.disabled=true;
      try{await InfoTrip.api(`/api/v1/mis-viajes/${item.id}/`,{method:'DELETE'});if(current===item.id){dirty=false;edit();}await load();status.textContent='Escapada eliminada.';}catch(error){status.textContent=error.message;}finally{remove.disabled=false;}
    });actions.append(remove);card.append(actions);list.append(card);
  }
  async function load(append=false) {
    more.disabled=true;
    try{const data=await InfoTrip.api(append?next:'/api/v1/mis-viajes/');if(!append)list.replaceChildren();data.results.forEach(render);next=data.next;more.hidden=!next;if(!list.children.length)list.append(node('p','Todavía no tienes escapadas guardadas. Crea tu primer plan.'));status.textContent='';}
    catch(error){status.textContent=error.message;document.getElementById('trip-login').hidden=!!localStorage.getItem('access_token');}
    finally{more.disabled=false;}
  }
  document.getElementById('add-activity').addEventListener('click',()=>{addActivity();dirty=true;activities.lastElementChild?.querySelector('[name="titulo"]').focus();});
  document.getElementById('add-task').addEventListener('click',()=>{addTask();dirty=true;tasks.lastElementChild?.querySelector('[name="texto"]').focus();});
  form.addEventListener('input',()=>{dirty=true;form.elements.fecha_fin.min=form.elements.fecha_inicio.value;calculate();});
  document.getElementById('add-expense').addEventListener('click',()=>{addExpense();dirty=true;expenses.lastElementChild?.querySelector('input').focus();});
  document.getElementById('new-trip').addEventListener('click',()=>edit());
  more.addEventListener('click',()=>load(true));
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  form.addEventListener('submit',event=>{
    event.preventDefault();
    const body=Object.fromEntries(['nombre','destino','fecha_inicio','fecha_fin','personas','presupuesto'].map(key=>[key,form.elements[key].value]));body.personas=Number(body.personas);body.gastos=readExpenses();Object.assign(body,agendaPayload());
    const snapshot=JSON.stringify(body);
    if(saving)return;
    saving=true;
    InfoTrip.submit(form,async feedback=>{
      const saved=await InfoTrip.api(current?`/api/v1/mis-viajes/${current}/`:'/api/v1/mis-viajes/',{method:current?'PATCH':'POST',body});
      current=saved.id;
      const now=Object.fromEntries(['nombre','destino','fecha_inicio','fecha_fin','personas','presupuesto'].map(key=>[key,form.elements[key].value]));now.personas=Number(now.personas);now.gastos=readExpenses();Object.assign(now,agendaPayload());
      dirty=JSON.stringify(now)!==snapshot;
      document.getElementById('editor-title').textContent='Editar escapada';feedback.textContent=dirty?'Guardado. Tienes cambios posteriores pendientes de guardar.':'Escapada guardada en tu cuenta.';await load();
    }).finally(()=>{saving=false;});
  });
  showPlaces();
  const suggested=new URLSearchParams(location.search).get('destino');
  if(suggested){form.elements.destino.value=suggested.slice(0,200);form.elements.nombre.value=('Escapada a '+suggested).slice(0,120);dirty=true;}
  calculate();
  if(localStorage.getItem('access_token'))load();
  else {document.getElementById('trip-login').hidden=false;list.append(node('p','Inicia sesión para ver tus escapadas. Puedes probar el presupuesto antes de entrar.'));}
})();
