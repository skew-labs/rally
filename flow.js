import {algorithmLibraryUI} from './assets/algorithm-library.js';
import {subscriptionToken} from './social-discovery.js';
import {algorithmRow} from './connected-ui.js';

export function feedPresentation(f) {
  if(f?.research?.wallet)return {icon:'markets',name:(f.research.tokens?.[0]?.symbol||'Public')+' wallet',description:'This wallet’s buys & sells'};
  const research={
    'wallet-reentry':{icon:'feed-watchlist',name:'Repeat buys',description:'Watch wallets buy again'},
    'wallet-confluence':{icon:'markets',name:'Wallet consensus',description:'See what tracked wallets buy together'},
    'wallet-exits':{icon:'feed-custom',name:'Exit watch',description:'Watch tracked wallets sell'}
  };
  if(research[f?.id])return research[f.id];
  const defaults={latest:{icon:'feed-latest',description:'Newest posts first'},community:{icon:'feed-watchlist',description:'Prioritizes your watchlist'},signals:{icon:'feed-popular',description:'Prioritizes engagement'}};
  if(!f?.algorithm_version)return defaults[f?.id]||{icon:'feed-custom',description:'Custom ranking'};
  const formula=String(f.formula||'').replace(/\s+/g,' ').trim();
  const formulas={
    '8 * watched + 3 * following + recency':{icon:'feed-watchlist',description:'Your watchlist & people you follow'},
    '4 * has_asset + 2 * recency + following':{icon:'markets',description:'Token posts & recent updates'},
    '4 * has_media + 2 * following + recency':{icon:'feed-media',description:'Photos, video & people you follow'}
  };
  return formulas[formula]||{icon:'feed-custom',description:'Custom ranking'};
}

export const feedTitle=f=>feedPresentation(f).name||String(f?.name||'Latest').replace(/\s*·\s*v\d+$/,'');
export const feedTerms=f=>Number(f.priceRaw)?f.price+' USDC / '+(f.periodDays||30)+' days':'Free';
export function feedReturn(f){const r=f?.research;return r?.wallet&&r.returnPct!=null&&Number.isFinite(Number(r.returnPct))?Number(r.returnPct):null;}

export function journeyUI(c) {
  const library=algorithmLibraryUI(c);
  const {S,$,api,esc,icon,avatar,token,logo,safeURL,postCard,pageHeader,empty,loading,boot,navigate,notify,modal,closeModal,closeTrade}=c;
  const date=n=>new Date(n*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'});
  const txLink=tx=>tx?`<a class="r-receipt-link" href="https://monadvision.com/tx/${esc(tx)}" target="_blank" rel="noopener noreferrer">Transaction ${icon('external')}</a>`:'';
  const feedAction=(f,compact=false)=>`<button class="r-btn ${compact?'r-feed-use':S.boot.activeFeed===f.id?'subtle':'primary'}" data-action="${f.access?'use-feed':'subscribe-feed'}" data-id="${esc(f.id)}">${S.boot.activeFeed===f.id?compact?'Selected':'Open feed':f.access?compact?'Use':'Use algorithm':compact?'Subscribe':'Subscribe · '+esc(f.price)+' USDC'}</button>`;
  const amount=n=>Number(n).toLocaleString('en-US',{maximumFractionDigits:2});
  const percent=n=>(Number(n)>0?'+':'')+Number(n).toLocaleString('en-US',{maximumFractionDigits:1})+'%';
  const walletName=w=>w.slice(0,6)+'…'+w.slice(-4);
  let walletLimit=4,liveLimit=3;
  const feedPrice=f=>Number(f.priceRaw)?'$'+esc(f.price):'Free';
  const getLabel=f=>S.boot.activeFeed===f.id||f.access&&Number(f.priceRaw)?'Open feed':f.access?f.research?.wallet?'Track wallet':'Open feed':'Subscribe · '+esc(f.price)+' USDC';
  function art(f){const t=f.research?.tokens?.[0];return t?logo({...t,...S.tokens.find(a=>a.id===t.id)},true):`<span class="am-feed-art">${icon(feedPresentation(f).icon)}</span>`;}
  function marketCard(f,index){
    return algorithmRow(c,f,feedTitle(f),feedReturn(f));
  }
  function homeHeading(){
    const f=S.boot.feeds.find(f=>f.id===S.boot.activeFeed)||S.boot.feeds[0];
    return `<button class="r-home-algorithm" data-action="algorithm-picker" aria-haspopup="dialog" aria-label="Change algorithm: ${esc(feedTitle(f))}"><span class="r-home-algorithm-mark">${icon(feedPresentation(f).icon)}</span><span><small>Algorithm</small><b>${esc(feedTitle(f))}</b></span>${icon('down')}</button>`;
  }
  function homeAlgorithms(){
    const all=S.boot.feeds,chosen=all.find(f=>f.id===S.boot.activeFeed),wallets=all.filter(f=>f.research?.wallet).sort((a,b)=>Number(b.research.pnlMON)-Number(a.research.pnlMON)),candidates=[chosen,...wallets,...all.filter(f=>f.algorithm_version)].filter(Boolean);
    const list=candidates.filter((f,i,a)=>a.findIndex(x=>x.id===f.id)===i).slice(0,6);
    return `<section class="r-home-algorithms" aria-label="Algorithm marketplace"><div class="r-home-algorithms-head"><h2>Algorithms</h2><a href="?view=feeds" data-nav="feeds">Explore all${icon('chevron')}</a></div><div class="r-algorithm-shortcuts" role="group" aria-label="Choose your feed algorithm">${list.map(f=>`<button class="r-algorithm-shortcut" data-action="${f.access?'use-feed':'feed-detail'}" data-id="${esc(f.id)}" aria-pressed="${f.id===S.boot.activeFeed}" aria-label="${f.access?'Use':'Preview'} ${esc(f.name)}. ${esc(feedTerms(f))}">${f.research?.wallet?logo(f.research.tokens?.[0]):icon(feedPresentation(f).icon)}<span><b>${esc(f.research?.wallet?walletName(f.research.wallet):feedTitle(f))}</b><small>${esc(f.research?.wallet?percent(feedReturn(f))+' wallet ROI':f.owner==='rally'?feedPresentation(f).description:'@'+(f.creator?.handle||'rally'))}</small></span><span class="r-algorithm-shortcut-state">${f.id===S.boot.activeFeed?icon('check'):esc(Number(f.priceRaw)?f.access?'Subscribed':f.price+' USDC':'Free')}</span></button>`).join('')}</div></section>`;
  }
  function picker(){
    const selected=S.boot.activeFeed;
    modal('Your feeds',`<label class="r-algorithm-search">${icon('search')}<input id="algorithm-picker-search" type="search" placeholder="Find a subscribed feed" aria-label="Search algorithms" autocomplete="off"></label><div id="algorithm-picker-list"></div><a class="r-algorithm-picker-market" href="?view=leaderboard" data-nav="leaderboard">Find creators${icon('chevron')}</a>`,'r-algorithm-picker');
    const input=$('#algorithm-picker-search'),host=$('#algorithm-picker-list');
    const paint=()=>{const q=input.value.trim().toLowerCase(),list=S.boot.feeds.filter(f=>(f.name+' '+f.creator?.handle+' '+feedPresentation(f).description).toLowerCase().includes(q));host.innerHTML=list.map(f=>`<div class="r-algorithm-option"><button data-action="${f.access?'use-feed':'feed-detail'}" data-id="${esc(f.id)}" aria-pressed="${f.id===selected}" aria-label="${f.access?'Use':'Preview'} ${esc(f.name)}. ${esc(feedTerms(f))}"><span class="r-algorithm-option-mark">${icon(feedPresentation(f).icon)}</span><span><b>${esc(feedTitle(f))}</b><small>${esc(feedPresentation(f).description)}</small></span><span class="r-algorithm-option-price">${f.id===selected?icon('check'):esc(feedTerms(f))}</span></button><button class="r-algorithm-option-preview" data-action="feed-detail" data-id="${esc(f.id)}" aria-label="Preview ${esc(f.name)}">${icon('chevron')}</button></div>`).join('')||'<p class="r-algorithm-empty">No algorithms found</p>';};
    input.addEventListener('input',paint);input.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){$('button',host)?.focus();e.preventDefault();}});paint();
  }
  function feedControls(){
    return `<div class="am-controls"><label class="r-algorithm-search">${icon('search')}<input id="algorithm-market-search" type="search" placeholder="Find your next move" aria-label="Search algorithms" autocomplete="off" value="${esc(S.feedQuery||'')}"></label><div class="am-toolbar"><div class="am-filters" role="group" aria-label="Algorithm filter">${[['all','All'],['free','Free'],['paid','Paid'],['yours','Yours']].map(([id,label])=>`<button data-action="feed-filter" data-id="${id}" aria-pressed="${(S.feedFilter||'all')===id}">${label}</button>`).join('')}</div></div></div>`;
  }
  function paintFeeds(){
    const host=$('#algorithm-market-list');if(!host)return;const q=(S.feedQuery||'').trim().toLowerCase(),filter=S.feedFilter||'all';
    const list=S.boot.feeds.filter(f=>(S.view!=='research'||f.owner==='rally')&&(filter!=='yours'||f.owner===S.boot.me?.id)&&(filter!=='free'||!Number(f.priceRaw))&&(filter!=='paid'||Number(f.priceRaw))&&(f.name+' '+feedTitle(f)+' '+f.creator?.handle+' '+feedPresentation(f).description+' '+(f.research?.wallet||'')).toLowerCase().includes(q));
    const wallets=list.filter(f=>f.research?.wallet).sort((a,b)=>S.feedSort==='roi'?(feedReturn(b)??-Infinity)-(feedReturn(a)??-Infinity):Number(b.research.pnlMON)-Number(a.research.pnlMON));
    const live=list.filter(f=>!f.research?.wallet).sort((a,b)=>Number(!!b.research)-Number(!!a.research)||Number(!!b.algorithm_version)-Number(!!a.algorithm_version));
    const groups=[{name:'Top wallets',note:'Sampled closed trades',items:q?wallets:wallets.slice(0,walletLimit)},{name:'Live feeds',items:q?live:live.slice(0,liveLimit)}];
    host.innerHTML=list.length?groups.filter(g=>g.items.length).map(g=>`<section class="am-section" aria-label="${esc(g.name)}"><header class="am-section-head"><div><h2>${g.name}</h2>${g.note?`<p>${g.note}</p>`:''}</div>${g.name==='Top wallets'?`<div class="am-sort" role="group" aria-label="Wallet ranking">${[['pnl','Top PnL'],['roi','Top ROI']].map(([id,label])=>`<button data-action="feed-sort" data-id="${id}" aria-pressed="${(S.feedSort||'pnl')===id}">${label}</button>`).join('')}</div>`:''}</header><div class="am-grid">${g.items.map(marketCard).join('')}</div>${g.name==='Top wallets'?`<div class="am-wallet-more">${!q&&wallets.length>walletLimit?`<button class="am-text" data-action="feed-more-wallets">See all ${wallets.length} wallets ${icon('chevron')}</button>`:''}<button class="am-text" data-action="wallet-research">Evidence ${icon('external')}</button></div>`:g.name==='Live feeds'&&!q&&live.length>liveLimit?`<button class="am-text" data-action="feed-more-live">See all ${live.length} feeds ${icon('chevron')}</button>`:''}</section>`).join(''):q&&!['paid','yours'].includes(filter)?'':empty(q?'No matches':filter==='paid'?'No paid feeds yet':filter==='yours'?'Your algorithms':'No algorithms yet',filter==='yours'&&!S.boot.me?'Sign in to see your feeds.':'',filter==='yours'&&!S.boot.me?'<button class="r-btn" data-action="account">Sign in</button>':q?'<button class="r-btn" data-action="feed-clear-search">Clear search</button>':'<button class="r-btn" data-action="create-feed">Create algorithm</button>');
    document.querySelectorAll('[data-action=feed-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===filter)));
    document.querySelectorAll('[data-action=feed-sort]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===(S.feedSort||'pnl'))));
    library.mount($('#algorithm-strategies'),{query:q,filter});
  }
  function feeds(){
    $('#page').innerHTML=`<header class="am-head"><div><h1>Algorithms</h1></div><button class="am-text" data-action="swipe-algorithms">Swipe</button><button class="r-icon-button" data-action="algorithm-market-menu" aria-label="Algorithm tools">${icon('ellipsis')}</button></header>`+feedControls()+'<div id="algorithm-market-list"></div><section class="al-library am-section" id="algorithm-strategies"></section>';
    $('#algorithm-market-search').addEventListener('input',e=>{S.feedQuery=e.target.value;paintFeeds();});paintFeeds();
  }
  function marketMenu(){modal('Your algorithms',`<div class="r-account-options"><button data-action="create-feed">${icon('plus')}Create a feed${icon('chevron')}</button><button data-action="creator-studio">${icon('feeds')}Creator studio${icon('chevron')}</button><button data-action="research-feeds">${icon('search')}Free strategy research${icon('chevron')}</button><button data-action="activity" data-id="subscriptions">${icon('saved')}Subscriptions${icon('chevron')}</button></div>`);}
  function walletTrades(r){return `<div class="am-trades">${r.trades.map(t=>`<details class="am-trade"><summary><span><b>${esc(t.symbol)}</b><small>${new Date(t.closedAt*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'})} · ${Math.round(t.holdingSeconds/60)} min</small></span><span class="am-trade-result"><b class="positive">${percent(t.returnPct)}</b><small>+${amount(t.pnlMON)} MON</small></span>${icon('chevron')}</summary><div class="am-trade-proof"><p>Buy → sell · finalized</p>${t.transactions.map(txLink).join('')}</div></details>`).join('')}</div>`;}
  function algorithmBody(d,full=false){
    const f=d.feed,r=f.research,roi=feedReturn(f),wallet=!!r?.wallet,verified=d.performance?.state==='verified'&&d.performance.roi!=null;
    const stats=wallet?`<div class="am-performance"><small>Realized PnL · sampled trades</small><strong class="positive">+${amount(r.pnlMON)}<span>MON</span></strong><div><span><b class="positive">${percent(roi)}</b><small>Closed-trade ROI</small></span><span><b>${r.roundTrips}</b><small>Closed ${r.roundTrips===1?'trade':'trades'}</small></span><span><b>${new Date(r.closedAt*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'})}</b><small>Last close</small></span></div></div>`:verified?`<div class="am-performance"><small>Creator’s closed-trade ROI · 30d</small><strong class="${d.performance.roi>=0?'positive':'negative'}">${percent(d.performance.roi)}</strong><div><span><b>${d.performance.closedTrades}</b><small>Closed trades</small></span></div></div>`:'';
    const note=r?r.stale?'Activity update delayed':r.activeAssets?'Recent wallet activity':'No new wallet activity · recent posts shown':'';
    return `<div class="am-preview-scroll"><div class="am-preview-identity">${avatar(d.creator||S.boot.people.find(p=>p.id===f.owner)||{...f.creator,id:f.owner})}<span><b>${esc(wallet?feedTitle(f):d.creator?.name||f.creator?.name||feedTitle(f))}</b><small>${wallet?esc(walletName(r.wallet))+' · Rally feed':esc(feedTitle(f))+' · @'+esc(f.creator?.handle||'rally')}</small></span></div>${stats}${subscriptionToken(c,f)}${note?`<p class="am-activity-note">${esc(note)}</p>`:''}${wallet?`<div class="am-detail-heading"><h3>Closed trades</h3><a href="https://nad.fun/profile/${esc(r.wallet)}" target="_blank" rel="noopener noreferrer">Wallet${icon('external')}</a></div>${walletTrades(r)}`:`<p class="am-preview-description">${esc(feedPresentation(f).description)}</p>`}<div class="am-detail-heading"><h3>Feed preview</h3>${full?'':`<button class="am-text" data-action="feed-detail" data-id="${esc(f.id)}">View feed${icon('chevron')}</button>`}</div>${d.loading?loading():d.posts.slice(0,full?6:2).map(p=>`<button class="am-post-preview" data-action="open-post" data-id="${esc(p.id)}"><span>${avatar(p.author)}<b>${esc(p.author.name)}</b><small>${c.age(p.created)}</small></span><p>${esc(p.text.slice(0,200))}${p.text.length>200?'…':''}</p></button>`).join('')||'<p class="am-activity-note">No posts yet.</p>'}<details class="am-about"><summary>About this feed${icon('down')}</summary><p>${wallet?'Ranks posts about tokens this public wallet buys or sells. Published by Rally; the wallet owner has not endorsed this feed.':esc(feedPresentation(f).description)}</p>${r?`<p>Shown returns belong to sampled wallet trades, not this algorithm. Matched swap gas is included; other transaction costs are excluded.</p><p>${r.stale?'Last data': 'Data checked'} ${new Date((r.evidenceAsOf||r.asOf)*1000).toLocaleString()}</p><button class="am-text" data-action="wallet-research">Full evidence & coverage${icon('chevron')}</button>`:''}${f.formula?`<details><summary>Ranking formula</summary><pre class="r-code">${esc(f.formula)}</pre></details>`:''}${Number(f.priceRaw)?`<p>${esc(f.price)} USDC for ${f.periodDays} days. Manual renewal.</p>`:''}</details></div><footer class="am-preview-foot"><span><b>${feedPrice(f)}</b><small>${Number(f.priceRaw)?f.periodDays+' days · manual renewal':'No payment needed'}</small></span><button class="r-btn primary" data-action="${f.access?'use-feed':'subscribe-feed'}" data-id="${esc(f.id)}" ${d.loading?'disabled aria-busy="true"':''}>${getLabel(f)}</button></footer>`;
  }
  async function preview(id){
    const controller=new AbortController(),cached=S.boot.feeds.find(f=>f.id===id);modal(cached?esc(feedTitle(cached)):'Algorithm',cached?algorithmBody({feed:cached,posts:[],loading:true}):loading(),'am-preview-modal');const instance=S.modal;instance.cleanup=()=>controller.abort();
    try{const d=await api('/api/discover/preview?id='+encodeURIComponent('feed:'+id),undefined,{signal:controller.signal});if(S.modal!==instance||controller.signal.aborted)return;
      S.algorithmPreview=d;S.posts=[...S.posts,...d.posts.filter(p=>!S.posts.some(x=>x.id===p.id))];modal(esc(feedTitle(d.feed)),algorithmBody(d),'am-preview-modal');
    }catch(e){if(e.name!=='AbortError'&&S.modal===instance){closeModal();notify(e.message);}}
  }
  async function walletResearch(){
    modal('Public wallet research','<div id="wallet-research-body">'+loading()+'</div>','r-wide-modal');
    const body=$('#wallet-research-body');
    try{
      const d=await api('/api/wallet-research');if(!body?.isConnected)return;
      body.innerHTML=`<p class="r-note">${d.stale?'Last snapshot · ':''}${d.asOf?new Date(d.asOf*1000).toLocaleString():'Collecting data'} · ${d.markets.length} sampled markets</p><p class="r-note">Closed round trips after matched swap gas. Sampled markets, not a global ranking.</p><div class="r-wallet-research-list">${d.wallets.map(w=>`<article class="r-wallet-research-row"><div><a href="https://nad.fun/profile/${esc(w.wallet)}" target="_blank" rel="noopener noreferrer">${esc(w.wallet.slice(0,6)+'…'+w.wallet.slice(-4))}${icon('external')}</a><small>${w.roundTrips} closed round trip${w.roundTrips===1?'':'s'}</small></div><b>+${Number(w.pnlMON).toLocaleString('en-US',{maximumFractionDigits:2})} MON</b><div class="r-wallet-research-proofs">${w.trades.map(t=>`<details><summary>${esc(t.symbol)} · ${Math.round(t.holdingSeconds/60)} min</summary>${t.transactions.map(txLink).join('')}</details>`).join('')}</div></article>`).join('')||'<p class="r-note">No verified profitable round trips yet.</p>'}</div><details class="r-feed-ranking"><summary>Method & coverage</summary><p class="r-note">${esc(d.method)}</p><p class="r-note">${esc(d.scope)}</p><p class="r-note">${esc(d.selection||'')}</p><a class="r-text-button" href="https://github.com/skew-labs/rally/blob/main/docs/public-wallet-algorithms.md" target="_blank" rel="noopener noreferrer">Methodology${icon('external')}</a></details>`;
    }catch(e){if(body?.isConnected)body.textContent=e.message;}
  }
  async function feedDetail(){
    const id=S.feed;$('#page').innerHTML=pageHeader('Algorithm',`<button class="r-text-button" data-nav="feeds">All algorithms</button>`)+loading();
    try{
      const query=new URLSearchParams({id});if(!S.boot.me)query.set('watch',S.boot.watches.join(','));
      const d=await api('/api/feed?'+query);if(S.view!=='feed'||S.feed!==id)return;
      S.feedPreview=d;S.previewMode='ranked';S.posts=[...d.posts,...d.latest].filter((p,i,a)=>a.findIndex(x=>x.id===p.id)===i);
      const f=d.feed;
      if(f.research?.wallet){$('#page').innerHTML=pageHeader('Algorithm',`<button class="r-text-button" data-nav="feeds">All algorithms</button>`)+`<section class="am-detail-page">${algorithmBody(d,true)}</section>`;return;}
      $('#page').innerHTML=pageHeader('Algorithm',`<button class="r-text-button" data-nav="feeds">All algorithms</button>`)+`<section class="r-feed-detail"><div class="r-feed-detail-title"><div class="r-feed-icon">${icon(feedPresentation(f).icon)}</div><div><h2>${esc(feedTitle(f))}</h2><button class="r-feed-creator" data-action="profile" data-id="${esc(f.owner)}">@${esc(f.creator?.handle||'rally')}</button></div><button class="r-icon-button" data-action="copy-feed" data-id="${esc(f.id)}" aria-label="Copy feed link">${icon('share')}</button></div><p class="r-feed-detail-description">${esc(feedPresentation(f).description)}</p><div class="r-feed-price"><b>${Number(f.priceRaw)?'$'+esc(f.price):'Free'}</b><span>${Number(f.priceRaw)?esc(f.periodDays||30)+' days · Manual renewal':'Use anytime'}</span></div>${f.algorithm_version&&f.formula?`<details class="r-feed-ranking"><summary>Ranking</summary><pre class="r-code r-codex-command">${esc(f.formula)}</pre></details>`:f.weights?`<details class="r-feed-ranking"><summary>Ranking</summary><div class="r-ranking-legend">${f.weights.map((w,i)=>`<span>${['Recency','Watchlist','Engagement'][i]} <b>${w}</b></span>`).join('')}</div></details>`:''}<div class="r-feed-detail-actions">${feedAction(f)}<button class="r-text-button" data-action="benefits-open" data-id="${esc(f.owner)}">Token benefits${f.holderDiscountBps?' · '+f.holderDiscountBps/100+'% off':''}</button>${f.accessExpires?`<span>Access until ${date(f.accessExpires)}</span><button class="r-text-button" data-action="subscribe-feed" data-id="${esc(f.id)}">Renew</button>`:Number(f.priceRaw)?`<span>${f.creatorShareBps/100}% creator${f.communityToken?' · '+f.communityToken.buybackBps/100+'% buyback':''}</span>`:''}</div></section><div class="r-preview-head"><h2>Preview</h2><span>${d.posts.length} posts${!f.access?' · Limited preview':''}</span></div><div class="r-tabs"><button class="active" data-action="preview-mode" data-id="ranked">This feed</button><button data-action="preview-mode" data-id="latest">Latest</button></div><div id="feed-preview-posts"></div>`;
      if(f.id.startsWith('wallet-')){
        const b=document.createElement('button');b.className='r-text-button';b.dataset.action='wallet-research';b.textContent='Wallet research';$('.r-feed-detail-actions').append(b);
        const note=document.createElement('p');note.className='r-note';note.textContent=!f.research?.asOf?'Collecting wallet activity':f.research.stale?'Activity update delayed · recent posts shown':!f.research.activeAssets?'No new wallet activity · recent posts shown':'Recent wallet activity';$('.r-feed-detail').append(note);
      }
      paintPreview();
    }catch(e){if(S.view==='feed'&&S.feed===id)$('#page').innerHTML=pageHeader('Algorithm')+empty('Algorithm unavailable',esc(e.message),'<button class="r-btn" data-nav="feeds">All algorithms</button>');}
  }
  function paintPreview(){const d=S.feedPreview,host=$('#feed-preview-posts');if(!d||!host)return;const posts=S.previewMode==='latest'?d.latest:d.posts;host.innerHTML=posts.map(postCard).join('')||empty('No posts yet','New posts will appear here.');}
  async function postDetail(){
    const id=S.post;$('#page').innerHTML=pageHeader('Post',`<button class="r-text-button" data-nav="home">Home</button>`)+loading();
    try{const [post,replies]=await Promise.all([api('/api/post?id='+encodeURIComponent(id)),api('/api/replies?post='+encodeURIComponent(id))]);if(S.view!=='post'||S.post!==id)return;S.posts=[post,...replies.posts];$('#page').innerHTML=pageHeader('Post',`<button class="r-text-button" data-nav="home">Home</button>`)+postCard(post)+`<div class="r-subhead"><h2>Replies</h2><button class="r-btn small" data-action="compose-reply" data-id="${esc(id)}">Reply</button></div>`+replies.posts.map(postCard).join('');}
    catch(e){if(S.view==='post'&&S.post===id)$('#page').innerHTML=pageHeader('Post')+empty('Post unavailable',esc(e.message),'<button class="r-btn" data-nav="home">Home</button>');}
  }
  async function connections(){
    const host=$('#connection-status');if(!host||!S.boot.me)return;
    const result=await api('/api/connections/status');if(!host.isConnected)return;
    host.innerHTML=result.connections.map(g=>`<div class="r-connection">${avatar(g.profile)}<span class="r-connection-info"><b>${esc(g.profile.name)}</b><small>${g.revoked?'Revoked':g.expires<Date.now()/1000?'Expired':g.lastPost?'Latest post '+c.age(g.lastPost.created):g.last_used?'Connected · No posts yet':'Waiting for first request'}</small></span><span class="r-pill r-connection-state ${!g.revoked&&g.expires>Date.now()/1000&&g.lastPost?'good':''}">${g.revoked?'Revoked':g.expires<Date.now()/1000?'Expired':g.lastPost?'Published':g.last_used?'Connected':'Ready'}</span>${g.lastPost?`<button class="r-btn small r-connection-post" data-action="open-post" data-id="${esc(g.lastPost.id)}">View post</button>`:''}${!g.revoked?`<button class="r-icon-button r-connection-revoke" data-action="revoke" data-id="${esc(g.id)}" aria-label="Revoke ${esc(g.profile.name)}">${icon('close')}</button>`:''}</div>`).join('')||'<p class="r-muted">No connections yet.</p>';
  }
  const chainLabel=state=>({submitted:'Submitted',confirmed:'Confirming',finalized:'Finalized',failed:'Failed',invalid:'Could not verify',awaiting_payment:'Awaiting payment',expired:'Expired',paid:'Paid'}[state]||state);
  function entryCard(e){
    let title,detail,status=chainLabel(e.state),action='';
    if(e.kind==='payment'){
      title=e.feedName;detail=e.amount+' USDC · 30 days';
      if(e.state==='paid')action=`<button class="r-btn small" data-action="use-feed" data-id="${esc(e.feed)}">Open feed</button>`;
      else if(['awaiting_payment','expired'].includes(e.state))action=`<button class="r-btn small" data-action="resume-payment" data-id="${esc(e.id)}">Review</button>`;
      if(e.state==='paid'&&e.accessExpires)detail+=' · Until '+date(e.accessExpires);
    }else if(e.kind==='community'){
      title=e.action==='launch'?'Launch '+e.summary.symbol:'Update '+e.summary.symbol+' allocation';
      detail='PancakeSwap V2 · '+(e.action==='launch'?e.summary.seedUSDC+' USDC pool':e.summary.buybackBps/100+'% buyback');
      if(e.state==='finalized'){status=e.action==='launch'?'Active':'Updated';action='<button class="r-btn small" data-action="community-token">Open token</button>';}
    }else if(e.kind==='approval'){
      title='Approve '+(token(e.summary.input)?.symbol||'Token');detail=e.venue+' · '+e.summary.amount+' '+(token(e.summary.input)?.symbol||'');
      if(e.state==='finalized'){status='Approved';detail+=' · Allowance only';}
    }else if(e.kind==='spot'){
      title=(token(e.summary.input)?.symbol||'Token')+' → '+(token(e.summary.output)?.symbol||'Token');detail=e.venue+' · '+e.summary.amount+' '+(token(e.summary.input)?.symbol||'');
      if(e.state==='finalized'){
        detail+=' · Check wallet balances';
        const purchase=S.activity.entries.find(x=>x.kind==='payment'&&x.feed===e.context?.feed&&x.state==='awaiting_payment');
        if(purchase)action=`<button class="r-btn small" data-action="resume-payment" data-id="${esc(purchase.id)}">Review subscription</button>`;
        else action='<button class="r-btn small" data-nav="portfolio">View balances</button>';
      }
    }else{
      const p=e.summary,outcome=e.outcome;
      title=p.market?p.market+' perpetual':p.action==='predict'?'Pool #'+p.pool:p.action==='claim'?'Prediction winnings':p.action==='deposit'?'Perpl deposit':'Perpl withdrawal';
      detail=e.venue==='perpl'?'Perpl':'Castora';
      if(p.quantity)detail+=' · '+p.quantity+' · '+(p.reduceOnly?'Reduce only':p.direction==='short'?'Short':'Long');
      if(p.amount)detail+=' · '+p.amount+' '+p.asset;
      if(p.action==='deposit'&&e.state==='finalized'&&e.outcome?.businessState==='collateral_deposit'){
        const market=S.perps?.markets.find(m=>m.symbol===token(e.context?.asset)?.symbol&&m.open);
        if(market)action=`<button class="r-btn small" data-action="continue-perpl" data-id="${market.id}" data-source="${esc(e.context.post)}">Trade ${esc(market.symbol)}</button>`;
      }
      if(outcome?.businessState){const business={filled:'Filled',partial_fill:'Partially filled',unfilled:'Unfilled',venue_result_pending:'Fill unverified',collateral_deposit:'Collateral deposited',collateral_withdraw:'Collateral withdrawn',prediction_entered:'Prediction entered',winnings_claimed:'Winnings claimed'}[outcome.businessState];if(business)status=business+' · '+chainLabel(e.state);}
      if(outcome?.fillQuantity)detail+=' · Filled '+outcome.fillQuantity+' @ $'+outcome.entryPrice+' · Fee '+outcome.feeAUSD+' AUSD';
      if(e.venue==='nadfun'){
        title=p.action==='create'?'Launch '+p.asset:(p.action==='buy'?'Buy ':'Sell ')+p.asset;
        detail='nad.fun · '+(p.action==='create'?p.amount+' MON launch fee':p.amount+' '+p.inputAsset+' · '+(p.phase==='dex'?'DEX':'Bonding curve'));
        const business={swap_delivered:'Delivered',token_created:'Token created',venue_result_pending:'Result unverified',reverted:'Reverted'}[outcome?.businessState];
        if(business)status=business+' · '+chainLabel(outcome?.chainState||e.state);
        if(outcome?.received)detail+=' · Received '+outcome.received+' '+outcome.receivedAsset;
        if(outcome?.businessState==='token_created'||outcome?.businessState==='swap_delivered')action=`<button class="r-btn small" data-action="nad-token" data-id="${esc(p.token)}">${p.action==='create'?'Open token':'Trade again'}</button><button class="r-text-button" data-nav="portfolio">Balances</button>`;
      }
    }
    const source=e.context?.post?`<button class="r-activity-source" data-action="open-post" data-id="${esc(e.context.post)}">${icon('feed')}<span>@${esc(e.context.author?.handle)} · ${esc(e.context.text)}</span>${icon('chevron')}</button>`:'';
    return `<article class="r-activity-entry" data-activity="${esc(e.id)}"><div class="r-activity-entry-head"><span><b>${esc(title)}</b><small>${esc(detail)}</small></span><span class="r-pill ${['paid','finalized'].includes(e.state)&&(e.venue!=='nadfun'||['token_created','swap_delivered'].includes(e.outcome?.businessState))?'good':''}">${esc(status)}</span></div>${source}<div class="r-activity-entry-foot"><span>${date(e.created)}</span>${txLink(e.tx)}${action}</div></article>`;
  }
  function paintActivity(){
    const d=S.activity,tab=S.activityTab||'all';
    const entries=d.entries.filter(e=>tab==='all'||tab==='trades'&&e.kind!=='payment'||tab==='subscriptions'&&e.kind==='payment');
    const recovery=c.finance.pending().filter(e=>e.user===S.boot.me?.id);
    $('#page').innerHTML=pageHeader('Activity',`<button class="r-btn small" data-action="share-fill">Share a trade</button><button class="r-btn small" data-action="refresh-activity">${icon('repeat-2')}Refresh</button>`)+`<div class="r-tabs">${[['all','All'],['trades','Trades'],['subscriptions','Subscriptions'],['earnings','Earnings']].map(([id,title])=>`<button data-action="activity-tab" data-id="${id}" class="${tab===id?'active':''}">${title}</button>`).join('')}</div>${d.refreshIncomplete.length?'<p class="r-note">Some confirmations could not be refreshed. Your submitted transactions are saved.</p>':''}${recovery.length?`<div class="r-recovery-notice"><b>Recording pending</b><p>${recovery.length} submitted transaction${recovery.length===1?'':'s'}. Refresh to record the same hash.</p>${recovery.map(e=>txLink(e.tx)).join('')}</div>`:''}<div class="r-activity-list">${tab==='earnings'?d.payouts.map(p=>`<article class="r-activity-entry"><div class="r-activity-entry-head"><span><b>${esc(p.amount)} USDC received</b><small>${esc(p.feedName)}</small></span><span class="r-pill good">Finalized</span></div><div class="r-activity-entry-foot"><span>${date(p.settled)}</span>${txLink(p.tx)}<button class="r-text-button" data-action="feed-detail" data-id="${esc(p.feed)}">View feed</button></div></article>`).join('')||empty('No earnings yet','Payments appear here after finality.','<button class="r-btn" data-nav="feeds">Your feeds</button>'):entries.map(entryCard).join('')||empty(tab==='subscriptions'?'No subscriptions yet':'No activity yet',tab==='subscriptions'?'Preview a feed before subscribing.':'Your submitted trades and feed payments appear here.',`<button class="r-btn" data-nav="${tab==='subscriptions'?'feeds':'explore'}">${tab==='subscriptions'?'Browse feeds':'Explore markets'}</button>`)}</div>`;
  }
  async function activity(){
    const viewer=S.boot.me?.id;
    if(!viewer){$('#page').innerHTML=pageHeader('Activity','<button class="r-btn small" data-action="share-fill">Share a trade</button>')+empty('Sign in to view activity','Trades, subscriptions and creator payments.','<button class="r-btn primary" data-action="account">Sign in</button>');return;}
    if(!S.activity)$('#page').innerHTML=pageHeader('Activity','<button class="r-btn small" data-action="share-fill">Share a trade</button>')+loading();
    try{await c.finance.resume();const d=await api('/api/activity');if(S.view!=='activity'||S.boot.me?.id!==viewer)return;S.activity=d;
      let intent;try{intent=JSON.parse(localStorage.getItem('rally:subscription-intent')||'null');}catch{}
      const subscribed=d.entries.find(e=>e.kind==='payment'&&e.state==='paid'&&e.id===intent?.id&&intent.user===viewer);
      if(subscribed){await api('/api/feeds/use',{id:subscribed.feed});localStorage.removeItem('rally:subscription-intent');notify('Subscribed. Your feed is ready.');}
      await boot();paintActivity();}
    catch(e){if(S.view==='activity')$('#page').innerHTML=pageHeader('Activity','<button class="r-btn small" data-action="share-fill">Share a trade</button>')+empty('Activity unavailable',esc(e.message),'<button class="r-btn" data-action="refresh-activity">Retry</button>');}
  }
  async function openActivity(tab){closeModal();closeTrade();S.activityTab=tab||'all';S.activity=null;await navigate('activity');}
  function origin(el){const id=el?.closest('[data-post]')?.dataset.post;const post=S.posts.find(p=>p.id===id);return post?{post:post.id,feed:S.view==='feed'?S.feed:S.boot.activeFeed}:null;}
  function originCard(context){const post=S.posts.find(p=>p.id===context?.post);if(post)return `<button class="r-trade-context" data-action="open-post" data-id="${esc(post.id)}">${avatar(post.author)}<span><b>@${esc(post.author.handle)}</b><small>${esc(post.text.slice(0,100))}</small></span>${icon('chevron')}</button>`;const feed=S.boot.feeds.find(f=>f.id===context?.feed);return feed?`<button class="r-trade-context" data-action="feed-detail" data-id="${esc(feed.id)}"><div class="r-feed-icon">${icon(feedPresentation(feed).icon)}</div><span><b>${esc(feed.name)}</b><small>@${esc(feed.creator?.handle)}</small></span>${icon('chevron')}</button>`:'';}
  async function handle(action,id,el){
    if(await library.handle(action,id))return true;
    if(action==='algorithm-tab'){S.algorithmTools=false;S.algorithmsTab='market';await navigate(S.view==='algorithms'?'algorithms':'feeds');return true;}
    if(action==='feed-detail'){closeModal();S.feed=id;await navigate('feed');}
    else if(action==='algorithm-preview'){await preview(id);}
    else if(action==='algorithm-market-menu'){marketMenu();}
    else if(action==='creator-studio'){closeModal();S.algorithmTools=true;await navigate('algorithms');}
    else if(action==='wallet-research'){await walletResearch();}
    else if(action==='research-feeds'){closeModal();S.feedFilter='free';S.feedQuery='';await navigate('research');}
    else if(action==='algorithm-picker'){picker();}
    else if(action==='feed-filter'){S.feedFilter=id;paintFeeds();}
    else if(action==='feed-sort'){S.feedSort=id;paintFeeds();}
    else if(action==='feed-more-wallets'){walletLimit=S.boot.feeds.length;paintFeeds();}
    else if(action==='feed-more-live'){liveLimit=S.boot.feeds.length;paintFeeds();}
    else if(action==='feed-clear-search'){S.feedQuery='';$('#algorithm-market-search').value='';paintFeeds();$('#algorithm-market-search').focus();}
    else if(action==='preview-mode'){S.previewMode=id;document.querySelectorAll('[data-action="preview-mode"]').forEach(b=>b.classList.toggle('active',b.dataset.id===id));paintPreview();}
    else if(action==='copy-feed'){await navigator.clipboard.writeText(location.origin+'/?view=feed&id='+encodeURIComponent(id));notify('Algorithm link copied');}
    else if(action==='open-post'){closeModal();closeTrade();S.post=id;await navigate('post');}
    else if(action==='activity'){await openActivity(id);}
    else if(action==='refresh-activity'){await activity();}
    else if(action==='activity-tab'){S.activityTab=id;paintActivity();}
    else if(action==='refresh-connections'){await boot();await connections();}
    else if(action==='continue-perpl'){await c.finance.openPerpl(id,{post:el.dataset.source,feed:S.boot.activeFeed},String(S.perplIntent?.market)===String(id)?S.perplIntent.direction:'long');}
    else return false;
    return true;
  }
  let polling=false;
  async function poll(){if(document.hidden||S.modal||polling)return;polling=true;try{if(S.view==='agents'&&S.boot.me)await connections();else if(S.view==='activity'&&S.boot.me&&(S.activity?.entries.some(e=>['submitted','confirmed'].includes(e.state))||c.finance.pending().some(e=>e.user===S.boot.me.id)))await activity();}finally{polling=false;}}
  return {homeHeading,homeAlgorithms,picker,feeds,paintFeeds,preview,feedDetail,postDetail,connections,activity,openActivity,origin,originCard,handle,poll};
}
