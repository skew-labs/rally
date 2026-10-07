// Bounded, interruptible UI motion. No network, account or wallet authority.
export function motionUI(){
 const ease='cubic-bezier(.22,.8,.24,1)',reduced=matchMedia('(prefers-reduced-motion:reduce)');
 const previous=new Map(),active=new Set();let source,route=0,pageMotion,resizeFrame=0;
 const allowed=()=>!document.hidden&&!reduced.matches;
 function animate(element,frames,options){
  const animation=element.animate(frames,options);active.add(animation);
  animation.finished.catch(()=>{}).finally(()=>active.delete(animation));return animation;
 }
 document.addEventListener('pointerdown',event=>{
  const target=event.target.closest('button,a');if(!target||event.button>0)return;
  const box=target.getBoundingClientRect();source={x:box.x+box.width/2,y:box.y+box.height/2,at:performance.now()};
 },{passive:true,capture:true});
 function glider(host,target,key,mobile=false,withMotion=true){
  if(!host||!target||!host.getClientRects().length)return;
  let shape=host.querySelector(':scope>.r-motion-glider');
  if(!shape){shape=document.createElement('span');shape.className='r-motion-glider';shape.setAttribute('aria-hidden','true');host.append(shape);}
  const rect=target.getBoundingClientRect(),parent=host.getBoundingClientRect();
  const current={x:(mobile?rect.x+rect.width/2-23:rect.x)-parent.x+host.scrollLeft,y:(mobile?parent.y+5:rect.y)-parent.y+host.scrollTop,width:mobile?46:rect.width,height:mobile?36:rect.height};
  let old=previous.get(key);previous.set(key,current);
  if(old&&shape.getAnimations().length){const visible=shape.getBoundingClientRect();old={x:visible.x-parent.x+host.scrollLeft,y:visible.y-parent.y+host.scrollTop,width:visible.width,height:visible.height};}
  const moved=old&&(Math.abs(old.x-current.x)>1||Math.abs(old.y-current.y)>1||Math.abs(old.width-current.width)>1);
  if(moved||!withMotion)shape.getAnimations().forEach(a=>a.cancel());
  Object.assign(shape.style,{left:current.x+'px',top:current.y+'px',width:current.width+'px',height:current.height+'px'});
  if(moved&&withMotion&&allowed())animate(shape,[
   {transform:`translate(${old.x-current.x}px,${old.y-current.y}px) scaleX(${old.width/current.width})`},{transform:'translate(0,0) scaleX(1)'}
  ],{duration:220,easing:ease});
 }
 function navigation(withMotion=true){
  const mobile=document.querySelector('.r-mobile-nav'),desktop=document.querySelector('.r-sidebar nav[aria-label="Main navigation"]');
  glider(mobile,mobile?.querySelector('a.active'),'mobile',true,withMotion);
  glider(desktop,desktop?.querySelector('a.active'),'desktop',false,withMotion);
 }
 function sections(withMotion=true){const host=document.querySelector('.rx-home-tabs');glider(host,host?.querySelector('[aria-current=page]'),'sections',false,withMotion);}
 function enterPage(){
  navigation();sections();pageMotion?.cancel();
  if(!allowed())return;
  const page=document.querySelector('#page');if(page)pageMotion=animate(page,[{opacity:.94},{opacity:1}],{duration:140,easing:ease});
 }
 function dialog(overlay,replacing=false){
  const panel=overlay?.querySelector('.r-modal');if(!panel||!allowed()||replacing)return;
  const mobile=innerWidth<=760,rect=panel.getBoundingClientRect();
  const origin=source&&performance.now()-source.at<2000?`${Math.max(0,Math.min(rect.width,source.x-rect.x))}px ${Math.max(0,Math.min(rect.height,source.y-rect.y))}px`:'50% 50%';
  panel.style.transformOrigin=mobile?'50% 100%':origin;
  animate(panel,[{opacity:0,transform:mobile?'translateY(24px)':'scale(.975)'},{opacity:1,transform:'none'}],{duration:200,easing:ease});
  animate(overlay,[{opacity:0},{opacity:1}],{duration:160,easing:'ease-out'});
 }
 function dismiss(overlay,immediate=false){
  if(!overlay)return;
  overlay.inert=true;overlay.setAttribute('aria-hidden','true');overlay.style.pointerEvents='none';
  if(immediate||!allowed()){overlay.remove();return;}
  const panel=overlay.querySelector('.r-modal'),style=panel&&getComputedStyle(panel),from=style&&{opacity:style.opacity,transform:style.transform},scrimOpacity=getComputedStyle(overlay).opacity;
  panel?.getAnimations().forEach(a=>a.cancel());overlay.getAnimations().forEach(a=>a.cancel());
  if(panel)animate(panel,[from,{opacity:0,transform:innerWidth<=760?'translateY(16px)':'scale(.985)'}],{duration:120,easing:'cubic-bezier(.4,0,1,1)'});
  const animation=animate(overlay,[{opacity:scrimOpacity},{opacity:0}],{duration:120,easing:'ease-out'});
  // Finish cleanup even if a busy browser delays the animation's final frame.
  const timer=setTimeout(()=>overlay.remove(),140);
  animation.finished.catch(()=>{}).finally(()=>{clearTimeout(timer);overlay.remove();});
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
 const resized=()=>{if(resizeFrame)return;resizeFrame=requestAnimationFrame(()=>{resizeFrame=0;navigation(false);sections(false);});};
 window.addEventListener('resize',resized,{passive:true});
 reduced.addEventListener('change',()=>{if(reduced.matches)active.forEach(a=>a.cancel());resized();});
 return {navigation,sections,enterPage,dialog,dismiss,begin,finish};
}
