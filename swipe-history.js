// Display-only history, shared by the visible card and its next-card prefetch.
export function swipeHistory(api){
 const cache=new Map(),pending=new Map();let epoch=0;
 const identity=item=>{if(!item?.asset||item.pool)return null;const t=item.asset,m=item.market,id=String(m?m.id:t.id);return {id,key:(m?.venue||'spot')+':'+id,path:t.nadfun&&!t.graduated?'/api/nadfun/chart?'+new URLSearchParams({token:id,interval:'60',preview:'1'}):'/api/market-chart?'+new URLSearchParams({asset:id,kind:m?'perps':'spot',period:'1D'})};};
 function dispose(){epoch++;for(const p of pending.values())p.controller.abort();pending.clear();}
 async function read(ref){
  const known=cache.get(ref.key);if(known&&Date.now()-known.at<30000)return known;
  if(pending.has(ref.key))return pending.get(ref.key).promise;
  // Fast swipes must not queue an unbounded number of provider reads.
  if(pending.size>=2){const [key,p]=pending.entries().next().value;p.controller.abort();pending.delete(key);}
  const controller=new AbortController(),version=epoch;
  const task={controller};pending.set(ref.key,task);
  task.promise=(async()=>{
   for(let attempt=0;attempt<5;attempt++){
    const d=await api(ref.path,undefined,{signal:controller.signal});
    if(controller.signal.aborted||version!==epoch)throw new DOMException('Aborted','AbortError');
    if(String(d.asset||d.token).toLowerCase()!==ref.id.toLowerCase())throw Error('Chart identity changed');
    const now=Date.now()/1000,byTime=new Map();
    for(const p of d.points||d.candles||[]){const time=Number(p.time),value=Number(p.value??p.close);if(Number.isFinite(value)&&value>0&&Number.isFinite(time)&&time>=now-86400&&time<=now+60)byTime.set(time,{time,value});}
    const points=[...byTime.values()].sort((a,b)=>a.time-b.time);
    if(points.length||!d.refreshing||attempt===4){const data={points,at:Date.now(),stale:Boolean(d.stale)};if(points.length){cache.delete(ref.key);cache.set(ref.key,data);while(cache.size>24)cache.delete(cache.keys().next().value);}return data;}
    await new Promise((resolve,reject)=>{const abort=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));};const timer=setTimeout(()=>{controller.signal.removeEventListener('abort',abort);resolve();},Math.min(8,Math.max(2,Number(d.retryAfter)||2))*1000);controller.signal.addEventListener('abort',abort,{once:true});});
   }
  })().finally(()=>{if(pending.get(ref.key)===task)pending.delete(ref.key);});
  return task.promise;
 }
 function prefetch(item){const ref=identity(item);if(ref&&pending.size<2)return read(ref).catch(()=>{});}
 async function mount(host,item){
  const ref=identity(item);if(!host||!ref||host.dataset.loaded===ref.key)return;
  host.dataset.loaded=ref.key;
  try{
   const data=await read(ref);if(!host.isConnected||host.dataset.loaded!==ref.key)return;
   const points=data.points;if(points.length<2){host.textContent='No recent price history';delete host.dataset.loaded;return;}
   const low=Math.min(...points.map(p=>p.value)),high=Math.max(...points.map(p=>p.value)),range=high-low||low*.01;
   const span=points.at(-1).time-points[0].time||1,step=Math.max(1,Math.ceil(points.length/240)),sample=points.filter((_,i)=>i%step===0||i===points.length-1);
   const path=sample.map((p,i)=>(i?'L':'M')+(8+(p.time-points[0].time)/span*384).toFixed(2)+','+(high===low?64:112-(p.value-low)/range*96).toFixed(2)).join(' ');
   host.innerHTML=`<svg viewBox="0 0 400 128" preserveAspectRatio="none" role="img" aria-label="Observed price history over the last day"><path d="${path}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/></svg><small>1D · ${data.stale?'Last available history':'Price history'}</small>`;
  }catch(e){if(host.isConnected&&host.dataset.loaded===ref.key){delete host.dataset.loaded;if(e.name!=='AbortError')host.textContent='Open chart for details';}}
 }
 return {mount,prefetch,dispose};
}
