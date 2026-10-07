import { swipeMotion, swipePaging } from './swipe-motion.js';
import { swipeTrade } from './swipe-trade.js';
// Social discovery stays separate from order review and wallet approval.
export function swipeUI(c){
  const {S,$,api,esc,icon,logo,avatar,usd,age,mediaCard,safeURL,token,navigate,notify}=c;
  let generation=0,deadlineTimer,metricsTimer,items=[],active=0,loadingMore=false,request,motion,paging,events,resize,deckHeight=0,busy=false,entryKey=null,layoutFrame=0;
  const cache=new Map(),positions=new Map(),playheads=new Map();
  const quick=swipeTrade({...c,releaseInteraction:()=>{busy=false;}});
  const cacheKey=()=>(S.boot.me?.id||'guest')+':'+S.boot.activeFeed+':'+S.mode+':'+S.boot.watches.join(',');
  const validTab=t=>['spot','perps','prediction'].includes(t)?t:'spot';
  S.swipeTab=validTab(new URLSearchParams(location.search).get('market'));
  const context=p=>p?{post:p.id,feed:S.boot.activeFeed}:null;
  const asset=p=>token(p?.asset)||p?.assetInfo;
  const artwork=(t,eager=false)=>`<span class="r-swipe-token">${logo(t,eager)}</span>`;
  const state=p=>p.state==='settled'?'Settled':p.close>Date.now()/1000?'Open':'Awaiting settlement';
  const eligible=p=>p.close>Date.now()/1000&&p.state!=='settled'&&p.stakeReviewed&&p.predictionReviewed;
  const when=t=>new Date(t*1000).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
  const merge=posts=>{const byID=new Map(S.posts.map((p,i)=>[p.id,i]));for(const p of posts){const index=byID.get(p.id);if(index===undefined){byID.set(p.id,S.posts.length);S.posts.push(p);}else S.posts[index]=p;}};
  const key=(tab=S.swipeTab)=>cacheKey()+':'+tab;
  const remember=()=>{if(items.length)positions.set(key(),active);};
  function save(tab,data){cache.delete(key(tab));cache.set(key(tab),{...data,time:Date.now()});while(cache.size>4)cache.delete(cache.keys().next().value);}
  function dispose(){remember();quick.dispose();generation++;request?.abort();events?.abort();resize?.disconnect();resize=null;motion?.dispose();paging?.dispose();paging=null;cancelAnimationFrame(layoutFrame);layoutFrame=0;document.body.style.removeProperty('--swipe-viewport-height');document.body.removeAttribute('data-swipe-keyboard');clearTimeout(deadlineTimer);clearTimeout(metricsTimer);document.querySelectorAll('.r-swipe-card').forEach(el=>media(el,false));loadingMore=false;}
  const stats=(t,m)=>t.nadfun&&!m?c.nad.metrics(t):`<b>${usd(m?m.mark:t.price)}</b><small>${m?esc(m.priceSource):t.price?'Reference price':'Quote in order'}</small>`;
  async function refreshMetrics(seq){
    if(seq!==generation||S.view!=='swipe'||S.swipeTab!=='spot')return;
    try{
      if(!document.hidden){await Promise.all([c.nad.catalog(),c.nad.catalog('','cap')]);if(seq!==generation||S.view!=='swipe'||S.swipeTab!=='spot')return;
        for(const item of items)if(item.asset){const fresh=token(item.asset.id);if(fresh?.nadfun)item.asset=fresh;}
        document.querySelectorAll('[data-swipe-index]').forEach(el=>{const item=items[Number(el.dataset.swipeIndex)],box=$('[data-swipe-metrics]',el);if(item?.asset&&box)box.innerHTML=stats(item.asset,item.market);});
      }
    }catch{}finally{if(seq===generation&&S.view==='swipe'&&S.swipeTab==='spot')metricsTimer=setTimeout(()=>refreshMetrics(seq),60000);}
  }
  const videoKey=v=>v.dataset.playheadKey||(v.dataset.playheadKey=cacheKey()+':'+v.closest('[data-swipe-post]')?.dataset.swipePost);
  function rememberVideo(v){if(v.readyState<1||!Number.isFinite(v.currentTime))return;const id=videoKey(v);playheads.delete(id);playheads.set(id,v.ended?0:v.currentTime);while(playheads.size>32)playheads.delete(playheads.keys().next().value);}
  function pause(){motion?.cancel();paging?.cancel();document.querySelectorAll('.r-swipe-card video').forEach(v=>{rememberVideo(v);v.pause();});}
  function source(p){const url=p?.source||p?.text.match(/https:\/\/[^\s<>]+/)?.[0];if(!url)return '';const safe=safeURL(url);if(safe==='#')return '';return `<a class="r-swipe-source" href="${esc(safe)}" target="_blank" rel="noopener noreferrer">${icon('link')}${esc(new URL(safe).hostname)}${icon('external')}</a>`;}
  function author(p){return `<div class="r-swipe-author"><button data-action="profile" data-id="${esc(p.author.id)}">${avatar(p.author)}<span><b>${esc(p.author.name)}${p.author.kind==='agent'?'<em>Agent</em>':''}</b><small>@${esc(p.author.handle)} · ${age(p.created)}</small></span></button><button class="r-icon-button" data-action="post-menu" data-id="${esc(p.id)}" aria-label="Post options">${icon('ellipsis')}</button></div>`;}
  function postContent(p,index){
    if(!p)return '';
    return `<div class="r-swipe-caption"><div class="r-swipe-copy" id="swipe-copy-${index}" tabindex="0">${esc(p.text.replace(/(?:^|\n)\s*https:\/\/[^\s<>]+\s*$/, '').trim()).replace(/\n/g,'<br>')}</div><button class="r-swipe-expand" data-action="swipe-expand" data-id="${index}" aria-controls="swipe-copy-${index}" aria-expanded="false" hidden>Read more</button></div>`;
  }
  function actions(item,index){
    const button=(side,label,style)=>`<button class="r-swipe-direction ${style} ${style==='buy'&&hasTicket(item)?'quick-selected':''}" data-action="swipe-order" data-id="${index}" data-side="${side}" aria-label="${label} in this card. Wallet approval required.">${style==='sell'||style==='skip'?icon('back'):''}<span>${label}</span>${style==='buy'?icon('arrow'):''}</button>`;
    if(item.kind==='spot')return item.asset?button('sell','Sell','sell')+button('buy','Buy','buy'):button('skip','Skip','skip')+button('discussion','Discuss','discussion');
    if(item.kind==='perps')return item.market.open?button('short','Short','sell')+button('long','Long','buy'):'<span class="r-swipe-unavailable">Market closed</span>';
    const p=item.pool;
    return button('skip','Skip','skip')+(eligible(p)?button('predict','Predict price','buy'):`<span class="r-swipe-unavailable">${state(p)==='Open'?'Asset review required':state(p)}</span>`);
  }
  function choice(index,direction){
    const item=items[index];if(!item)return null;
    const right=direction==='right';
    if(item.kind==='spot')return item.asset?{side:right?'buy':'sell',label:right?'Buy':'Sell'}:{side:right?'discussion':'skip',label:right?'Discuss':'Skip'};
    if(item.kind==='perps')return item.market.open?{side:right?'long':'short',label:right?'Long':'Short'}:null;
    return right?(eligible(item.pool)?{side:'predict',label:'Predict price'}:null):{side:'skip',label:'Skip'};
  }
  const hasTicket=item=>Boolean(item.asset||item.pool||item.market)&&(item.kind!=='prediction'||eligible(item.pool));
  function ticketPreview(item){
    if(!hasTicket(item))return '';
    const t=item.asset,m=item.market,p=item.pool,perp=item.kind==='perps';
    const unit=item.kind==='spot'?(t.nadfun?t.quoteSymbol||'MON':t.id==='MON'?'USDC':'MON'):perp?(m.venue==='Pingu'?'MON':m.baseSymbol||m.symbol):'USD';
    const field=(label,unit)=>`<div class="r-quick-amount"><span>${label}</span><span class="r-quick-placeholder">0.00</span><b>${esc(unit)}</b></div>`;
    const fields=perp?`<div class="r-quick-perp">${field(m.venue==='Pingu'?'Margin':'Quantity',unit)}${m.venue==='LeverUp'?field('Margin','USDC'):`<div class="r-quick-option">${m.venue==='Drake'?'Margin':'Leverage'}<span class="r-quick-select-preview">${m.venue==='Drake'?'Isolated':'1×'}</span></div>`}</div>`:field(p?'Your price':'Amount',unit)+(p?'':`<div class="r-quick-presets">${(unit==='MON'?[1,5,10]:['USDC','AUSD'].includes(unit)?[5,10,25]:[]).map(n=>`<span>${n}</span>`).join('')}</div>`);
    const extra=p?`<small class="r-quick-stake">Stake ${esc(p.stake)} ${esc(p.stakeAsset)} · ${p.feeBps/100}% fee</small>`:perp?(m.venue==='LeverUp'?'<small class="r-quick-stake">0.5% slippage · Margin settles in LVUSD</small>':'<div class="r-quick-options"><span class="r-quick-protection-preview">Protection price ⌄</span></div>'):'';
    return `<div class="r-swipe-ticket-preview" aria-hidden="true" inert><div class="r-quick-fields">${fields}${extra}</div><div class="r-quick-summary"><div><span>${p?'Prediction':perp?'Size':'Receive'}</span><b>— ${esc(p?'USD':t.symbol)}</b></div><small>&nbsp;</small></div></div>`;
  }
  function card(item,index){
    const p=item.post,t=item.asset,m=item.market,pool=item.pool;
    const visual=p?.media?`<div class="r-swipe-media">${mediaCard(p.media,p.author.name).replace(/<video\b([^>]*?)\bsrc=/,'<video$1data-src=')}</div>`:t&&!p?`<div class="r-swipe-art">${artwork(t,index===active)}<span>${esc(t.symbol)}</span></div>`:'';
    const identity=t?`<div class="r-swipe-market"><div>${artwork(t)}<span><b>${esc(t.symbol)}${m?'<small> Perp</small>':''}</b><small>${esc(m?m.venue+' · '+(m.venue==='LeverUp'?'USDC':'AUSD'):pool?'Castora · Price prediction':t.venue||'Monad · Spot')}</small></span></div><div class="r-swipe-price" data-swipe-metrics>${stats(t,m)}</div></div>`:'';
    const poolInfo=pool?`<div class="r-swipe-pool"><div><span>Pool #${pool.id}</span><b>${esc(state(pool))}</b></div><div><span>Stake</span><b>${esc(pool.stake)} ${esc(pool.stakeAsset)}</b></div><div><span>${state(pool)==='Open'?'Closes':'Snapshot'}</span><time datetime="${new Date((state(pool)==='Open'?pool.close:pool.snapshot)*1000).toISOString()}">${esc(when(state(pool)==='Open'?pool.close:pool.snapshot))}</time></div><small>${pool.feeBps/100}% fee · ${pool.predictions} entries</small></div>`:'';
    return `<article class="r-swipe-card ${p?.media?'has-media':''} ${hasTicket(item)?'has-quick-ticket':''}" data-swipe-index="${index}" data-kind="${item.kind}" ${p?`data-swipe-post="${esc(p.id)}"`:''} aria-label="${esc(p?p.author.name+' post':pool?'Prediction pool '+pool.id:t.symbol+' perpetual')}" aria-roledescription="slide"><div class="r-swipe-intent" aria-hidden="true"></div><div class="r-swipe-content">${p?author(p):''}${visual}${p?postContent(p,index):`<div class="r-swipe-market-heading"><h1>${esc(t?.name||t?.symbol||pool?.asset||'Market')}</h1><p>${m?'Perpetual · Monad':'Price prediction · Monad'}</p></div>`}${poolInfo}<div class="r-swipe-engagement">${p?source(p):''}<div class="r-swipe-social">${p?`<button data-action="swipe-like" data-id="${esc(p.id)}" class="${p.liked?'liked':''}" aria-label="${p.liked?'Unlike':'Like'} post">${icon('heart')}<span>${p.likes||''}</span></button><button data-action="reply" data-id="${esc(p.id)}" aria-label="Reply to post">${icon('chat')}<span>${p.replies||''}</span></button><button data-action="share" data-id="${esc(p.id)}" aria-label="Copy post link">${icon('share')}</button>`:''}</div></div></div><footer>${identity}<div data-swipe-ticket data-kind="${item.kind}">${ticketPreview(item)}</div><div class="r-swipe-directions">${actions(item,index)}</div></footer></article>`;
  }
  function media(el,selected){
    el.querySelectorAll('video').forEach(v=>{
      if(!v.dataset.src&&v.hasAttribute('src'))v.dataset.src=v.getAttribute('src');
      if(selected){if(!v.hasAttribute('src')&&v.dataset.src){
        const id=videoKey(v),restore=()=>{v._swipeRestore=null;const time=playheads.get(id);if(time>0&&Number.isFinite(v.duration))v.currentTime=Math.min(time,Math.max(0,v.duration-.1));};
        v._swipeRestore=restore;v.addEventListener('loadedmetadata',restore,{once:true});v.src=v.dataset.src;
      }}else {rememberVideo(v);v.pause();if(v._swipeRestore){v.removeEventListener('loadedmetadata',v._swipeRestore);v._swipeRestore=null;}if(v.hasAttribute('src')){v.removeAttribute('src');v.load();}}
    });
    el.querySelectorAll('img').forEach(img=>{img.draggable=false;if(selected)img.loading='eager';});
    el.toggleAttribute('data-active',selected);
  }
  function syncMedia(){if(S.view==='swipe')$('#swipe-deck')?.querySelectorAll('[data-swipe-index]').forEach(el=>media(el,Number(el.dataset.swipeIndex)===active));}
  function captions(elements){
    const updates=[];for(const el of elements){const copy=$('.r-swipe-copy',el),button=$('.r-swipe-expand',el);if(copy&&button&&!el.classList.contains('copy-expanded'))updates.push([button,copy.scrollHeight<=copy.clientHeight+1]);}
    for(const [button,hidden] of updates)if(button.hidden!==hidden)button.hidden=hidden;
    for(const el of elements){const content=$('.r-swipe-content',el);if(content){content.classList.toggle('is-scrollable',content.scrollHeight>content.clientHeight+1);readingEdge(content);}}
  }
  function readingEdge(content){const edge=content.scrollTop<=1?'start':content.scrollTop+content.clientHeight>=content.scrollHeight-1?'end':'middle';if(content.dataset.scrollEdge!==edge)content.dataset.scrollEdge=edge;}
  function windowCards(){
    const deck=$('#swipe-deck');if(!deck||!items.length||!deckHeight)return;
    const start=Math.max(0,Math.min(active-2,items.length-5)),end=Math.min(items.length,start+5);
    const existing=new Map([...deck.querySelectorAll('[data-swipe-index]')].map(el=>[Number(el.dataset.swipeIndex),el]));
    for(const [index,el] of existing)if(index<start||index>=end){resize?.unobserve($('.r-swipe-content',el));media(el,false);el.remove();existing.delete(index);}
    const before=$('.r-swipe-spacer.before',deck),after=$('.r-swipe-spacer.after',deck);
    before.style.height=start*deckHeight+'px';after.style.height=(items.length-end)*deckHeight+'px';
    const measured=[];for(let i=start;i<end;i++){
      let el=existing.get(i),added=!el;if(added){const template=document.createElement('template');template.innerHTML=card(items[i],i);el=template.content.firstElementChild;const next=[...deck.querySelectorAll('[data-swipe-index]')].find(n=>Number(n.dataset.swipeIndex)>i)||after;deck.insertBefore(el,next);}
      const height=deckHeight+'px',resized=el.style.height!==height;if(resized){el.style.height=height;el.style.minHeight=height;}
      const label=el.getAttribute('aria-label').replace(/ · \d+ of \d+$/,'')+' · '+(i+1)+' of '+items.length;if(el.getAttribute('aria-label')!==label)el.setAttribute('aria-label',label);
      if(added||el.hasAttribute('data-active')!==(i===active))media(el,i===active);
      el.inert=i!==active&&!paging?.moving();
      // Decode nearby artwork before it enters; keep the five-card DOM bound.
      if(Math.abs(i-active)<=1)el.querySelectorAll('img').forEach(img=>{img.loading='eager';});
      if(added||resized)measured.push(el);
    }
    const selected=$('[data-swipe-index="'+active+'"]',deck);if(selected)quick.mount(items[active],selected,()=>Number(selected.dataset.swipeIndex)===active);
    if(selected&&!measured.includes(selected))measured.push(selected);captions(measured);
    if(resize)for(const el of measured)resize.observe($('.r-swipe-content',el));
    deck.dataset.total=items.length;deck.dataset.windowStart=start;updatePosition();
  }
  function scheduleDeadline(){
    clearTimeout(deadlineTimer);
    const closes=items.filter(x=>x.pool&&state(x.pool)==='Open').map(x=>x.pool.close*1000-Date.now()+1);
    if(!closes.length)return;
    deadlineTimer=setTimeout(()=>{
      if(S.view!=='swipe')return;
      $('#swipe-deck')?.querySelectorAll('[data-swipe-index]').forEach(el=>{
        const index=Number(el.dataset.swipeIndex),item=items[index];if(!item.pool)return;
        $('.r-swipe-directions',el).innerHTML=actions(item,index);
        const pool=item.pool;$('.r-swipe-pool>div:first-child b',el).textContent=state(pool);
        const row=$('.r-swipe-pool',el).children[2];$('span',row).textContent=state(pool)==='Open'?'Closes':'Snapshot';
        const time=$('time',row),date=state(pool)==='Open'?pool.close:pool.snapshot;time.textContent=when(date);time.dateTime=new Date(date*1000).toISOString();
      });scheduleDeadline();
    },Math.max(1,Math.min(2147483647,...closes)));
  }
  function mount(){
    const deck=$('#swipe-deck');if(!deck||!items.length)return;
    deckHeight=deck.clientHeight;deck.innerHTML='<div class="r-swipe-spacer before" aria-hidden="true"></div><div class="r-swipe-spacer after" aria-hidden="true"></div>';
    events=new AbortController();windowCards();deck.scrollTop=active*deckHeight;
    deck.addEventListener('dragstart',e=>e.preventDefault(),{signal:events.signal});
    deck.addEventListener('scroll',e=>{if(e.target.classList?.contains('r-swipe-content'))readingEdge(e.target);},{capture:true,passive:true,signal:events.signal});
    const available=()=>S.view==='swipe'&&!S.modal&&!S.trade&&!busy&&!quick.locked;
    paging=swipePaging({deck,index:()=>active,count:()=>items.length,available:()=>available()&&!motion?.isDragging(),select:index=>{
      if(index!==active){motion?.cancel();active=index;windowCards();remember();}
      if(items.length-active<3&&S.swipeTab==='spot'&&S.swipeCursor)more().catch(()=>{});
    }});
    motion=swipeMotion({deck,choice,commit:(index,side)=>order(index,side,true),paging,available});
    const viewport=()=>{
      const height=window.visualViewport?.height||innerHeight,editing=document.activeElement?.matches('input,textarea,select');
      document.body.style.setProperty('--swipe-viewport-height',height+'px');
      document.body.toggleAttribute('data-swipe-keyboard',Boolean(editing&&innerHeight-height>120));
    };
    const scheduleLayout=()=>{if(layoutFrame)return;layoutFrame=requestAnimationFrame(()=>{
      layoutFrame=0;viewport();const height=deck.clientHeight;
      if(height&&height!==deckHeight){motion.cancel();deckHeight=height;windowCards();paging.cancel();}
      captions([...deck.querySelectorAll('[data-swipe-index]')]);
    });};
    resize=new ResizeObserver(scheduleLayout);resize.observe(deck);deck.querySelectorAll('.r-swipe-content').forEach(el=>resize.observe(el));
    window.visualViewport?.addEventListener('resize',scheduleLayout,{signal:events.signal});
    window.addEventListener('resize',scheduleLayout,{signal:events.signal});
    deck.addEventListener('focusin',scheduleLayout,{signal:events.signal});deck.addEventListener('focusout',scheduleLayout,{signal:events.signal});scheduleLayout();
    const seq=generation;document.fonts.ready.then(()=>{if(seq===generation&&S.view==='swipe')captions([...deck.querySelectorAll('[data-swipe-index]')]);});
    scheduleDeadline();
  }
  function updatePosition(){S.swipePosition={tab:S.swipeTab,feed:S.boot.activeFeed,index:active};const host=$('#swipe-position');if(host)host.textContent=items.length?`${active+1} / ${items.length}${S.swipeTab==='spot'&&S.swipeCursor?' +':''}`:'';const prev=$('[data-action=swipe-prev]'),next=$('[data-action=swipe-next]');if(prev)prev.disabled=active===0;if(next)next.disabled=active>=items.length-1&&!S.swipeCursor;}
  async function more(){
    if(loadingMore||!S.swipeCursor||S.swipeTab!=='spot')return;
    loadingMore=true;const seq=generation,cursor=S.swipeCursor;
    try{const q=postQuery();q.set('cursor',cursor);const d=await api('/api/posts?'+q,undefined,{signal:request.signal});if(seq!==generation||S.view!=='swipe')return;merge(d.posts);const ids=new Set(items.map(x=>x.post?.id));items.push(...d.posts.filter(p=>!ids.has(p.id)).map(p=>({kind:'spot',post:p,asset:asset(p)})));S.swipeCursor=d.cursor;save('spot',{items:[...items],cursor:d.cursor});$('#swipe-more-error')?.remove();windowCards();}
    catch(e){if(e.name!=='AbortError'&&seq===generation&&S.view==='swipe'&&!$('#swipe-more-error'))$('#swipe-status').innerHTML=`<button id="swipe-more-error" data-action="swipe-more">Couldn't load more · Retry</button>`;}
    finally{if(seq===generation)loadingMore=false;}
  }
  function postQuery(){const q=new URLSearchParams({mode:S.mode,feed:S.boot.activeFeed,observe:'0'});if(!S.boot.me)q.set('watch',S.boot.watches.join(','));return q;}
  async function render(refresh=false){
    dispose();request=new AbortController();const seq=generation,tab=S.swipeTab=validTab(S.swipeTab),host=$('#page');
    active=refresh?0:(positions.get(key())??0);items=[];
    if(!$('#swipe-deck'))host.innerHTML=(c.homeHeader?.()||'')+`<section class="r-swipe"><header class="r-swipe-head"><button class="r-icon-button" data-action="swipe-exit" aria-label="Exit swipe mode">${icon('back')}</button><div class="r-swipe-tabs" role="group" aria-label="Swipe market"><span class="r-swipe-tab-pill" aria-hidden="true"></span>${[['spot','Spot'],['perps','Perps'],['prediction','Prediction']].map(([id,name])=>`<button data-action="swipe-tab" data-id="${id}">${name}</button>`).join('')}</div><button class="r-theme-button" data-action="theme" aria-label="Switch theme">${icon(document.documentElement.dataset.theme==='dark'?'sun':'moon')}</button></header><div id="swipe-deck" class="r-swipe-deck" tabindex="0" aria-label="Swipe feed. Up or down for posts. Left or right to choose an order side."></div><div class="r-swipe-progress"><span id="swipe-position" aria-live="polite"></span><span id="swipe-status"></span><button data-action="swipe-refresh" aria-label="Refresh swipe feed">${icon('refresh')}</button></div><div class="r-swipe-step"><button class="r-icon-button previous" data-action="swipe-prev" aria-label="Previous card">${icon('down')}</button><button class="r-icon-button" data-action="swipe-next" aria-label="Next card">${icon('down')}</button></div></section>`;
    const tabs=$('.r-swipe-tabs');tabs.style.setProperty('--tab-index',['spot','perps','prediction'].indexOf(tab));tabs.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===tab)));
    $('#swipe-position').textContent='';$('#swipe-status').textContent=tab==='spot'?S.boot.feeds.find(f=>f.id===S.boot.activeFeed)?.name||'Latest':tab==='perps'?'Monad · Venue prices':'Castora · Price predictions';
    $('#swipe-deck').setAttribute('aria-busy','true');$('[data-action=swipe-refresh]').disabled=true;$('#swipe-deck').innerHTML='<div class="r-swipe-skeleton" role="status" aria-label="Loading feed"><div class="skeleton-author"><i></i><span></span></div><div class="skeleton-art"></div><div class="skeleton-lines"><i></i><i></i><i></i><i></i></div><div class="skeleton-foot"><i></i><i></i></div></div>';
    try{
      const saved=cache.get(key());
      if(!refresh&&saved&&Date.now()-saved.time<(tab==='spot'?60000:30000)){
        items=[...saved.items];S.swipeCursor=saved.cursor;
      }else if(tab==='spot'){
        const d=await api('/api/posts?'+postQuery(),undefined,{signal:request.signal});if(seq!==generation||S.view!=='swipe')return;merge(d.posts);S.swipeCursor=d.cursor;items=d.posts.map(p=>({kind:'spot',post:p,asset:asset(p)}));save(tab,{items:[...items],cursor:d.cursor});
      }else if(tab==='perps'){
        const d=await api('/api/perps',undefined,{signal:request.signal});if(seq!==generation||S.view!=='swipe')return;S.perps=d;S.swipeCursor=null;
        items=d.markets.filter(m=>m.execution==='wallet_transactions').map(m=>({kind:'perps',market:m,asset:c.finance.perplAsset(m),post:m.id===10?S.posts.find(p=>p.asset==='MON'):null}));save(tab,{items:[...items],cursor:null});
      }else{
        const d=!refresh&&S.predictions&&Date.now()/1000-S.predictions.fetchedAt<30?S.predictions:await api('/api/predictions',undefined,{signal:request.signal});if(seq!==generation||S.view!=='swipe')return;S.predictions=d;S.swipeCursor=null;
        items=d.pools.map(pool=>({kind:'prediction',pool,asset:pool.predictionReviewed?token(pool.assetId):{symbol:'?',name:'Unreviewed asset'},post:null}));save(tab,{items:[...items],cursor:null});
      }
      active=Math.min(active,Math.max(0,items.length-1));
      if(items.length){mount();if(tab==='spot')refreshMetrics(seq);}else $('#swipe-deck').innerHTML=`<div class="r-swipe-loading"><b>No ${tab==='spot'?'posts':tab==='perps'?'markets':'pools'} yet</b><button class="r-btn" data-action="swipe-refresh">Refresh</button></div>`;
    }catch(e){if(e.name!=='AbortError'&&seq===generation&&S.view==='swipe')$('#swipe-deck').innerHTML=`<div class="r-swipe-loading"><b>Couldn't load ${tab==='spot'?'feed':'markets'}</b><p>${esc(e.message)}</p><button class="r-btn" data-action="swipe-refresh">Retry</button></div>`;}finally{if(seq===generation&&S.view==='swipe'){$('#swipe-deck').setAttribute('aria-busy','false');$('[data-action=swipe-refresh]').disabled=false;}}
  }
  async function order(index,side,gesture=false){
    const item=items[index];if(!item||busy||S.modal||S.trade||S.view!=='swipe')return;
    if(index!==active||paging?.moving())return;
    if(side==='skip'){await step(1);return;}
    busy=true;pause();
    try{
      if(side==='discussion')await c.openPost(item.post.id);
      else if(item.kind==='spot'&&item.asset&&['buy','sell'].includes(side))await quick.act(side,gesture);
      else if(item.kind==='perps'&&item.market.open&&['long','short'].includes(side))await quick.act(side,gesture);
      else if(item.pool&&side==='predict'){if(!eligible(item.pool)){notify('This pool is no longer open');return;}await quick.act(side,gesture);}
    }catch(e){notify(e.message);}finally{busy=false;}
  }
  function exit(){if(quick.locked)return;if(entryKey&&history.state?.key===entryKey&&S.swipeReturnKey){history.back();return;}navigate(S.swipeReturn||'home');}
  async function step(delta){if(quick.locked)return;const seq=generation;if(active+delta>=items.length&&S.swipeCursor)await more();if(seq===generation)paging?.step(delta);}
  async function handle(action,id,el){
    if(!action.startsWith('swipe-'))return false;
    if(quick.locked&&['swipe-exit','swipe-tab','swipe-refresh','swipe-prev','swipe-next'].includes(action))return true;
    if(action==='swipe-enter'){
      const cards=S.view==='home'?[...document.querySelectorAll('#timeline [data-post]')]:[],byId=new Map(S.posts.map(p=>[p.id,p])),posts=cards.map(el=>byId.get(el.dataset.post)).filter(Boolean);
      const nearest=c.readingAnchor?.()||posts[0]?.id;
      if(posts.length)save('spot',{items:posts.map(p=>({kind:'spot',post:p,asset:asset(p)})),cursor:S.cursor});
      S.swipeReturn=S.view==='explore'?'explore':'home';S.swipeTab=S.view==='explore'?validTab(S.marketTab):'spot';
      positions.set(key(S.swipeTab),Math.max(0,posts.findIndex(p=>p.id===nearest)));S.swipePosition=null;
      S.swipeReturnKey=history.state?.key;await navigate('swipe');entryKey=history.state?.key;
    }
    else if(action==='swipe-exit')exit();
    else if(action==='swipe-tab'){remember();S.swipeTab=validTab(id);items=[];const url=new URL(location.href);url.searchParams.set('market',S.swipeTab);history.replaceState({...history.state},'',url);await render();}
    else if(action==='swipe-refresh'){S.swipePosition=null;await render(true);}
    else if(action==='swipe-more')await more();
    else if(action==='swipe-prev'||action==='swipe-next')await step(action==='swipe-prev'?-1:1);
    else if(action==='swipe-like'){const p=S.posts.find(p=>p.id===id);if(p)await c.needAccount(async()=>{const r=await api('/api/reaction',{post:id,kind:'like',active:!p.liked});Object.assign(p,r);document.querySelectorAll('[data-action=swipe-like]').forEach(b=>{if(b.dataset.id===id){b.classList.toggle('liked',p.liked);b.setAttribute('aria-label',p.liked?'Unlike post':'Like post');$('span',b).textContent=p.likes||'';}});});}
    else if(action==='swipe-expand'){const card=$('[data-swipe-index="'+Number(id)+'"]');if(card){const expanded=el.getAttribute('aria-expanded')!=='true';el.setAttribute('aria-expanded',String(expanded));el.textContent=expanded?'Show less':'Read more';card.classList.toggle('copy-expanded',expanded);captions([card]);}}
    else if(action==='swipe-order')await order(Number(id),el.dataset.side);
    return true;
  }
  document.addEventListener('keydown',e=>{if(e.defaultPrevented||S.view!=='swipe'||S.modal||S.trade||e.altKey||e.ctrlKey||e.metaKey||e.target.closest('input,textarea,select,video,.r-swipe-copy'))return;if(['ArrowDown','PageDown','ArrowUp','PageUp'].includes(e.key)){e.preventDefault();step(['ArrowDown','PageDown'].includes(e.key)?1:-1);}else if(['ArrowLeft','ArrowRight'].includes(e.key)&&!e.target.closest('button,a')){e.preventDefault();const intent=choice(active,e.key==='ArrowLeft'?'left':'right');if(intent)order(active,intent.side,true);}else if(e.key==='Escape')exit();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
  return {render,handle,dispose,pause,syncMedia};
}
