// A branded presentation of an existing select. Its value and change events stay native.
let nextPicker=0;
export function identityPicker(select,{label,describe,esc,icon}){
 const root=document.createElement('div'),id=`r-identity-${++nextPicker}`;
 root.className='ri-picker';
 root.innerHTML=`<button type="button" class="ri-trigger" aria-haspopup="listbox" aria-expanded="false" aria-controls="${id}"></button><div id="${id}" class="ri-options" role="listbox" aria-label="${esc(label)}" hidden></div>`;
 select.after(root);select.hidden=true;
 const trigger=root.querySelector('.ri-trigger'),list=root.querySelector('.ri-options'),events=new AbortController();
 let expanded=false,typeahead='',typedAt=0,previousTrigger='',previousOptions='';
 const details=option=>({name:option.textContent,...describe(option.value)});
 const content=option=>{const d=details(option);return `<span class="ri-mark" aria-hidden="true">${d.mark||icon('nav-agents')}</span><span class="ri-copy"><b>${esc(d.name)}</b>${d.subtitle?`<small>${esc(d.subtitle)}</small>`:''}</span>`;};
 const options=()=>[...list.querySelectorAll('[role=option]:not(:disabled)')];
 function close(focus=false){expanded=false;list.hidden=true;trigger.setAttribute('aria-expanded','false');if(focus)trigger.focus({preventScroll:true});}
 function refresh(){
  const selected=select.selectedOptions[0];
  const triggerContent=(selected?content(selected):`<span class="ri-copy">${esc(label)}</span>`)+icon('down');
  if(triggerContent!==previousTrigger){trigger.innerHTML=triggerContent;previousTrigger=triggerContent;}
  trigger.setAttribute('aria-label',label+': '+(selected?details(selected).name:'Choose'));
  trigger.disabled=select.disabled||!select.options.length;
  const optionsContent=[...select.options].map((o,i)=>`<button type="button" role="option" tabindex="-1" data-index="${i}" ${o.disabled?'disabled':''}>${content(o)}<span class="ri-check" aria-hidden="true">${icon('check')}</span></button>`).join('');
  if(optionsContent!==previousOptions){list.innerHTML=optionsContent;previousOptions=optionsContent;}
  [...list.children].forEach((row,i)=>row.setAttribute('aria-selected',String(select.options[i].selected)));
  if(trigger.disabled)close();
 }
 function open(last=false){
  if(trigger.disabled)return;
  refresh();expanded=true;list.hidden=false;trigger.setAttribute('aria-expanded','true');
  (list.querySelector('[aria-selected=true]:not(:disabled)')||(last?options().at(-1):options()[0]))?.focus({preventScroll:true});
 }
 trigger.onclick=()=>expanded?close():open();
 trigger.onkeydown=e=>{if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();e.stopPropagation();open(e.key==='ArrowUp');}};
 list.onclick=e=>{
  const option=e.target.closest('[data-index]');if(!option||option.disabled||select.disabled)return;
  const value=select.options[Number(option.dataset.index)]?.value;if(value==null)return;
  const changed=value!==select.value;select.value=value;refresh();close(true);
  if(changed){select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}));}
 };
 root.onkeydown=e=>{
  if(!expanded)return;
  if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close(true);return;}
  if(e.key==='Tab'){close(true);return;}
  const rows=options(),current=rows.indexOf(document.activeElement);let target;
  if(e.key==='ArrowDown')target=rows[(current+1)%rows.length];
  if(e.key==='ArrowUp')target=rows[(current-1+rows.length)%rows.length];
  if(e.key==='Home')target=rows[0];if(e.key==='End')target=rows.at(-1);
  if(e.key.length===1&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&e.key!==' '){
   typeahead=(Date.now()-typedAt<700?typeahead:'')+e.key.toLowerCase();typedAt=Date.now();
   target=rows.find(row=>details(select.options[Number(row.dataset.index)]).name.toLowerCase().startsWith(typeahead));
  }
  if(target){e.preventDefault();target.focus({preventScroll:true});target.scrollIntoView({block:'nearest'});}
 };
 document.addEventListener('pointerdown',e=>{if(expanded&&!root.contains(e.target))close();},{capture:true,signal:events.signal});
 select.addEventListener('change',refresh,{signal:events.signal});
 const observer=new MutationObserver(refresh);observer.observe(select,{attributes:true,attributeFilter:['disabled']});
 refresh();
 // The parent owns removal; keep the styled row visible during its closing animation.
 return {refresh,destroy(){events.abort();observer.disconnect();}};
}
