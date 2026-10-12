// A bounded preview of the same observed history used by the token detail.
export function swipeHistory(api){
 const cache=new Map();let requests=new Set();
 function dispose(){for(const c of requests)c.abort();requests.clear();}
 async function mount(host,item){
  if(!host||host.dataset.loaded||!item?.asset||item.pool)return;
  host.dataset.loaded='true';const t=item.asset,m=item.market,assetId=m?String(m.id):t.id,key=(m?.venue||'spot')+':'+assetId;
  const controller=new AbortController();requests.add(controller);
  try{
   let data=cache.get(key);if(!data||Date.now()-data.at>30000){
    const path=t.nadfun&&!t.graduated?'/api/nadfun/chart?'+new URLSearchParams({token:assetId,interval:'60'}):'/api/market-chart?'+new URLSearchParams({asset:assetId,kind:m?'perps':'spot',period:'1D'});
    const d=await api(path,undefined,{signal:controller.signal});
    if(String(d.asset||d.token).toLowerCase()!==String(assetId).toLowerCase())throw Error('Chart identity changed');
    const cutoff=Date.now()/1000-86400;
    const points=(d.points||d.candles||[]).map(p=>({time:Number(p.time),value:Number(p.value??p.close)})).filter(p=>Number.isFinite(p.value)&&p.value>0&&Number.isFinite(p.time)&&p.time>=cutoff&&p.time<=Date.now()/1000+60).sort((a,b)=>a.time-b.time);
    data={points,at:Date.now()};cache.set(key,data);while(cache.size>24)cache.delete(cache.keys().next().value);
   }
   if(controller.signal.aborted||!host.isConnected)return;
   const points=data.points;if(points.length<2){host.textContent='Price history unavailable';return;}
   const low=Math.min(...points.map(p=>p.value)),high=Math.max(...points.map(p=>p.value)),range=high-low||low*.01;
   const span=points.at(-1).time-points[0].time||1,step=Math.max(1,Math.ceil(points.length/240)),sample=points.filter((_,i)=>i%step===0||i===points.length-1);
   const path=sample.map((p,i)=>(i?'L':'M')+(8+(p.time-points[0].time)/span*384).toFixed(2)+','+(112-(p.value-low)/range*96).toFixed(2)).join(' ');
   host.innerHTML=`<svg viewBox="0 0 400 128" preserveAspectRatio="none" role="img" aria-label="Observed price history over the last day"><path d="${path}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/></svg><small>1D · Price history</small>`;
  }catch(e){if(!controller.signal.aborted&&host.isConnected)host.textContent='Open chart for details';}
  finally{requests.delete(controller);}
 }
 return {mount,dispose};
}
