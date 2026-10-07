// Android/browser presentation only. No wallet, account or execution authority.
export function mobileUI({state,closeModal,closeTrade}){
 const root=document.documentElement,standalone=matchMedia('(display-mode: standalone)'),viewport=window.visualViewport;
 let frame=0,baseline=innerHeight,width=innerWidth,stack=[],pending=null,fromBack=false;
 const editable=()=>document.activeElement?.matches('input:not([type=button]):not([type=submit]),textarea,[contenteditable=true]');
 function measure(){
  frame=0;if(viewport&&Math.abs(viewport.scale-1)>.02)return;
  const height=viewport?.height||innerHeight;
  if(Math.abs(innerWidth-width)>80){baseline=innerHeight;width=innerWidth;}
  if(!editable())baseline=Math.max(innerHeight,height);
  const keyboard=Boolean(editable()&&baseline-height>120);
  root.style.setProperty('--r-viewport-height',height+'px');
  root.style.setProperty('--r-viewport-top',(viewport?.offsetTop||0)+'px');
  document.body.toggleAttribute('data-keyboard',keyboard);
  document.body.toggleAttribute('data-installed',standalone.matches||document.referrer.startsWith('android-app://com.rallydot.app'));
  if(keyboard){
   const active=document.activeElement,scroll=active?.closest('.r-trade-scroll,.r-checkout-scroll,.r-modal');
   if(scroll){const field=active.getBoundingClientRect(),bounds=scroll.getBoundingClientRect(),bottom=Math.min(bounds.bottom,height+(viewport?.offsetTop||0))-16;
    if(field.bottom>bottom)scroll.scrollTop+=field.bottom-bottom;
   }
  }
 }
 const schedule=()=>{if(!frame)frame=requestAnimationFrame(measure);};
 viewport?.addEventListener('resize',schedule,{passive:true});
 viewport?.addEventListener('scroll',schedule,{passive:true});
 window.addEventListener('resize',schedule,{passive:true});
 document.addEventListener('focusin',schedule);document.addEventListener('focusout',schedule);
 standalone.addEventListener('change',schedule);schedule();
 const layers=()=>[...(state.trade||state.nadOverlay?['trade']:[]),...(state.modal?['modal']:[])];
 function sync(){
  if(fromBack||pending)return;
  const wanted=layers();let same=0;while(same<stack.length&&same<wanted.length&&stack[same]===wanted[same])same++;
  if(same<stack.length){
   const remove=stack.length-same;stack=stack.slice(0,same);
   let done;const promise=new Promise(resolve=>{done=resolve;});pending={promise,done};
   history.go(-remove);return;
  }
  for(const name of wanted.slice(same)){
   stack.push(name);history.pushState({...history.state,rallyOverlay:stack.length},'',location.href);
  }
 }
 // A sheet gets its own same-URL history entry so Android Back closes the
 // sheet before leaving its market. Normal route snapshots remain unchanged.
 window.addEventListener('popstate',event=>{
  if(pending){
   event.stopImmediatePropagation();const wait=pending;pending=null;wait.done();sync();return;
  }
  if(stack.length&&Number(event.state?.rallyOverlay||0)<stack.length){
   event.stopImmediatePropagation();const name=stack.pop();fromBack=true;
   try{if(name==='modal')closeModal();else closeTrade();}finally{fromBack=false;sync();}
  }
 },{capture:true});
 const observer=new MutationObserver(sync);
 observer.observe(document.body,{attributes:true,attributeFilter:['class']});
 // Touch dismissal is a presentation gesture on the existing close control.
 // The header owns it; fields, content scrolling and order submission do not.
 const reduced=matchMedia('(prefers-reduced-motion:reduce)');let drag=null,settling;
 const locked=panel=>Boolean(state.financialBusy||state.busy||state.trade?.busy||state.trade?.submittedHash||document.body.hasAttribute('data-keyboard')||panel.matches('[data-order-state]')||panel.querySelector('.r-checkout-form[data-pending="true"],[data-order-state],[aria-busy="true"]'));
 const reset=g=>{g.panel.style.removeProperty('transform');g.panel.style.removeProperty('opacity');g.overlay.style.removeProperty('opacity');g.panel.classList.remove('r-sheet-dragging');};
 function restore(g){
  if(!g?.panel.isConnected)return;
  const from=getComputedStyle(g.panel).transform;reset(g);
  if(!reduced.matches){settling=g.panel.animate([{transform:from},{transform:'none'}],{duration:170,easing:'cubic-bezier(.22,.8,.24,1)'});settling.finished.catch(()=>{});}
 }
 function cancelDrag(){const g=drag;drag=null;if(g){if(g.head.hasPointerCapture(g.id))g.head.releasePointerCapture(g.id);restore(g);}}
 document.addEventListener('pointerdown',e=>{
  if(!e.isPrimary){cancelDrag();return;}
  const head=e.target.closest('.r-modal-head'),panel=head?.closest('.r-modal');
  if(!panel||innerWidth>760||e.pointerType!=='touch'||e.button!==0||e.target.closest('button,a,input,select,textarea')||locked(panel))return;
  settling?.cancel();drag={head,panel,overlay:panel.closest('.r-overlay'),instance:state.modal,id:e.pointerId,x:e.clientX,y:e.clientY,dy:0,start:performance.now(),samples:[],moving:false};
 },{capture:true,passive:true});
 document.addEventListener('pointermove',e=>{
  const g=drag;if(!g||g.id!==e.pointerId)return;
  if(!g.panel.isConnected||state.modal!==g.instance||locked(g.panel)){cancelDrag();return;}
  const dx=e.clientX-g.x,dy=e.clientY-g.y;
  if(!g.moving){if(Math.max(Math.abs(dx),Math.abs(dy))<10)return;if(dy<0||Math.abs(dx)>dy*.8){cancelDrag();return;}
   g.panel.getAnimations().forEach(a=>a.cancel());g.overlay.getAnimations().forEach(a=>a.cancel());g.head.setPointerCapture(e.pointerId);g.panel.classList.add('r-sheet-dragging');g.moving=true;
  }
  if(e.cancelable)e.preventDefault();g.dy=Math.max(0,dy);const now=performance.now();g.samples.push({y:e.clientY,at:now});g.samples=g.samples.filter(p=>now-p.at<100).slice(-8);
  g.panel.style.transform=`translate3d(0,${g.dy*.9}px,0)`;g.overlay.style.opacity=String(Math.max(.6,1-g.dy/700));
 },{capture:true,passive:false});
 document.addEventListener('pointerup',e=>{
  const g=drag;if(!g||g.id!==e.pointerId)return;drag=null;
  if(g.head.hasPointerCapture(g.id))g.head.releasePointerCapture(g.id);
  const first=g.samples[0],last=g.samples.at(-1),speed=first&&last&&performance.now()-last.at<100?(last.y-first.y)/Math.max(1,last.at-first.at):0;
  const accepted=g.moving&&(g.dy>=88||g.dy>=32&&speed>.65)&&g.panel.isConnected&&state.modal===g.instance&&!locked(g.panel);
  g.panel.classList.remove('r-sheet-dragging');if(accepted)closeModal();else restore(g);
 },{capture:true});
 document.addEventListener('pointercancel',cancelDrag,{capture:true});
 document.addEventListener('lostpointercapture',e=>{if(drag?.id===e.pointerId&&e.target===drag.head)cancelDrag();},{capture:true});
 window.addEventListener('blur',cancelDrag);document.addEventListener('visibilitychange',()=>{if(document.hidden)cancelDrag();});
 reduced.addEventListener('change',()=>{cancelDrag();settling?.cancel();});
 async function dismissForNavigation(){
  cancelDrag();settling?.cancel();
  closeModal(true);closeTrade();sync();
  while(pending)await pending.promise;
 }
 return {dismissForNavigation};
}
