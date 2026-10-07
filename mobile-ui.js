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
 async function dismissForNavigation(){
  closeModal(true);closeTrade();sync();
  while(pending)await pending.promise;
 }
 return {dismissForNavigation};
}
