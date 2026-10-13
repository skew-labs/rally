export const tokenCategories=[['crypto','Crypto'],['trending','Trending'],['graduated','Graduated'],['new','New']];
export function tokenCategory(params){
 const requested=params.get('category');
 if(tokenCategories.some(([key])=>key===requested))return requested;
 return params.get('tab')==='memes'?(params.get('phase')==='dex'?'graduated':params.get('sort')==='latest'?'new':'trending'):'crypto';
}
export function tokenMarketsUI(c){
 const {S,api,esc,logo,usd,priceHTML,volumeHTML,age}=c;let state=null,sequence=0,observer=null,refreshing=false;
 const cache=new Map();
 const active=()=>['home','explore'].includes(S.view)&&S.marketTab==='tokens'&&(S.view!=='home'||S.homeSection==='markets');
 function filters(){return `<div class="rt-filters" role="group" aria-label="Token categories">${tokenCategories.map(([id,label])=>`<button data-action="token-category" data-id="${id}" aria-pressed="${S.tokenCategory===id}">${label}</button>`).join('')}</div>`;}
 const metrics=t=>{const cap=t.nadfun&&Number(t.marketCap)>0;return `<b>${cap?usd(t.marketCap):priceHTML(t.price)}</b><small>${t.stale?'Last known':cap?priceHTML(t.price):t.change==null?'—':(t.change>=0?'+':'')+Number(t.change).toFixed(2)+'%'}</small>`;};
 function row(t){const action=t.nadfun?'nad-token':'market-detail';return `<article class="rt-token-row" data-token-row="${esc(t.id)}"><button class="rt-identity" data-action="${action}" data-id="${esc(t.id)}" aria-label="Open ${esc(t.symbol)}">${logo(t)}<span><b>${esc(t.symbol)}</b><small>${esc(t.name)}</small></span></button><button class="rt-price" data-action="${action}" data-id="${esc(t.id)}">${metrics(t)}</button><span class="rt-change ${!t.stale&&t.change!=null?(t.change>=0?'positive':'negative'):''}">${t.change==null?'—':(t.change>=0?'+':'')+Number(t.change).toFixed(2)+'%'}</span><span class="rt-volume">${volumeHTML(t.volume)}</span><button class="rt-buy" data-action="${t.nadfun?'nad-token':'trade'}" data-id="${esc(t.id)}" data-order="buy" aria-label="Buy ${esc(t.symbol)}" ${t.locked||t.tradeSupported===false?'disabled':''}>Buy</button></article>`;}
 function remember(tokens){const map=new Map(S.tokens.map(t=>[t.id,t]));tokens.forEach(t=>map.set(t.id,{...map.get(t.id),...t}));S.tokens=[...map.values()];}
 function dispose(){sequence++;observer?.disconnect();observer=null;state?.controller.abort();state=null;}
 function footer(){if(!state?.host.isConnected)return;const more=state.host.querySelector('.rt-more');more.innerHTML=state.cursor?`<button data-action="token-more" ${state.busy?'disabled':''}>${state.busy?'Loading…':'Load more'}</button>`:'';observer?.disconnect();if(state.cursor&&!state.busy){observer=new IntersectionObserver(entries=>{if(entries.some(x=>x.isIntersecting)&&!S.modal&&!S.nadOverlay&&!document.hidden)append();},{rootMargin:'160px'});observer.observe(more);}}
 function draw(){const x=state;if(!x?.host.isConnected)return;x.host.innerHTML=`<div class="rt-table-head"><span>Token</span><span>Price / Mcap</span><span>24h</span><span>Volume</span><span></span></div><div class="rt-rows">${x.tokens.map(row).join('')||'<div class="rt-empty">No tokens found</div>'}</div><div class="rt-more"></div><div class="rt-foot"><span>${x.total.toLocaleString('en-US')} tokens</span><span title="Rally ranks observed liquidity, volume and price activity. New and Graduated use verified launch records.">Rally ranked</span></div>`;footer();}
 async function show(host){dispose();const seq=sequence,category=S.tokenCategory||'crypto',query=(S.filter||'').trim();const params=new URLSearchParams({category,query,limit:40});if(S.watchOnly)params.set('watch',S.boot.watches.join(','));const key=params.toString(),hit=cache.get(key);state={host,params,controller:new AbortController(),tokens:[],cursor:null,busy:true};
  if(hit&&Date.now()-hit.at<15000){Object.assign(state,hit.data,{tokens:[...hit.data.tokens],busy:false});remember(state.tokens);draw();return;}
  host.innerHTML='<div class="rt-loading" role="status" aria-label="Loading tokens">'+Array.from({length:8},()=>'<div><i></i><span></span><b></b></div>').join('')+'</div>';
  try{const data=await api('/api/token-markets?'+params,undefined,{signal:state.controller.signal});if(seq!==sequence||!host.isConnected)return;remember(data.tokens);Object.assign(state,{tokens:data.tokens,total:data.total,cursor:data.nextCursor,busy:false});cache.set(key,{at:Date.now(),data:{tokens:[...data.tokens],total:data.total,cursor:data.nextCursor}});while(cache.size>12)cache.delete(cache.keys().next().value);draw();}
  catch(e){if(seq===sequence&&host.isConnected)host.innerHTML=`<div class="rt-empty"><p>${esc(e.message)}</p><button data-action="refresh-markets">Retry</button></div>`;}
 }
 async function append(){const x=state;if(!x?.cursor||x.busy||!active())return;x.busy=true;footer();const params=new URLSearchParams(x.params);params.set('cursor',x.cursor);
  try{const data=await api('/api/token-markets?'+params,undefined,{signal:x.controller.signal});if(state!==x||!x.host.isConnected)return;const known=new Set(x.tokens.map(t=>t.id)),added=data.tokens.filter(t=>!known.has(t.id));x.tokens.push(...added);remember(added);x.cursor=data.nextCursor;x.host.querySelector('.rt-rows').insertAdjacentHTML('beforeend',added.map(row).join(''));}
  catch(e){if(state===x){observer?.disconnect();x.host.querySelector('.rt-more').innerHTML=`<button data-action="refresh-markets">${esc(e.message)} · Refresh</button>`;return;}}
  finally{x.busy=false;}footer();
 }
 async function refresh(){const x=state;if(refreshing||!active()||!x?.host.isConnected||document.hidden||S.modal||S.nadOverlay)return;const rows=[...x.host.querySelectorAll('[data-token-row]')].filter(r=>{const b=r.getBoundingClientRect();return b.bottom>0&&b.top<innerHeight+300;}).slice(0,60);if(!rows.length)return;refreshing=true;
  try{const data=await api('/api/token-markets/references?'+new URLSearchParams({assets:rows.map(r=>r.dataset.tokenRow).join(',')}));if(state!==x)return;remember(data.tokens);const map=new Map(data.tokens.map(t=>[t.id,t]));for(const r of rows){const t=map.get(r.dataset.tokenRow);if(!t||!r.isConnected)continue;r.querySelector('.rt-price').innerHTML=metrics(t);const change=r.querySelector('.rt-change');change.textContent=t.change==null?'—':(t.change>=0?'+':'')+Number(t.change).toFixed(2)+'%';change.classList.toggle('positive',!t.stale&&t.change!=null&&t.change>=0);change.classList.toggle('negative',!t.stale&&t.change!=null&&t.change<0);r.querySelector('.rt-volume').innerHTML=volumeHTML(t.volume);}}
  catch{}finally{refreshing=false;}
 }
 setInterval(refresh,15000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
 return {filters,show,dispose,append,refresh,invalidate:()=>cache.clear()};
}
