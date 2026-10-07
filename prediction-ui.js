// Public market presentation. Signing and settlement remain in financeUI.
export function predictionUI(c,readReferences){
 const {S,$,api,esc,icon,usd,age,empty}=c;
 const time=new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
 const state=p=>p.state==='settled'?'settled':p.close>Date.now()/1000?'open':'awaiting_settlement';
 const visible=()=>!document.hidden&&(S.view==='explore'||S.view==='home'&&S.homeSection==='markets')&&S.marketTab==='prediction';
 let request,referenceRequest,host,clock,observer,failed=false;
 const reference=p=>S.perps?.markets.find(m=>m.venue==='Perpl'&&String(m.id)===String(p?.assetInfo?.chartMarket));
 const fresh=m=>m&&!m.stale&&Number.isFinite(Number(m.mark))&&Number(m.mark)>0&&Date.now()/1000-m.observationAt>=-5&&Date.now()/1000-m.observationAt<=60;
 const format=t=>time.format(new Date(t*1000));
 const text=(node,value)=>{if(node&&node.textContent!==String(value))node.textContent=value;};
 const remaining=t=>{const s=Math.max(0,Math.ceil(t-Date.now()/1000));return s<60?s+'s':s<3600?Math.ceil(s/60)+'m':s<86400?Math.floor(s/3600)+'h '+Math.floor(s%3600/60)+'m':Math.ceil(s/86400)+'d';};
 function quotes(){
  const pools=S.predictions?.pools||[],symbols=['MON','BTC','ETH','SOL'];
  return symbols.map(symbol=>{const p=pools.find(p=>p.asset===symbol&&p.assetInfo),m=p&&reference(p),value=fresh(m)?usd(m.mark):'—';return `<button class="r-prediction-reference" ${p?`data-action="prediction-detail" data-id="${p.id}"`:'disabled'} aria-label="${symbol} reference price chart"><span>${c.logo(p?.assetInfo||{symbol},true)}<b>${symbol}</b></span><strong data-reference-symbol="${symbol}">${value}</strong></button>`;}).join('');
 }
 function card(p){
  const asset=p.assetInfo||(p.predictionReviewed?c.token(p.assetId):null),label=p.asset.length>15?'Asset':p.asset;
  const status=p.state==='open'?'Open':p.state==='settled'?'Resolved':'Pending';
  return `<article class="r-prediction-card" data-prediction-pool="${p.id}" data-state="${p.state}"><div class="r-prediction-identity">${c.logo(asset||{symbol:'?'},true)}<div><h2>${esc(label)}${asset?' / USD':''}</h2><small>Castora #${p.id}</small></div><span class="r-prediction-state">${status}</span></div><p class="r-prediction-question">${esc(label)} price on ${esc(format(p.snapshot))}</p>${p.state==='settled'?`<div class="r-prediction-result">${usd(p.settlementPrice)}<small>Resolved price</small></div>`:''}<dl class="r-prediction-terms"><div><dt>Entry</dt><dd>${esc(p.stake||'—')} ${esc(p.stakeAsset.length>15?p.stakeAsset.slice(0,6)+'…'+p.stakeAsset.slice(-4):p.stakeAsset)}</dd></div><div><dt>Entries</dt><dd data-prediction-entries>${p.predictions}</dd></div><div><dt>Pool fee</dt><dd>${p.feeBps/100}%</dd></div>${p.state==='settled'?`<div><dt>Winners</dt><dd>${p.winners??'—'}</dd></div>`:''}</dl><div class="r-prediction-actions"><small>${p.state==='open'?`Closes in <span data-prediction-close="${p.close}">${remaining(p.close)}</span>`:p.state==='settled'?'Resolved':'Awaiting settlement'}</small>${p.state==='open'?`<button class="r-btn small primary" data-action="predict" data-id="${p.id}" ${p.stakeReviewed&&p.predictionReviewed?'':'disabled'}>Predict</button>`:asset?`<button class="r-btn small" data-action="${p.assetInfo?'prediction-detail':'market-detail'}" data-id="${esc(p.assetInfo?p.id:p.assetId)}">Chart</button>`:''}</div></article>`;
 }
 function tick(){
  if(!host?.isConnected){stop();return;}if(!visible())return;
  const elapsed=Date.now()/1000-(S.predictions?.fetchedAt||0),sync=host.querySelector('[data-prediction-sync]');
  if(sync){sync.dataset.state=failed||elapsed>60?'delayed':'current';text(sync,(failed||elapsed>60?'Update delayed · ':'Updated ')+age(S.predictions?.fetchedAt||0));}
  for(const e of host.querySelectorAll('[data-prediction-close]')){if(Number(e.dataset.predictionClose)<=Date.now()/1000){render(host,S.filter.toLowerCase());break;}e.textContent=remaining(Number(e.dataset.predictionClose));}
  patchPrices();
 }
 function patchPrices(){
  if(!host?.isConnected)return;
  for(const e of host.querySelectorAll('[data-reference-symbol]')){const p=S.predictions.pools.find(p=>p.asset===e.dataset.referenceSymbol&&p.assetInfo),m=p&&reference(p),value=fresh(m)?usd(m.mark):'—';if(e.textContent!==value)e.textContent=value;}
  const source=host.querySelector('[data-prediction-price-source]'),prices=['MON','BTC','ETH','SOL'].map(symbol=>reference(S.predictions?.pools.find(p=>p.asset===symbol&&p.assetInfo))).filter(fresh);
  text(source,prices.length?'Perpl mark · Reference only':'Reference prices unavailable');
 }
 function stop(){clearInterval(clock);clock=null;observer?.disconnect();observer=null;}
 function watch(){
  if(!clock)clock=setInterval(tick,1000);
  if(!observer){observer=new MutationObserver(()=>{if(!host?.isConnected)stop();});observer.observe(document.querySelector('#app'),{childList:true,subtree:true});}
 }
 function render(target,q){
  if(!target?.isConnected||S.marketTab!=='prediction'||S.filter.toLowerCase()!==q)return;
  host=target;const d=S.predictions,all=d.pools.map(p=>({...p,state:state(p)}));
  S.predictionStatus ||= 'open';
  const matching=all.filter(p=>(p.asset+' '+p.assetId+' '+(c.token(p.assetId)?.name||'')+' '+p.id).toLowerCase().includes(q)&&(!S.watchOnly||(S.boot?.watches||[]).includes(p.assetId)));
  const filters=[['open','Open',matching.filter(p=>p.state==='open').length],['recent','History',matching.length],['settled','Resolved',matching.filter(p=>p.state==='settled').length]];
  const pools=matching.filter(p=>S.predictionStatus==='recent'||p.state===S.predictionStatus);
  if(!host.querySelector('.r-prediction-shell'))host.innerHTML=`<section class="r-prediction-shell"><div class="r-prediction-heading"><div><b>Price predictions</b><span data-prediction-sync role="status" aria-live="off"></span></div><button class="r-icon-button" data-action="my-predictions" aria-label="My predictions">${icon('wallet')}</button></div><div class="r-prediction-references">${quotes()}</div><small class="r-prediction-price-source" data-prediction-price-source></small><div class="r-prediction-filters" role="group" aria-label="Prediction status">${filters.map(([id,label])=>`<button data-action="prediction-status" data-id="${id}" aria-pressed="false">${label}<span data-prediction-count="${id}"></span></button>`).join('')}</div><div class="r-prediction-list"></div><div class="r-data-foot"><span data-prediction-scope></span><button class="r-text-button" data-action="refresh-predictions">Refresh</button></div></section>`;
  for(const [id,,count] of filters){const b=host.querySelector(`[data-action="prediction-status"][data-id="${id}"]`),selected=String(id===S.predictionStatus);if(b.getAttribute('aria-pressed')!==selected)b.setAttribute('aria-pressed',selected);text(b.querySelector('span'),count);}
  const list=host.querySelector('.r-prediction-list'),previous=new Map([...list.querySelectorAll('[data-prediction-pool]')].map(e=>[e.dataset.predictionPool,e]));
  if(pools.length){list.querySelector('.r-prediction-empty')?.remove();for(const [index,p] of pools.entries()){let node=previous.get(String(p.id));const signature=JSON.stringify(p);if(!node||node.dataset.signature!==signature){const template=document.createElement('template');template.innerHTML=card(p);const next=template.content.firstElementChild;next.dataset.signature=signature;if(node){const focused=node.contains(document.activeElement),action=document.activeElement?.dataset?.action;node.replaceWith(next);if(focused)next.querySelector(`[data-action="${action}"]`)?.focus({preventScroll:true});}node=next;}if(list.children[index]!==node)list.insertBefore(node,list.children[index]||null);previous.delete(String(p.id));}previous.forEach(node=>node.remove());}
  else{const key=q||S.watchOnly?'search':S.predictionStatus;if(list.dataset.empty!==key||!list.querySelector('.r-prediction-empty'))list.innerHTML=`<div class="r-prediction-empty">${icon('prediction')}<h2>${key==='search'?'No matching pools':key==='open'?'No open pools':'No resolved pools'}</h2><p>${key==='search'?'Try another asset or pool number.':key==='open'?'New Monad pools will appear here automatically.':'Check the pool history.'}</p><button class="r-btn" data-action="prediction-status" data-id="recent">View history</button></div>`;list.dataset.empty=key;}
  host.querySelector('[data-prediction-scope]').textContent=(d.scope==='all'?'All '+d.totalPools:d.pools.length+' of '+d.totalPools)+' pools · Monad';
  watch();tick();
 }
 async function prices(){
  if(!visible())return;
  if(S.perps&&Date.now()/1000-S.perps.fetchedAt<15){patchPrices();return;}
  if(!referenceRequest)referenceRequest=readReferences().then(patchPrices).catch(()=>patchPrices()).finally(()=>{referenceRequest=null;});
  return referenceRequest;
 }
 async function read(target,q,force=false){
  // A tab/filter action never waits on an RPC read to display an existing
  // catalog. Its timestamp and delayed state stay visible during refresh.
  if(S.predictions)render(target,q);
  if(!force&&S.predictions&&Math.abs(Date.now()/1000-S.predictions.fetchedAt)<15){prices();return;}
  if(!request)request=api('/api/predictions').then(d=>{S.predictions=d;failed=false;return d;}).catch(e=>{failed=true;tick();throw e;}).finally(()=>{request=null;});
  try{await request;}catch(e){if(!S.predictions)throw e;return;}
  render(target,q);prices();
 }
 async function refresh(){if(!visible())return;await read($('#market-list'),S.filter.toLowerCase());}
 document.addEventListener('visibilitychange',()=>{if(!document.hidden&&visible()){tick();refresh().catch(()=>{});}});
 return {read,render,refresh,state,reference,fresh};
}
