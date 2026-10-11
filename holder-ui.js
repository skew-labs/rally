// Public indexed observations only. These snapshots never authorize a trade.
const cache=new Map(),pending=new Map(),listeners=new Map();
const storageKey='rally:holder-snapshots:v1',now=()=>Date.now()/1000;
const address=/^0x[0-9a-f]{40}$/i;
function valid(p,id){
 return p?.asset?.toLowerCase()===id&&typeof p.indexed==='boolean'&&Array.isArray(p.holders)&&p.holders.length<=20&&
  (p.total==null||Number.isSafeInteger(p.total)&&p.total>=0)&&
  p.holders.every(h=>address.test(h.address)&&typeof h.amount==='string'&&/^\d+(\.\d+)?$/.test(h.amount)&&h.amount.length<=116&&(!h.name||typeof h.name==='string'&&h.name.length<=80))&&
  (p.fetchedAt==null||Number.isFinite(p.fetchedAt)&&now()-p.fetchedAt>=0&&now()-p.fetchedAt<=900);
}
try{const raw=localStorage.getItem(storageKey)||'[]';if(raw.length<=256000)for(const p of JSON.parse(raw).slice(-16)){const id=p?.asset?.toLowerCase();if(address.test(id)&&valid(p,id)&&p.fetchedAt)cache.set(id,p);}}catch{}
let persistTimer;
function remember(id,p){
 if(!valid(p,id))throw Error('Holder identity or observations changed');
 if(!p.fetchedAt&&cache.get(id)?.fetchedAt)return cache.get(id);
 cache.delete(id);cache.set(id,p);while(cache.size>32)cache.delete(cache.keys().next().value);
 if(p.fetchedAt){clearTimeout(persistTimer);persistTimer=setTimeout(()=>{try{localStorage.setItem(storageKey,JSON.stringify([...cache.values()].filter(p=>p.fetchedAt).slice(-16)));}catch{}},500);}
 for(const update of listeners.get(id)||[])update(p);
 return p;
}
export function cachedHolders(asset){
 const id=String(asset).toLowerCase(),p=cache.get(id);return p&&valid(p,id)?{...p,stale:!!p.stale||!!p.fetchedAt&&now()-p.fetchedAt>=90}:null;
}
export function warmHolders(c,asset,foreground=false){
 const id=String(asset).toLowerCase();if(!address.test(id))return Promise.resolve(null);
 const saved=cachedHolders(id);if(saved?.fetchedAt&&now()-saved.fetchedAt<60&&!saved.refreshing)return Promise.resolve(saved);
 if(pending.has(id))return pending.get(id);
 if(pending.size>=(foreground?4:3))return Promise.resolve(saved);
 const task=(async()=>{
  for(let i=0;i<20;i++){
   const p=remember(id,await c.api('/api/token-holders?asset='+id));
   if(!p.refreshing&&!p.waiting)return p;
   await new Promise(r=>setTimeout(r,i===0?400:i===1?800:i===2?1500:2500));
  }
  return cachedHolders(id);
 })().finally(()=>pending.delete(id));pending.set(id,task);return task;
}
function html(c,p){
 if(!p)return '<div class="r-holders-title"><h3>Holders</h3><small>Updating…</small></div><div class="r-holder-skeleton" aria-label="Loading holders"><i></i><i></i><i></i></div>';
 if(!p.indexed)return '<div class="r-holders-title"><h3>Holders</h3></div><p class="r-note">Holder indexing is unavailable for this asset.</p>';
 return `<div class="r-holders-title"><h3>Holders ${p.total!=null?'<small>'+c.esc(Number(p.total).toLocaleString('en-US'))+'</small>':''}</h3><small>${p.fetchedAt?c.esc(p.source||'nad.fun')+' · '+c.age(p.fetchedAt)+(p.stale?' · Last known':''):p.refreshing||p.waiting?'Updating…':'Unavailable'}</small></div><div class="r-holders-columns" aria-hidden="true"><span>Wallet</span><span>Tokens</span></div>${p.holders.map((h,i)=>{
  const short=h.address.slice(0,6)+'…'+h.address.slice(-4),name=h.name&&!/^0x/i.test(h.name)?h.name:null,n=Number(h.amount);
  const amount=Number.isFinite(n)?n>0&&(n<.000001||n>=1e15)?n.toExponential(3):n.toLocaleString('en-US',{notation:n>=100000?'compact':'standard',maximumSignificantDigits:4}):'—';
  return `<a class="r-holder" href="https://monadvision.com/address/${c.esc(h.address)}" target="_blank" rel="noopener noreferrer" aria-label="${c.esc((name||short)+', '+h.amount+' tokens. View wallet')}"><span class="r-holder-rank">${i+1}</span><span class="r-holder-identity"><b title="${c.esc(name||h.address)}">${c.esc(name||short)}</b>${name?'<small>'+c.esc(short)+'</small>':''}</span><b class="r-holder-amount" title="${c.esc(h.amount)} tokens">${c.esc(amount)}</b></a>`;
 }).join('')}${!p.holders.length&&!p.refreshing&&!p.waiting?'<p class="r-note">'+c.esc(p.error||'No indexed holders yet.')+'</p>':''}`;
}
export function mountHolders(c,host,asset){
 if(!host||!address.test(asset))return;
 const id=asset.toLowerCase();host.dataset.holderAsset=id;
 const paint=p=>{if(!host.isConnected||host.dataset.holderAsset!==id)return;const content=html(c,p);if(host.innerHTML!==content)host.innerHTML=content;host.dataset.holdersReady=String(!!p?.fetchedAt);};
 paint(cachedHolders(id));
 const update=p=>{if(host.isConnected)paint({...p,stale:!!p.stale||!!p.fetchedAt&&now()-p.fetchedAt>=90});else listeners.get(id)?.delete(update);};
 if(!listeners.has(id))listeners.set(id,new Set());listeners.get(id).add(update);
 const refresh=async()=>{for(let i=0;i<20&&host.isConnected;i++){const p=await warmHolders(c,id,true);if(p)return;await new Promise(r=>setTimeout(r,500));}};
 return refresh().catch(()=>{if(!cachedHolders(id)&&host.isConnected)host.innerHTML='<h3>Holders</h3><p class="r-note">Temporarily unavailable.</p>';}).finally(()=>{listeners.get(id)?.delete(update);if(!listeners.get(id)?.size)listeners.delete(id);});
}
