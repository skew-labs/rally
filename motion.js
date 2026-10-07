// Bounded, interruptible UI motion. No network, account or wallet authority.
export function motionUI(){
 const ease='cubic-bezier(.22,.8,.24,1)',reduced=matchMedia('(prefers-reduced-motion:reduce)');
 const previous=new Map();let source,route=0,pageMotion;
 const allowed=()=>!document.hidden&&!reduced.matches;
 document.addEventListener('pointerdown',event=>{
  const target=event.target.closest('button,a');if(!target||event.button>0)return;
  const box=target.getBoundingClientRect();source={x:box.x+box.width/2,y:box.y+box.height/2,at:performance.now()};
 },{passive:true,capture:true});
 function glider(host,target,key,mobile=false){
  if(!host||!target||!host.getClientRects().length)return;
  let shape=host.querySelector(':scope>.r-motion-glider');
  if(!shape){shape=document.createElement('span');shape.className='r-motion-glider';shape.setAttribute('aria-hidden','true');host.append(shape);}
  const rect=target.getBoundingClientRect(),parent=host.getBoundingClientRect();
  const current={x:mobile?rect.x+rect.width/2-23:rect.x,y:mobile?parent.y+5:rect.y,width:mobile?46:rect.width,height:mobile?36:rect.height};
  const old=previous.get(key);previous.set(key,current);
  const moved=old&&(Math.abs(old.x-current.x)>1||Math.abs(old.y-current.y)>1||Math.abs(old.width-current.width)>1);
  if(moved)shape.getAnimations().forEach(a=>a.cancel());
  Object.assign(shape.style,{left:(current.x-parent.x+host.scrollLeft)+'px',top:(current.y-parent.y+host.scrollTop)+'px',width:current.width+'px',height:current.height+'px'});
  if(moved&&allowed())shape.animate([
   {transform:`translate(${old.x-current.x}px,${old.y-current.y}px) scaleX(${old.width/current.width})`},{transform:'translate(0,0) scaleX(1)'}
  ],{duration:240,easing:ease});
 }
 function navigation(){
  const mobile=document.querySelector('.r-mobile-nav'),desktop=document.querySelector('.r-sidebar nav[aria-label="Main navigation"]');
  glider(mobile,mobile?.querySelector('a.active'),'mobile',true);
  glider(desktop,desktop?.querySelector('a.active'),'desktop');
 }
 function sections(){const host=document.querySelector('.rx-home-tabs');glider(host,host?.querySelector('[aria-current=page]'),'sections');}
 function enterPage(){
  navigation();sections();pageMotion?.cancel();
  if(!allowed())return;
  const page=document.querySelector('#page');if(page)pageMotion=page.animate([{opacity:.8,transform:'translateY(4px)'},{opacity:1,transform:'translateY(0)'}],{duration:160,easing:ease});
 }
 function dialog(overlay,replacing=false){
  const panel=overlay?.querySelector('.r-modal');if(!panel||!allowed()||replacing)return;
  const mobile=innerWidth<=760,rect=panel.getBoundingClientRect();
  const origin=source&&performance.now()-source.at<2000?`${Math.max(0,Math.min(rect.width,source.x-rect.x))}px ${Math.max(0,Math.min(rect.height,source.y-rect.y))}px`:'50% 50%';
  panel.style.transformOrigin=mobile?'50% 100%':origin;
  panel.animate([{opacity:0,transform:mobile?'translateY(32px)':'scale(.955)'},{opacity:1,transform:'none'}],{duration:240,easing:ease});
  overlay.animate([{backgroundColor:'transparent'},{backgroundColor:getComputedStyle(overlay).backgroundColor}],{duration:180,easing:'ease-out'});
 }
 function dismiss(overlay,immediate=false){
  if(!overlay)return;
  overlay.inert=true;overlay.setAttribute('aria-hidden','true');overlay.style.pointerEvents='none';
  if(immediate||!allowed()){overlay.remove();return;}
  const panel=overlay.querySelector('.r-modal');panel?.getAnimations().forEach(a=>a.cancel());
  panel?.animate([{opacity:1,transform:'none'},{opacity:0,transform:innerWidth<=760?'translateY(24px)':'scale(.97)'}],{duration:140,easing:'cubic-bezier(.4,0,1,1)'});
  const animation=overlay.animate([{opacity:1},{opacity:0}],{duration:140,easing:'ease-out'});
  animation.finished.catch(()=>{}).finally(()=>overlay.remove());
 }
 function begin(){return {id:++route,start:performance.now()};}
 function finish(ticket,view){
  if(ticket.id!==route||document.hidden)return;
  // Measure after the new content has had a frame to paint; never delay the action.
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
   if(ticket.id!==route||document.hidden)return;
   performance.measure('rally:navigation:'+view,{start:ticket.start,end:performance.now()});
   const entries=performance.getEntriesByType('measure').filter(e=>e.name.startsWith('rally:navigation:'));
   if(entries.length>40)performance.clearMeasures(entries[0].name);
  }));
 }
 const resized=()=>{navigation();sections();};
 window.addEventListener('resize',resized,{passive:true});
 reduced.addEventListener('change',()=>{if(reduced.matches)document.querySelectorAll('.r-motion-glider,#page,.r-modal,.r-overlay').forEach(e=>e.getAnimations().forEach(a=>a.cancel()));resized();});
 return {navigation,sections,enterPage,dialog,dismiss,begin,finish};
}
