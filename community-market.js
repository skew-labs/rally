// Community cards share the marketplace's tap-to-open, tap-to-join vocabulary.
import {avatarAsset} from './avatar-identity.js';
export function communityMarketUI({S,$,esc,icon,logo,trade,empty}){
 const count=n=>Number(n||0).toLocaleString('en-US');
 const posts=n=>count(n)+' '+(Number(n)===1?'post':'posts');
 const short=n=>new Intl.NumberFormat('en-US',{maximumSignificantDigits:4,notation:Number(n)>=10000?'compact':'standard'}).format(Number(n));
 const paired=c=>c.token||S.boot.communityToken?.token?.community===c.id&&S.boot.communityToken.token||S.boot.people.find(p=>p.communityToken?.community===c.id)?.communityToken||null;
 const finite=n=>n!=null&&Number.isFinite(Number(n))&&Number(n)>=0;
 function market(c){
  const t=paired(c),asset=S.tokens.find(a=>a.id===t?.address)||t?.asset||{},stats=t?.stats||{};
  if(!t)return {cap:null,price:null,currency:'USD'};
  if(!asset.stale&&Number(asset.fetchedAt)>Date.now()/1000-120&&finite(asset.price))return {cap:finite(asset.marketCap)?Number(asset.marketCap):null,price:Number(asset.price),currency:'USD',at:asset.fetchedAt};
  if(t.stale||Number(t.verifiedAt)<=Date.now()/1000-120)return {cap:null,price:null,currency:'USD'};
  return {cap:finite(stats.referenceMarketCapUSDC)?Number(stats.referenceMarketCapUSDC):null,price:finite(stats.referencePriceUSDC)?Number(stats.referencePriceUSDC):null,currency:'USDC',at:t.verifiedAt};
 }
 function money(n,currency='USD',price=false){
  if(!finite(n))return '—';
  const value=price?new Intl.NumberFormat('en-US',{maximumSignificantDigits:4}).format(Number(n)):short(n);
  return currency==='USD'?'$'+value:value+' USDC';
 }
 function art(c){
  const t=paired(c);
  if(t)return logo({id:t.address,name:t.name,symbol:t.symbol,logoURI:t.logoURI});
  if(c.id==='monad')return logo({id:'mon',name:c.name,symbol:'MON',logoURI:'/assets/MON.png'});
  return `<span class="cx-letter-art r-character-avatar" aria-hidden="true"><img src="${avatarAsset(c.id,'community')}" alt="" width="56" height="56" decoding="async"></span>`;
 }
 function card(c){
  const t=paired(c),m=market(c),joined=c.joined;
  return `<article class="cx-card ${t?'has-token':''}" data-community="${esc(c.id)}"><button class="cx-card-open" data-action="community" data-id="${esc(c.id)}" aria-label="Open ${esc(c.name)}"><span class="cx-card-top">${art(c)}<span class="cx-kind">${t?esc(t.symbol):'Community'}</span></span><h2>${esc(t?t.symbol:c.name)}</h2><span class="cx-card-meta">${t?esc(c.name)+' · ':''}${count(c.members)} ${Number(c.members)===1?'member':'members'}</span><strong class="cx-card-value">${t?money(m.cap,m.currency):count(c.posts24h)}</strong><small class="cx-card-label">${t?'Market cap':'Posts in 24h'}</small><span class="cx-card-activity">${t?posts(c.posts24h)+' in 24h':posts(c.posts)}</span></button><footer class="cx-card-foot"><button class="cx-join ${joined?'is-joined':''}" data-action="${joined?'community':'join'}" data-id="${esc(c.id)}">${joined?'Open':'Join'}</button>${t?`<button class="cx-buy" data-action="community-buy" data-id="${esc(c.id)}" aria-label="Buy ${esc(t.symbol)}">Buy</button>`:''}</footer></article>`;
 }
 function paint(){
  const host=$('#community-market-list');if(!host)return;
  const query=(S.communityQuery||'').trim().toLowerCase(),filter=S.communityFilter||'all',sort=S.communitySort||'active';
  const list=S.boot.communities.filter(c=>(filter!=='joined'||c.joined)&&(filter!=='tokens'||paired(c))&&(c.name+' '+(paired(c)?.symbol||'')).toLowerCase().includes(query));
  list.sort((a,b)=>sort==='members'?Number(b.members)-Number(a.members):Number(b.posts24h||0)-Number(a.posts24h||0)||Number(b.lastPostAt||0)-Number(a.lastPostAt||0)||Number(!!paired(b))-Number(!!paired(a))||Number(b.members)-Number(a.members));
  host.innerHTML=list.length?`<div class="cx-grid">${list.map(card).join('')}</div>`:empty(query?'No matches':filter==='joined'?'No communities joined yet':'No community tokens yet','',`<button class="r-btn" data-action="community-reset">Browse all</button>`);
  document.querySelectorAll('[data-action=cx-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===filter)));
  document.querySelectorAll('[data-action=cx-sort]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===sort)));
 }
 function directory(){
  $('#page').innerHTML=`<header class="cx-head"><h1>Communities</h1><button class="r-icon-button" data-action="cr-community-setup" aria-label="Create community">${icon('plus')}</button></header><div class="cx-controls"><label class="r-algorithm-search">${icon('search')}<input id="community-market-search" type="search" placeholder="Search token or community" aria-label="Search communities" autocomplete="off" value="${esc(S.communityQuery||'')}"></label><div class="cx-toolbar"><div class="cx-filters" role="group" aria-label="Community filter">${[['all','All'],['tokens','Tokens'],['joined','Joined']].map(([id,label])=>`<button data-action="cx-filter" data-id="${id}" aria-pressed="${(S.communityFilter||'all')===id}">${label}</button>`).join('')}</div><div class="cx-sort" role="group" aria-label="Community ranking">${[['active','Active'],['members','Members']].map(([id,label])=>`<button data-action="cx-sort" data-id="${id}" aria-pressed="${(S.communitySort||'active')===id}">${label}</button>`).join('')}</div></div></div><div id="community-market-list"></div>`;
  $('#community-market-search').addEventListener('input',e=>{S.communityQuery=e.target.value;paint();});paint();
 }
 function header(c){
  const t=paired(c),m=market(c),own=Boolean(t&&t.owner===S.boot.me?.id);
  return `<section class="cx-room ${t?'has-token':''}" aria-label="${esc(c.name)} community"><div class="cx-room-identity">${art(c)}<div><span class="cx-room-symbol">${t?esc(t.symbol)+' · Monad':'Community'}</span><h1>${esc(c.name)}</h1><small>${count(c.members)} ${Number(c.members)===1?'member':'members'}<span>·</span>${posts(c.posts24h)} in 24h</small></div><button class="cx-join ${c.joined?'is-joined':''}" data-action="${own?'community-token':'join'}" ${own?'':`data-id="${esc(c.id)}"`}>${own?'Manage':c.joined?'Joined':'Join'}</button></div>${t?`<div class="cx-room-market"><div><small>Market cap</small><strong>${money(m.cap,m.currency)}</strong></div><div><small>Price</small><strong>${money(m.price,m.currency,true)}</strong></div><div class="cx-room-orders"><button class="cx-buy" data-action="cr-token-buy" aria-label="Buy ${esc(t.symbol)}">Buy</button><button class="cx-sell" data-action="cr-token-sell" aria-label="Sell ${esc(t.symbol)}">Sell</button></div></div><div class="cx-room-reference"><span>${m.price==null?'Price unavailable':'Pool reference'+(m.at?' · '+new Date(m.at*1000).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'}):'')}</span>${Number(t.buybackBps)>0?`<button data-action="community-section" data-id="revenue">${Number(t.buybackBps)/100}% sales buyback${icon('chevron')}</button>`:''}</div>`:''}</section>`;
 }
 function refreshPrices(){
  if(S.view==='communities')document.querySelectorAll('.cx-card.has-token').forEach(el=>{const c=S.boot.communities.find(c=>c.id===el.dataset.community);if(c){const m=market(c);el.querySelector('.cx-card-value').textContent=money(m.cap,m.currency);}});
  else if(S.view==='community'){
   const c=S.boot.communities.find(c=>c.id===S.community),host=$('.cx-room-market');if(!c||!host)return;
   const m=market(c),values=host.querySelectorAll('strong');values[0].textContent=money(m.cap,m.currency);values[1].textContent=money(m.price,m.currency,true);
   $('.cx-room-reference>span').textContent=m.price==null?'Price unavailable':'Pool reference'+(m.at?' · '+new Date(m.at*1000).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'}):'');
  }
 }
 async function handle(action,id){
  if(action==='cx-filter'){S.communityFilter=id;paint();return true;}
  if(action==='cx-sort'){S.communitySort=id;paint();return true;}
  if(action==='community-reset'){S.communityQuery='';S.communityFilter='all';directory();return true;}
  if(action==='community-buy'){const community=S.boot.communities.find(c=>c.id===id),t=community&&paired(community);if(t)trade(t.address,null,'buy');return true;}
  return false;
 }
 return {directory,paint,header,handle,refreshPrices};
}
