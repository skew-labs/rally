// Shared navigation, media-first discovery and verified performance surfaces.
// Wallet requests and subscription settlement remain in the existing checkout.
export function experienceUI(c){
 const {S,$,api,esc,icon,avatar,mediaCard,postCard,safeURL,usd,pct,navigate,notify,modal,closeModal,needAccount,empty,loading,motion}=c;
 let generation=0,controller,observer,searchTimer,previewController,loadingMore=false;
 const pages=new Map(),boards=new Map();
 const boardKey=()=>`${S.boot.me?.id||'guest'}|${S.discoverScope||'all'}|${S.discoverQuery||''}`;
 let primed;
 const invalidate=()=>{pages.clear();boards.clear();primed?.controller.abort();primed=null;};
 function prime(){
  if(primed)return;
  const request=new AbortController();
  primed={controller:request,at:Date.now(),promise:api('/api/discover?q=&scope=all',undefined,{signal:request.signal}).catch(()=>null)};
 }
 async function firstPage(params,request){
  const pending=primed;primed=null;
  if(pending){
   const data=await pending.promise;
   if(data&&Date.now()-pending.at<15000&&!request.signal.aborted&&!params.get('cursor')&&!params.get('q')&&params.get('scope')==='all'&&data.viewer===(S.boot.me?.id||null))return data;
  }
  return api('/api/discover?'+params,undefined,{signal:request.signal});
 }
 const homeViews=new Set(['home','explore','launchpad','launch','payments','analytics','swipe','token']);
 const section=()=>S.view==='explore'?'markets':S.view==='swipe'?'swipe':['launchpad','launch','payments','analytics'].includes(S.view)?'launch':S.homeSection||'markets';
 function homeHeader(){
  return `<header class="rx-home-head"><div><h1>Home<span class="rx-brand-dot" aria-hidden="true"></span></h1><div class="rx-head-actions"><button class="r-icon-button" data-nav="notifications" aria-label="Notifications">${icon('bell')}${S.boot?.unread?'<i class="rx-notice-dot"></i>':''}</button><button class="r-icon-button" data-action="search" aria-label="Search Rally">${icon('search')}</button></div></div><nav class="rx-home-tabs" aria-label="Home sections">${[['markets','Markets'],['launch','Launch'],['swipe','Swipe'],['feed','Feed']].map(([id,name])=>`<button data-action="home-section" data-id="${id}" aria-current="${section()===id?'page':'false'}">${name}</button>`).join('')}</nav></header>`;
 }
 function decorateHome(){
  if(!homeViews.has(S.view))return;
  if(!$('#page>.rx-home-head'))$('#page').insertAdjacentHTML('afterbegin',homeHeader());
  motion.sections();
 }
 function enterPage(){
  motion.enterPage();
 }
 function dispose(){generation++;controller?.abort();observer?.disconnect();clearTimeout(searchTimer);loadingMore=false;}
 const rate=p=>p?.roi==null?'—':pct(p.roi);
 const status=p=>p?.roi==null?'No verified returns':'Realized ROI · 30d';
 function tile(item,index=0){
  const f=item.feed,algorithm=item.kind==='algorithm',art=item.cover;
  return `<button class="rx-tile ${art?'has-art':'is-text'} ${item.coverType==='token'?'is-token-art':''} ${algorithm?'is-algorithm':''}" data-action="discover-preview" data-id="${esc(item.id)}" aria-label="${algorithm?'Preview algorithm':'Open post'}: ${esc(item.title.slice(0,100)||item.author.name)}">
   ${art?`<img src="${esc(safeURL(art))}" alt="" width="320" height="320" loading="${index<6?'eager':'lazy'}" decoding="async" onload="this.classList.add('is-loaded')" onerror="this.hidden=true;this.parentElement.classList.add('art-missing')">`:''}
   <span class="rx-tile-fallback" aria-hidden="true">${algorithm?icon('feeds'):avatar(item.author)}<b>${esc(item.title.slice(0,120)||item.author.name)}</b></span>
   ${algorithm||item.kind==='video'?`<span class="rx-tile-type">${icon(algorithm?'feeds':'video')}</span>`:''}
   ${algorithm?`<span class="rx-tile-bottom"><b>${esc(item.title)}</b><span><strong class="${item.performance?.roi>=0&&item.performance?.roi!=null?'positive':item.performance?.roi<0?'negative':''}">${rate(item.performance)}</strong><small>${Number(f.priceRaw)?f.access?'Subscribed':esc(f.price)+' USDC':'Free'}</small></span></span>`:`<span class="rx-tile-author">@${esc(item.author.handle)}</span>`}
  </button>`;
 }
 const skeleton=()=>`<div class="rx-grid rx-grid-skeleton" aria-label="Loading discovery" role="status">${Array.from({length:9},()=>'<div></div>').join('')}</div>`;
 async function discover(){
  const seq=generation;S.discoverQuery||='';S.discoverScope||='all';
  $('#page').innerHTML=`<header class="rx-discover-head"><div><h1>Discover</h1><button class="r-icon-button" data-nav="feeds" aria-label="Manage algorithms">${icon('feeds')}</button></div><label class="rx-search">${icon('search')}<input id="discover-search" type="search" autocomplete="off" placeholder="Search people, posts, algorithms" aria-label="Search discovery" value="${esc(S.discoverQuery)}"><button type="button" data-action="discover-clear" aria-label="Clear search" ${S.discoverQuery?'':'hidden'}>${icon('close')}</button></label><div class="rx-discover-filters" role="group" aria-label="Discovery filter">${[['all','For you'],['algorithms','Algorithms'],['photos','Photos'],['videos','Videos']].map(([id,title])=>`<button data-action="discover-filter" data-id="${id}" aria-pressed="${S.discoverScope===id}">${title}</button>`).join('')}</div></header><div id="discover-content">${skeleton()}</div>`;
  $('#discover-search').addEventListener('input',e=>{S.discoverQuery=e.target.value;const clear=$('[data-action=discover-clear]');if(clear)clear.hidden=!S.discoverQuery;clearTimeout(searchTimer);controller?.abort();searchTimer=setTimeout(()=>load(false,seq),180);});
  const saved=boards.get(boardKey());
  if(saved&&Date.now()-saved.at<30000){
   S.discoverItems=saved.items;S.discoverCursor=saved.cursor;
   $('#discover-content').innerHTML='<div class="rx-grid" id="discover-grid">'+saved.items.map(tile).join('')+'</div><div class="rx-discover-more" id="discover-more">'+(saved.cursor?'<button class="r-text-button" data-action="discover-more">Load more</button>':'<span>You’re all caught up</span>')+'</div>';
   if(saved.cursor){observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)&&!loadingMore&&!document.hidden)load(true,seq);},{rootMargin:'80px'});observer.observe($('#discover-more'));}
  }else await load(false,seq);
 }
 async function load(append=false,seq=generation){
  const host=$('#discover-content');if(!host||seq!==generation||S.view!=='discover'||append&&loadingMore)return;
  if(append&&!S.discoverCursor)return;
  loadingMore=true;controller?.abort();controller=new AbortController();const request=controller;
  const params=new URLSearchParams({q:S.discoverQuery||'',scope:S.discoverScope||'all'});if(append)params.set('cursor',S.discoverCursor);
  const account=S.boot.me?.id||'guest',key=account+'|'+params.toString(),cached=pages.get(key);
  if(!append){observer?.disconnect();host.setAttribute('aria-busy','true');}
  try{
   const d=cached&&Date.now()-cached.at<15000?cached.data:await firstPage(params,request);
   if(request.signal.aborted||seq!==generation||!host.isConnected)return;
   pages.delete(key);pages.set(key,{data:d,at:Date.now()});while(pages.size>20)pages.delete(pages.keys().next().value);
   S.discoverItems=append?[...(S.discoverItems||[]),...d.items.filter(x=>!S.discoverItems.some(y=>y.id===x.id))]:d.items;
   S.discoverCursor=d.cursor;
   boards.delete(boardKey());boards.set(boardKey(),{items:S.discoverItems,cursor:d.cursor,at:Date.now()});while(boards.size>8)boards.delete(boards.keys().next().value);
   if(!append)host.innerHTML=d.items.length?'<div class="rx-grid" id="discover-grid"></div><div class="rx-discover-more" id="discover-more"></div>':empty(S.discoverQuery?'No results':'No discoveries yet',S.discoverQuery?'Try another name or keyword.':'Publish a post or algorithm to get started.','<button class="r-btn" data-action="compose">Create post</button>');
   const grid=$('#discover-grid'),more=$('#discover-more');
   if(grid){const known=new Set([...grid.children].map(x=>x.dataset.id));grid.insertAdjacentHTML('beforeend',d.items.filter(x=>!known.has(x.id)).map((x,i)=>tile(x,(append?grid.children.length:0)+i)).join(''));}
   if(more){more.innerHTML=d.cursor?'<button class="r-text-button" data-action="discover-more">Load more</button>':'<span>You’re all caught up</span>';observer?.disconnect();if(d.cursor){observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)&&!loadingMore&&!document.hidden)load(true,seq);},{rootMargin:'80px'});}}
  }catch(error){if(error.name!=='AbortError'&&seq===generation&&host.isConnected){if(!append)host.innerHTML=empty('Couldn’t load discovery',esc(error.message),'<button class="r-btn" data-action="discover-retry">Retry</button>');else notify(error.message);}}
  finally{if(controller===request){loadingMore=false;host.removeAttribute('aria-busy');const more=$('#discover-more');if(S.discoverCursor&&more&&seq===generation)observer?.observe(more);}}
 }
 async function preview(id){
  previewController?.abort();previewController=new AbortController();const request=previewController;
  modal('Preview',loading(),'rx-preview-modal');
  const instance=S.modal;instance.cleanup=()=>request.abort();
  try{
   const d=await api('/api/discover/preview?id='+encodeURIComponent(id),undefined,{signal:request.signal});
   if(request.signal.aborted||S.modal!==instance)return;
   if(d.kind==='post'){
    S.posts=[...S.posts.filter(p=>p.id!==d.post.id),d.post];
    modal('Post',postCard(d.post),'rx-post-modal');return;
   }
   const f=d.feed,author=S.boot.people.find(p=>p.id===f.owner)||{...d.creator,name:d.creator?.name||f.creator?.name||'Rally',handle:d.creator?.handle||f.creator?.handle||'rally',id:f.owner};
   S.discoveryPreview=d;S.posts=[...S.posts,...d.posts.filter(p=>!S.posts.some(x=>x.id===p.id))];
   const locked=!f.access,art=d.posts[0]?.media;
   const slides=d.posts.map((p,i)=>`<article class="rx-preview-slide" data-preview-slide="${i}" aria-label="Post ${i+1}">${mediaCard(p.media,p.author.name)}<div class="rx-preview-post"><span>${avatar(p.author)}<b>${esc(p.author.name)}</b><small>${p.author.kind==='agent'?'Agent':''}</small></span><p>${esc(p.text).replace(/\n/g,'<br>')}</p><button class="r-text-button" data-action="open-post" data-id="${esc(p.id)}">Open post${icon('chevron')}</button></div></article>`).join('');
   modal(esc(f.name),`<div class="rx-preview-identity"><button data-action="profile" data-id="${esc(f.owner)}">${avatar(author)}<span><b>${esc(author.name)}</b><small>@${esc(author.handle)}</small></span></button><span>${Number(f.priceRaw)?esc(f.price)+' USDC / '+f.periodDays+' days':'Free'}</span></div><div class="rx-preview-performance"><div><small>Realized ROI · 30d</small><strong class="${d.performance.roi>=0&&d.performance.roi!=null?'positive':d.performance.roi<0?'negative':''}">${rate(d.performance)}</strong></div><div><small>Closed trades</small><b>${d.performance.closedTrades}</b></div><button class="r-icon-button" data-action="performance-info" aria-label="How returns are measured">${icon('info')}</button></div><div class="rx-preview-deck" id="preview-deck" tabindex="0" aria-label="Algorithm preview carousel">${slides||'<article class="rx-preview-slide rx-preview-empty"><b>No posts yet</b><p>New posts appear here.</p></article>'}${locked?`<article class="rx-preview-slide rx-preview-locked"><span class="rx-paywall-mark">${icon('feeds')}</span><h3>Keep going</h3><p>Subscribe for the next posts and creator alerts.</p><button class="r-btn primary" data-action="subscribe-feed" data-id="${esc(f.id)}">Subscribe · ${esc(f.price)} USDC</button></article>`:''}</div><div class="rx-preview-navigation"><button class="r-icon-button" data-action="preview-step" data-id="previous" aria-label="Previous slide">${icon('back')}</button><span id="preview-position" aria-live="polite">1 / ${Math.max(1,d.posts.length)+(locked?1:0)}</span><button class="r-icon-button" data-action="preview-step" data-id="next" aria-label="Next slide">${icon('arrow')}</button></div><footer class="rx-preview-footer"><button class="r-btn ${locked?'primary':'subtle'}" data-action="${locked?'subscribe-feed':'use-feed'}" data-id="${esc(f.id)}">${locked?'Subscribe · '+esc(f.price)+' USDC':'Use algorithm'}</button><button class="r-btn subtle" data-action="discover-alert" data-id="${esc(f.id)}" aria-pressed="${d.alerts}" ${locked?'disabled':''}>${icon('bell')}${d.alerts?'Alerts on':'Alerts'}</button></footer>${f.accessExpires?'<small class="rx-access-until">Access until '+new Date(f.accessExpires*1000).toLocaleDateString('en-US')+'</small>':''}`,'rx-preview-modal');
   const deck=$('#preview-deck'),count=Math.max(1,d.posts.length)+(locked?1:0);
   let raf=0;deck.addEventListener('scroll',()=>{if(raf)return;raf=requestAnimationFrame(()=>{raf=0;if(deck.isConnected){const n=Math.min(count-1,Math.max(0,Math.round(deck.scrollLeft/deck.clientWidth)));$('#preview-position').textContent=(n+1)+' / '+count;deck.querySelectorAll('video').forEach((v)=>{if(!v.closest('.rx-preview-slide')?.matches(':nth-child('+(n+1)+')'))v.pause();});}});},{passive:true});
   S.modal.cleanup=()=>{request.abort();cancelAnimationFrame(raf);deck.querySelectorAll('video').forEach(v=>v.pause());};
  }catch(error){if(error.name!=='AbortError'&&S.modal===instance){closeModal();notify(error.message);}}
 }
 function performanceInfo(){
  const d=S.discoveryPreview,p=d?.performance;if(!p)return;
  modal('Verified returns',`<p class="rx-method">${esc(p.basis)}</p><p class="rx-method">Only finalized USDC spot buy/sell pairs recorded in Rally are included. Open positions, perpetuals, quoted prices and feed engagement are excluded.</p>${p.proofs.length?'<div class="rx-proof-list">'+p.proofs.map(tx=>`<a href="https://monadvision.com/tx/${esc(tx)}" target="_blank" rel="noopener noreferrer">${esc(tx.slice(0,10)+'…'+tx.slice(-6))}${icon('external')}</a>`).join('')+'</div>':'<p class="rx-method">No verified closed trades yet.</p>'}${d.feed.owner===S.boot.me?.id?`<div class="rx-sharing"><p class="rx-method">Publishing shows the return and supporting transaction links publicly.</p><button class="r-btn" data-action="discover-performance-sharing" data-id="${esc(d.feed.id)}" aria-pressed="${d.performancePublic}">${d.performancePublic?'Stop publishing returns':'Publish verified returns'}</button></div>`:''}`,'rx-method-modal');
 }
 async function leaderboard(){
  const seq=generation;S.leaderKind||='all';
  $('#page').innerHTML=`<header class="rx-leader-head"><div><h1>Leaderboard</h1><span>Realized ROI · 30d</span></div><button class="r-btn small" data-action="weekly-league">Weekly league</button><div class="rx-leader-filters" role="group" aria-label="Leaderboard creator type">${[['all','Everyone'],['human','People'],['agent','Agents']].map(([id,label])=>`<button data-action="leader-filter" data-id="${id}" aria-pressed="${S.leaderKind===id}">${label}</button>`).join('')}</div></header><div id="leader-results">${loading()}</div>`;
  controller=new AbortController();
  try{
   const d=await api('/api/performance/leaderboard?kind='+S.leaderKind,undefined,{signal:controller.signal});if(seq!==generation||S.view!=='leaderboard')return;
   const row=(e,ranked)=>`<article class="rx-leader-row"><span class="rx-rank">${ranked?e.rank:'—'}</span><button class="rx-leader-person" data-action="profile" data-id="${esc(e.author.id)}">${avatar(e.author)}<span><b>${esc(e.author.name)}${e.author.kind==='agent'?'<em>Agent</em>':''}</b><small>@${esc(e.author.handle)}</small></span></button><button class="rx-leader-algorithm" data-action="${e.algorithms.length>1?'leader-algorithms':'discover-preview'}" data-id="${e.algorithms.length>1?esc(e.author.handle):'feed:'+esc(e.id)}">${e.algorithms.length>1?e.algorithms.length+' algorithms':esc(e.name)}${icon('chevron')}</button><span class="rx-leader-return ${e.performance.roi>=0&&e.performance.roi!=null?'positive':e.performance.roi<0?'negative':''}"><b>${rate(e.performance)}</b><small>${ranked?e.performance.closedTrades+' closed trades':'Unranked'}</small></span></article>`;
   $('#leader-results').innerHTML=(d.entries.length?`<div class="rx-leader-columns"><span>Rank</span><span>Creator</span><span>Algorithm</span><span>Return</span></div>`+d.entries.map(e=>row(e,true)).join(''):`<div class="rx-leader-empty">${icon('trophy')}<h2>No verified rankings yet</h2><p>Rankings start with verified closed trades.</p><button class="r-btn" data-nav="discover">Discover algorithms</button></div>`)+(d.unranked.length?'<section class="rx-unranked"><h2>Not ranked yet</h2>'+d.unranked.map(e=>row(e,false)).join('')+'</section>':'')+`<p class="rx-leader-method">${esc(d.basis)}</p><a class="rx-leader-compare" href="?view=algorithms" data-nav="algorithms">Compare feed quality ${icon('chevron')}</a>`;
  }catch(error){if(error.name!=='AbortError'&&seq===generation)$('#leader-results').innerHTML=empty('Rankings unavailable',esc(error.message),'<button class="r-btn" data-action="leader-retry">Retry</button>');}
 }
 async function handle(action,id,el){
  if(action==='home-section'){
   S.homeSection=id;closeModal();
   await navigate(id==='launch'?'launchpad':id==='swipe'?'swipe':'home');return true;
  }
  if(action==='discover-preview'){await preview(id);return true;}
  if(action==='discover-more'){await load(true);return true;}
  if(action==='discover-filter'){S.discoverScope=id;dispose();await discover();return true;}
  if(action==='discover-retry'){await load(false);return true;}
  if(action==='discover-clear'){S.discoverQuery='';$('#discover-search').value='';el.hidden=true;await load(false);$('#discover-search')?.focus();return true;}
  if(action==='preview-step'){
   const deck=$('#preview-deck');if(deck)deck.scrollBy({left:deck.clientWidth*(id==='next'?1:-1),behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});return true;
  }
  if(action==='performance-info'){performanceInfo();return true;}
  if(action==='discover-alert'){
   await needAccount(async()=>{const d=S.discoveryPreview;if(!d||d.feed.id!==id)return;el.disabled=true;try{const r=await api('/api/discover/alerts',{feed:id,enabled:!d.alerts});if(el.isConnected){d.alerts=r.enabled;el.setAttribute('aria-pressed',String(r.enabled));el.innerHTML=icon('bell')+(r.enabled?'Alerts on':'Alerts');}notify(r.enabled?'Creator alerts enabled':'Creator alerts turned off');}catch(error){notify(error.message);}finally{if(el.isConnected)el.disabled=false;}});return true;
  }
  if(action==='discover-performance-sharing'){
   await needAccount(async()=>{const d=S.discoveryPreview;if(!d||d.feed.id!==id)return;el.disabled=true;try{const r=await api('/api/discover/performance-sharing',{feed:id,enabled:!d.performancePublic});invalidate();notify(r.enabled?'Verified returns published':'Returns are private');await preview('feed:'+id);}catch(error){notify(error.message);if(el.isConnected)el.disabled=false;}});return true;
  }
  if(action==='leader-algorithms'){S.discoverQuery=id;S.discoverScope='algorithms';await navigate('discover');return true;}
  if(action==='leader-filter'){S.leaderKind=id;dispose();await leaderboard();return true;}
  if(action==='leader-retry'){await leaderboard();return true;}
  return false;
 }
 return {homeHeader,decorateHome,enterPage,discover,leaderboard,handle,dispose,invalidate,prime,homeViews,section};
}
