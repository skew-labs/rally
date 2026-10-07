// Connection presentation and bounded reads. Writes retain their caller's policy.
export async function networkRequest(path,options={},deadline=12000){
 const read=['GET','HEAD'].includes(String(options.method||'GET').toUpperCase());
 if(read&&navigator.onLine===false)throw new Error('You’re offline. Reconnect and try again.');
 const controller=read?new AbortController():null,external=options.signal;
 let timedOut=false,timer;
 const cancel=()=>controller?.abort(external.reason);
 if(controller){
  if(external?.aborted)cancel();else external?.addEventListener('abort',cancel,{once:true});
  timer=setTimeout(()=>{timedOut=true;controller.abort();},deadline);
 }
 try{
  const response=await fetch(path,{...options,...(controller?{signal:controller.signal}:{})});
  const value=await response.json().catch(error=>{
   if(controller?.signal.aborted||external?.aborted)throw error;
   return {message:'Connection interrupted. Try again.'};
  });
  return {response,value};
 }catch(error){
  if(external?.aborted)throw new DOMException('Request canceled','AbortError');
  if(timedOut)throw new DOMException('Connection timed out. Try again.','TimeoutError');
  if(error instanceof TypeError)throw new Error(navigator.onLine===false?'You’re offline. Reconnect and try again.':'Connection interrupted. Try again.');
  throw error;
 }finally{clearTimeout(timer);external?.removeEventListener('abort',cancel);}
}

export function connectionUI(){
 const status=document.createElement('div');status.className='r-connection-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.hidden=true;document.body.append(status);
 const update=()=>{const offline=navigator.onLine===false;document.body.toggleAttribute('data-offline',offline);status.hidden=!offline;status.textContent=offline?'Offline':'';};
 window.addEventListener('online',update,{passive:true});window.addEventListener('offline',update,{passive:true});update();
 // The worker only supplies a public offline navigation screen. It never
 // stores account data, market data, API responses or pending transactions.
 if('serviceWorker' in navigator&&isSecureContext&&['https:','http:'].includes(location.protocol)&&location.pathname!=='/authorize'){
  const register=()=>navigator.serviceWorker.register('/rally-offline.js',{scope:'/',updateViaCache:'none'}).catch(()=>{});
  if(document.readyState==='complete')register();else window.addEventListener('load',register,{once:true});
 }
}
