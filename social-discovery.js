// People are subscribed to through their published feed plans. Prices and access
// always come from settlement; leaderboard returns are never inferred from price.
import {feedTitle} from './flow.js';

export function subscriptionAllocation(feed) {
 const token=feed?.communityToken,bps=Number(token?.buybackBps);
 return token?.vault&&token.address&&Number.isInteger(bps)&&bps>=0&&bps<=10000
  ? {token,buyback:bps/100,creator:(10000-bps)/100}:null;
}
export function subscriptionToken(c,feed) {
 const a=subscriptionAllocation(feed);if(!a)return '';
 const {esc,logo}=c,t=a.token;
 return `<section class="rs-allocation" aria-label="Subscription revenue"><button data-action="creator-token" data-id="${esc(t.address)}">${logo({...t,id:t.address})}<span><b>${esc(t.symbol)}</b><small>Creator’s community token</small></span>${c.icon('chevron')}</button><div class="rs-split"><span>${a.creator}% creator</span><b>${a.buyback}% buyback allocation</b></div><div class="rs-split-bar" aria-hidden="true"><i style="width:${a.buyback}%"></i></div><small>From this subscription. Buybacks execute separately; an allocation is not a completed buyback.</small></section>`;
}

export function socialDiscoveryUI(c) {
 const {S,$,api,esc,icon,avatar,logo,usd,priceHTML,pct,navigate,modal,closeModal,empty,loading}=c;
 let controller,timer,generation=0,offset=null,busy=false;
 const plans=owner=>(S.boot.feeds||[]).filter(f=>f.owner===owner);
 const person=f=>(S.boot.people||[]).find(p=>p.id===f.owner)||{...f.creator,id:f.owner,name:f.creator?.name||'Rally',handle:f.creator?.handle||'rally'};
 const price=f=>Number(f.priceRaw)?f.price+' USDC / '+(f.periodDays||30)+'d':'Free';
 function dispose(){generation++;controller?.abort();clearTimeout(timer);busy=false;}
 function communityHeader(){
  const subscribed=S.boot.feeds.filter(f=>f.subscribed);
  return `<header class="rs-community-head"><div><h1>Community</h1><div class="rs-community-tools"><button class="rs-manage-feeds" data-action="algorithm-picker">Subscriptions${subscribed.length?`<span>${subscribed.length}</span>`:''}</button><button class="r-icon-button" data-action="community-directory" aria-label="Browse communities">${icon('nav-communities')}</button><button class="r-icon-button" data-action="compose" aria-label="Create post">${icon('plus')}</button></div></div><nav class="rs-feed-modes" aria-label="Community feed">${[['for-you','Latest'],['following','Following'],['trades','Trades']].map(([id,label])=>`<button data-action="mode" data-id="${id}" aria-pressed="${S.mode===id}">${label}</button>`).join('')}</nav>${subscribed.length?`<div class="rs-subscribed-strip" aria-label="Subscribed feeds"><button data-action="use-feed" data-id="latest" aria-pressed="${S.boot.activeFeed==='latest'}">All</button>${subscribed.map(f=>`<button data-action="use-feed" data-id="${esc(f.id)}" aria-pressed="${S.boot.activeFeed===f.id}" title="${esc(feedTitle(f))}">${avatar(person(f))}<span>${esc(person(f).name)}</span></button>`).join('')}</div>`:''}</header>`;
 }
 function homeCards(){
  const following=new Set(S.boot.people.filter(p=>p.following).map(p=>p.id));
  const all=S.boot.feeds.filter(f=>f.owner!=='rally');
  const feeds=[...all.filter(f=>following.has(f.owner)||Number(f.priceRaw)&&f.access),...all].filter((f,i,a)=>a.findIndex(x=>x.owner===f.owner)===i).slice(0,8);
  return `<div class="rs-home-people" aria-label="Traders and agents">${feeds.map(f=>{const p=person(f);return `<button class="rs-creator-card" data-action="creator-offers" data-id="${esc(f.owner)}" data-home-owner="${esc(f.owner)}">${avatar(p)}<span><b>${esc(p.name)}</b><small>${esc(feedTitle(f))}</small></span><em data-home-return>${Number(f.priceRaw)&&f.access?'Subscribed':esc(price(f))}</em></button>`;}).join('')||S.boot.people.slice(0,5).map(p=>`<button class="rs-creator-card" data-action="profile" data-id="${esc(p.id)}">${avatar(p)}<span><b>${esc(p.name)}</b><small>${p.kind==='agent'?'Agent':'Trader'}</small></span></button>`).join('')}</div>`;
 }
 async function creatorOffers(owner){
  const list=plans(owner);
  if(list.length===1)return list[0].access?c.openFeed(list[0].id):c.algorithmPreview(list[0].id);
  const p=S.boot.people.find(p=>p.id===owner)||S.leaderCreators?.find(p=>p.author.id===owner)?.author;
  modal(p?esc(p.name):'Subscriptions',`<div class="rs-plan-list">${list.map(f=>`<button data-action="algorithm-preview" data-id="${esc(f.id)}"><span><b>${esc(feedTitle(f))}</b><small>${f.access&&Number(f.priceRaw)?'Subscribed':esc(price(f))}</small></span>${icon('chevron')}</button>`).join('')||'<p class="r-note">No public subscription plans yet.</p>'}</div>`,'rs-plans-modal');
 }
 function tokenRows(list){return list.map(t=>`<article class="rs-token-row"><button class="rs-token-open" data-action="${t.nadfun?'nad-token':'market-detail'}" data-id="${esc(t.id)}" aria-label="Open ${esc(t.symbol)}">${logo(t)}<span><b>${esc(t.symbol)}</b><small>${esc(t.name)}</small></span><span class="rs-token-numbers"><b>${priceHTML(t.price)}</b><small class="${t.change==null?'':Number(t.change)>=0?'positive':'negative'}">${t.stale?'Last known':t.change==null?'—':pct(t.change)}</small></span></button><button class="rs-quick-buy" data-action="${t.nadfun?'nad-token':'trade'}" data-id="${esc(t.id)}" data-order="buy" aria-label="Buy ${esc(t.symbol)}">Buy</button></article>`).join('');}
 async function search(){
  dispose();S.discoverQuery||='';S.tokenSort||='gainers';
  $('#page').innerHTML=`<header class="rs-search-head"><h1>Search</h1><label class="rx-search">${icon('search')}<input id="token-search" type="search" autocomplete="off" placeholder="Token name or address" aria-label="Search tokens" value="${esc(S.discoverQuery)}"><button data-action="token-search-clear" class="r-icon-button" aria-label="Clear search" ${S.discoverQuery?'':'hidden'}>${icon('close')}</button></label><nav class="rs-feed-modes" aria-label="Token order">${[['gainers','24h gainers'],['volume','Volume']].map(([id,label])=>`<button data-action="token-search-sort" data-id="${id}" aria-pressed="${S.tokenSort===id}">${label}</button>`).join('')}</nav></header><div class="rs-search-columns"><span>Token</span><span>Price / 24h</span></div><div id="token-search-results">${loading()}</div><div id="token-search-more"></div>`;
  $('#token-search').addEventListener('input',e=>{S.discoverQuery=e.target.value;$('#page [data-action=token-search-clear]').hidden=!S.discoverQuery;controller?.abort();generation++;clearTimeout(timer);timer=setTimeout(()=>loadTokens(),180);});
  await loadTokens();
 }
 async function loadTokens(append=false){
  const host=$('#token-search-results');if(!host||S.view!=='discover'||append&&(busy||offset==null))return;
  const seq=++generation;controller?.abort();controller=new AbortController();const signal=controller.signal;busy=true;host.setAttribute('aria-busy','true');
  const more=$('#token-search-more');if(more)more.innerHTML='';
  try{
   const params=new URLSearchParams({query:S.discoverQuery||'',scope:'discovery',sort:S.tokenSort||'gainers',limit:40,offset:append?offset:0});
   const d=await api('/api/market-catalog?'+params,undefined,{signal});
   if(signal.aborted||generation!==seq||!host.isConnected)return;
   const map=new Map(S.tokens.map(t=>[t.id,t]));for(const t of d.tokens)map.set(t.id,{...map.get(t.id),...t});S.tokens=[...map.values()];
   if(!append)host.innerHTML=d.tokens.length?tokenRows(d.tokens):empty('No tokens found','Try a name, symbol or contract address.');
   else host.insertAdjacentHTML('beforeend',tokenRows(d.tokens.filter(t=>!host.querySelector(`[data-id="${CSS.escape(t.id)}"]`))));
   offset=d.nextOffset;more.innerHTML=offset!=null?'<button class="r-text-button" data-action="token-search-more">Load more</button>':'';
  }catch(e){if(e.name!=='AbortError'&&seq===generation&&host.isConnected){if(!append)host.innerHTML=empty('Couldn’t load tokens',esc(e.message));more.innerHTML='<button class="r-btn" data-action="token-search-retry">Retry</button>';}}
  finally{if(seq===generation){busy=false;host.removeAttribute('aria-busy');}}
 }
 async function leaderboard(){
  dispose();const seq=generation;S.leaderKind||='all';
  $('#page').innerHTML=`<header class="rs-leader-head"><div><h1>Leaderboard</h1><button class="r-icon-button" data-action="weekly-league" aria-label="Weekly league">${icon('trophy')}</button></div><p>Realized ROI · 30 days</p><nav class="rs-feed-modes" aria-label="Leaderboard creator type">${[['all','Everyone'],['human','People'],['agent','Agents']].map(([id,label])=>`<button data-action="leader-filter" data-id="${id}" aria-pressed="${S.leaderKind===id}">${label}</button>`).join('')}</nav></header><div id="leader-results">${loading()}</div>`;
  controller=new AbortController();const signal=controller.signal;
  try{
   const d=await api('/api/performance/leaderboard?kind='+S.leaderKind,undefined,{signal});if(signal.aborted||seq!==generation)return;
   S.leaderCreators=[...d.entries,...d.unranked];
   const row=(e,ranked)=>{const list=e.algorithms||[],f=list[0],a=e.author,roi=e.performance.roi;
    for(const plan of list)if(plan.owner){const at=S.boot.feeds.findIndex(f=>f.id===plan.id);if(at<0)S.boot.feeds.push(plan);else S.boot.feeds[at]=plan;}
    return `<article class="rs-leader-row"><span class="rs-rank">${ranked?e.rank:'—'}</span><button class="rs-leader-identity" data-action="profile" data-id="${esc(a.id)}">${avatar(a)}<span><b>${esc(a.name)}${a.kind==='agent'?'<em>Agent</em>':''}</b><small>${esc(list.length===1?f.name:list.length+' feeds')}</small></span></button><span class="rs-leader-roi"><b class="${roi==null?'':roi>=0?'positive':'negative'}">${roi==null?'—':pct(roi)}</b><small>${ranked?e.performance.closedTrades+' closed trades':'Not ranked'}</small></span><button class="rs-subscribe" data-action="creator-offers" data-id="${esc(a.id)}">${list.length===1&&f.subscribed?'Open feed':'Subscribe'}<small>${list.length===1?esc(price(f)):'Choose a feed'}</small></button>${a.communityToken?`<button class="rs-leader-token" data-action="creator-token" data-id="${esc(a.communityToken.address)}">${logo({...a.communityToken,id:a.communityToken.address})}<span>${esc(a.communityToken.symbol)}</span>${icon('chevron')}</button>`:''}</article>`;};
   $('#leader-results').innerHTML=(d.entries.length?d.entries.map(e=>row(e,true)).join(''):'<div class="rs-ranking-pending"><b>No verified rankings yet</b><span>Follow a creator below. Closed trades earn a rank.</span></div>')+(d.unranked.length?'<h2 class="rs-section-label">Creators to follow</h2>'+d.unranked.map(e=>row(e,false)).join(''):'')+`<details class="rs-ranking-method"><summary>How rankings work</summary><p>${esc(d.basis)} Missing results are not ranked. Subscription payments unlock the selected feed, not guaranteed returns.</p></details><button class="r-text-button rs-studio-link" data-action="algorithm-market-menu">Create or manage a feed ${icon('chevron')}</button>`;
  }catch(e){if(e.name!=='AbortError'&&seq===generation)$('#leader-results').innerHTML=empty('Rankings unavailable',esc(e.message),'<button class="r-btn" data-action="leader-retry">Retry</button>');}
 }
 async function handle(action,id){
  if(action==='creator-offers'){await creatorOffers(id);return true;}
  if(action==='creator-token'){const t=(S.boot.feeds||[]).map(f=>f.communityToken).concat((S.boot.people||[]).map(p=>p.communityToken)).find(t=>t?.address===id);const nad=t?.venue?.includes('nad.fun');if(!nad&&!S.tokens.some(a=>a.id===id)){const a=t?.asset||await api('/api/market-asset?address='+encodeURIComponent(id));if(String(a.id||a.address).toLowerCase()!==id.toLowerCase())throw Error('Token identity changed');S.tokens.push({...a,id,logoURI:a.logoURI||t?.logoURI,communityToken:!!t});}closeModal();await c.openToken(id,nad);return true;}
  if(action==='token-search-sort'){S.tokenSort=id;document.querySelectorAll('[data-action=token-search-sort]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===id)));await loadTokens();return true;}
  if(action==='token-search-clear'){S.discoverQuery='';$('#token-search').value='';$('#page [data-action=token-search-clear]').hidden=true;await loadTokens();$('#token-search')?.focus();return true;}
  if(action==='token-search-more'||action==='token-search-retry'){await loadTokens(action.endsWith('more'));return true;}
  if(action==='leader-filter'||action==='leader-retry'){if(action==='leader-filter')S.leaderKind=id;await leaderboard();return true;}
  return false;
 }
 return {search,leaderboard,handle,dispose,communityHeader,homeCards};
}
