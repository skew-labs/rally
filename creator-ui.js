// Creator identity, launch previews and receipt-backed earnings share one vocabulary.
export function creatorUI({S,$,api,esc,icon,avatar,priceHTML,notify,navigate,render,closeModal,trade,openCommunityToken,pageHeader,empty,loading,afterEarnings,modal,needAccount,walletReady}){
 const raw=(value,decimals=6)=>{
  if(value==null)return '—';
  try{const n=BigInt(value),unit=10n**BigInt(decimals),whole=n/unit,part=(n%unit).toString().padStart(decimals,'0').slice(0,decimals===6?6:4).replace(/0+$/,'');return whole.toLocaleString('en-US')+(part?'.'+part:'');}catch{return '—';}
 };
 const usdc=n=>raw(n)+' USDC';
 const stamp=n=>new Date(n*1000).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
 const art=t=>`<span class="cr-art">${t?.logoURI||t?.imageURI?`<img src="${esc(t.logoURI||t.imageURI)}" alt="${esc(t.name||'Token')}" width="72" height="72">`:icon('image')}</span>`;
 const ownFeeds=()=>S.boot.feeds.filter(f=>f.owner===S.boot.me?.id);
 const allocation=t=>`<div class="cr-allocation"><div><span>Creator</span><b>${100-Number(t.buybackBps||0)/100}%</b></div><div><span>Buyback</span><b>${Number(t.buybackBps||0)/100}%</b></div><div><span>Burn of tokens bought</span><b>${Number(t.burnBps||0)/100}%</b></div></div>`;
 function buybackStatus(t){
  const v=t?.stats||{};
  if(t?.stale)return {state:'stale',text:'Refresh to check buyback availability'};
  if(v.paused)return {state:'paused',text:'Buybacks paused'};
  if(Number(t?.buybackBps)===0)return {state:'disabled',text:'Buybacks off · Sales paid to creator'};
  try{
   if(v.poolQuoteRaw==null||v.minBatchRaw==null)return {state:'unknown',text:'Buyback availability not checked'};
   const pool=BigInt(v.poolQuoteRaw),minimum=BigInt(v.minBatchRaw),required=minimum*200n;
   if(pool/200n<minimum)return {state:'liquidity',text:'Buybacks need '+raw(required)+' USDC in the pool · '+raw(pool)+' available'};
   if(BigInt(v.pendingBuyback||0)<minimum)return {state:'revenue',text:'Buybacks start at '+raw(minimum)+' USDC reserved'};
   return {state:'queued',text:'Queued · Waiting for oracle and price checks'};
  }catch{return {state:'unknown',text:'Buyback availability not checked'};}
 }
 function preview(v){return `<aside class="cr-launch-preview" aria-label="Token and community preview"><div class="cr-preview-label">Your community</div><div class="cr-preview-identity">${art(v)}<span><b data-cr-name>${esc(v.name||'Your token')}</b><small data-cr-symbol>${esc(v.symbol||'TOKEN')}</small></span></div><div class="cr-preview-creator">${avatar(S.boot.me)}<span>@${esc(S.boot.me.handle)}</span><span>Creator</span></div><div class="cr-preview-network"><img src="/assets/MON.png" alt="" width="16" height="16">Monad<span>PancakeSwap V2</span></div><div class="cr-preview-pool"><span>Initial pool</span><b data-cr-seed>${esc(v.seedUSDC)} USDC</b></div><div class="cr-preview-routing"><div class="cr-preview-label">Per 100 USDC algorithm sale</div><div><span>Paid to you</span><b><span data-cr-payout>${100-Number(v.buybackBps)/100}</span> USDC</b></div><div><span>Token buyback</span><b><span data-cr-reserve>${Number(v.buybackBps)/100}</span> USDC</b></div><div><span>Burn of tokens bought</span><b data-cr-burn>${Number(v.burnBps)/100}%</b></div></div><small class="cr-preview-caption">Allocation preview · Launch required</small></aside>`;}
 function updatePreview(f,v,image){
  const assign=(selector,value)=>{const e=$(selector,f);if(e)e.textContent=value;};
  assign('[data-cr-name]',v.name.trim()||'Your token');assign('[data-cr-symbol]',v.symbol.toUpperCase()||'TOKEN');assign('[data-cr-seed]',v.seedUSDC+' USDC');
  assign('[data-cr-payout]',100-v.buybackBps/100);assign('[data-cr-reserve]',v.buybackBps/100);assign('[data-cr-burn]',v.burnBps/100+'%');
  const host=$('.cr-art',f),url=image||v.imageURI;
  if(host&&host.dataset.src!==(url||'')){host.dataset.src=url||'';host.innerHTML=url?`<img src="${esc(url)}" alt="Token preview" width="72" height="72">`:icon('image');}
 }
 function account(t,d){const feeds=ownFeeds();return `<section class="cr-account" aria-label="Creator tools"><button class="ct-account-card" data-action="${t?'community':'community-token'}" ${t?`data-id="${esc(t.community)}"`:""}>${art(t||d)}<span><b>${esc(t?.name||d?.name||'Create your token')}</b><small>${t?'Active · '+esc(t.symbol):d?'Draft saved':'Your community on Monad'}</small></span>${icon('chevron')}</button>${t?`<div class="cr-account-links"><button data-action="ct-community" data-id="${esc(t.community)}">${icon('nav-communities')}Community</button><button data-action="cr-share" data-id="profile">${icon('share')}Share profile</button></div>${allocation(t)}`:''}<div class="cr-account-tools"><button data-action="cr-algorithms">${icon('feeds')}<span>Algorithms<small>${feeds.length?feeds.length+' published':'Create an algorithm'}</small></span>${icon('chevron')}</button><button data-nav="earnings">${icon('nav-activity')}<span>Earnings<small>Payments & buybacks</small></span>${icon('chevron')}</button></div></section>`;}
 function publicToken(p){const t=p.communityToken;if(!t)return '';const feeds=S.boot.feeds.filter(f=>f.owner===t.owner);return `<section class="cr-profile-token" aria-label="Community token"><div class="cr-profile-token-head">${art(t)}<span><b>${esc(t.name)}</b><small>${esc(t.symbol)} · Monad</small></span><button class="r-btn small" data-action="trade" data-id="${esc(t.address)}">Trade</button></div><div class="cr-profile-token-meta"><button data-action="ct-community" data-id="${esc(t.community)}">Community ${icon('chevron')}</button><span>${t.buybackBps/100}% sales buyback</span>${feeds.length?`<button data-action="${p.id===t.owner?'profile-section':'cr-creator-algorithms'}" data-id="${p.id===t.owner?'feeds':esc(t.owner)}">${feeds.length} algorithm${feeds.length===1?'':'s'}</button>`:''}</div></section>`;}
 // A community token is the shared identity, not a new hosted-agent runtime.
 function communityToken(id){
  const own=S.boot.communityToken?.token;
  return own?.community===id?own:S.boot.people.find(p=>p.communityToken?.community===id)?.communityToken||null;
 }
 const agentsFor=t=>S.boot.people.filter(p=>p.kind==='agent'&&p.owner===t.owner);
 const feedsFor=t=>S.boot.feeds.filter(f=>f.owner===t.owner);
 const isOwner=t=>Boolean(t&&S.boot.me?.id===t.owner);
 function communityEntry(){
  const status=S.boot.communityToken,t=status?.token,d=status?.draft,owner=S.boot.me;
  if(!owner)return `<section class="cr-community-entry"><div><h2>Your community</h2><p>One profile. Your token, agents and algorithms.</p></div><button class="lp-primary" data-action="cr-community-setup">Create community</button></section>`;
  return `<section class="cr-community-entry" data-community-state="${t?'live':d?'draft':'not_started'}"><div class="cr-community-entry-identity">${art(t||d)}<div><small>Your community</small><h2>${esc(t?.name||d?.name||owner.name)}</h2><p>${t?esc(t.symbol)+' · Monad':d?'Token draft saved':'Set up your community token'}</p></div></div><div class="cr-community-entry-actions">${t?`<button class="lp-primary" data-action="cr-community-open" data-id="posts">Open community</button><button class="lp-secondary" data-action="cr-community-open" data-id="agents">${icon('nav-agents')}Agents</button><button class="lp-secondary" data-action="cr-community-open" data-id="algorithms">${icon('feeds')}Algorithms</button>`:`<button class="lp-primary" data-action="cr-community-setup">${d?'Continue setup':'Create community'}</button>`}</div></section>`;
 }
 function communityHeader(c){
  const t=communityToken(c.id);if(!t)return '';
  const market=t.asset||{},stats=t.stats||{},fresh=!t.stale&&!market.stale;
  const price=fresh?(market.price??stats.referencePriceUSDC):null,cap=fresh?(market.marketCap??stats.referenceMarketCapUSDC):null;
  const dollar=n=>n==null||!Number.isFinite(Number(n))?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumSignificantDigits:5,maximumFractionDigits:2,notation:Number(n)>=10000?'compact':'standard'}).format(Number(n));
  const owner=[S.boot.me,...S.boot.people].find(p=>p?.id===t.owner);
  return `<section class="cr-community-header" aria-label="Community token"><div class="cr-community-title">${art(t)}<div><small>${esc(t.symbol)} · Monad</small><h1>${esc(t.name)}</h1>${owner?`<button class="cr-community-owner" data-action="profile" data-id="${esc(owner.id)}">${avatar(owner)}@${esc(owner.handle)}</button>`:`<span class="cr-community-owner">${esc(c.members)} members</span>`}</div><div class="cr-community-trade"><button class="r-btn cr-buy" data-action="cr-token-buy">Buy</button><button class="r-btn cr-sell" data-action="cr-token-sell">Sell</button></div></div><div class="cr-community-market"><div><small>Market cap / FDV</small><b>${esc(dollar(cap))}</b></div><div><small>Price</small><b>${priceHTML(price)}</b></div><div><small>Algorithm sales</small><b>${usdc(stats.grossRevenue)}</b></div></div><div class="cr-community-footer"><span>${Number(c.members).toLocaleString('en-US')} members</span><span>${fresh?'Observed '+stamp(t.verifiedAt):'Price reference unavailable'}</span>${!isOwner(t)?`<button class="r-text-button" data-action="join" data-id="${esc(c.id)}">${c.joined?'Joined':'Join community'}</button>`:`<button class="r-text-button" data-action="community-token">Manage token</button>`}</div></section>`;
 }
 function communitySection(c,section){
  const t=communityToken(c.id);if(!t)return '';
  if(section==='agents'){
   const agents=agentsFor(t),posts=(S.timelinePosts||[]).filter(p=>agents.some(a=>a.id===p.author.id)),owner=isOwner(t);
   return `<section class="cr-community-section"><div class="cr-section-head"><h2>Agents</h2>${owner?'<button class="r-btn small" data-action="connect-agent">Connect agent</button>':''}</div><p class="cr-workspace-note">External agents operated by this creator.</p><div class="cr-community-agents">${agents.map(a=>`<button class="cr-agent-profile" data-action="profile" data-id="${esc(a.id)}">${avatar(a)}<span><b>${esc(a.name)}</b><small>@${esc(a.handle)}</small></span>${icon('chevron')}</button>`).join('')||`<div class="cr-empty"><p>No agent profiles yet</p>${owner?'<button class="r-btn" data-action="connect-agent">Connect your agent</button>':''}</div>`}</div><div class="cr-section-head"><h3>In this community</h3></div>${posts.slice(0,8).map(p=>`<button class="cr-agent-update" data-action="open-post" data-id="${esc(p.id)}">${avatar(p.author)}<span><b>${esc(p.author.name)}</b><p>${esc(p.text||'Media post')}</p><small>${stamp(p.created)}</small></span>${icon('chevron')}</button>`).join('')||'<p class="cr-workspace-note">No agent posts in this community yet.</p>'}</section>`;
  }
  if(section==='algorithms'){
   const feeds=feedsFor(t);return `<section class="cr-community-section"><div class="cr-section-head"><h2>Algorithms</h2>${isOwner(t)?'<button class="r-btn small" data-action="create-feed">Create algorithm</button>':''}</div><p class="cr-workspace-note">Creator subscriptions. ${Number(t.buybackBps)/100}% of sales is reserved for ${esc(t.symbol)} buybacks.</p>${feeds.map(f=>`<button class="cr-workspace-feed" data-action="feed-detail" data-id="${esc(f.id)}">${icon('feeds')}<span><b>${esc(f.name)}</b><small>${Number(f.priceRaw)?esc(f.price)+' USDC / 30 days':'Free'}</small></span>${icon('chevron')}</button>`).join('')||'<div class="cr-empty"><p>No published algorithms yet</p></div>'}</section>`;
  }
  if(section==='revenue'){
   const v=t.stats||{};return `<section class="cr-community-section"><div class="cr-section-head"><h2>Revenue & buybacks</h2>${isOwner(t)?'<button class="r-btn small" data-nav="earnings">Receipts</button>':''}</div><div class="cr-workspace-totals"><div><small>Algorithm sales</small><b>${usdc(v.grossRevenue)}</b></div><div><small>Reserved for buyback</small><b>${usdc(v.pendingBuyback)}</b></div><div><small>Buybacks spent</small><b>${usdc(v.quoteSpent)}</b></div><div><small>Tokens burned</small><b>${raw(v.tokensBurned,18)} ${esc(t.symbol)}</b></div></div>${allocation(t)}<p class="ct-status" data-buyback-state="${buybackStatus(t).state}">${esc(buybackStatus(t).text)}</p><small class="cr-workspace-note">${t.stale?'Last observed ':'Observed '}${stamp(t.verifiedAt)}. Reserved funds are not completed buybacks.</small>${isOwner(t)?'<button class="r-btn" data-action="ct-policy">Edit allocation</button>':''}<a class="cr-workspace-contract" href="https://monadvision.com/address/${esc(t.vault)}" target="_blank" rel="noopener noreferrer">View vault ${icon('external')}</a></section>`;
  }
  return '';
 }
 function feedList(feeds){return `<section class="cr-feeds"><div class="cr-section-head"><h2>Your algorithms</h2><button class="r-text-button" data-action="cr-algorithms">Manage ${icon('chevron')}</button></div>${feeds.length?feeds.map(f=>`<button class="cr-feed-row" data-action="feed-detail" data-id="${esc(f.id)}">${icon('feeds')}<span><b>${esc(f.name)}</b><small>${Number(f.priceRaw)?esc(f.price)+' USDC / 30 days':'Free'}</small></span>${icon('chevron')}</button>`).join(''):`<div class="cr-empty"><p>No algorithms yet</p><button class="r-btn" data-action="create-feed">Create algorithm</button></div>`}</section>`;}
 let sequence=0,period='all',tab='payments';
 const earningsCache=new Map(),earningsRequests=new Map();
 async function earnings(refresh=false){
  const version=++sequence,actor=S.boot.me?.id,host=$('#page');
  if(!actor){host.innerHTML=pageHeader('Earnings')+empty('Sign in to see earnings','','<button class="r-btn primary" data-action="account">Sign in</button>');return;}
  const key=actor+'|'+period,hit=earningsCache.get(key),oldScroll=window.scrollY;
  if(!host.querySelector('.cr-earnings'))host.innerHTML=pageHeader('Earnings')+`<div class="cr-earnings-loading">${loading()}</div>`;
  host.setAttribute('aria-busy','true');
  try{
   if(refresh)earningsCache.delete(key);
   if((refresh||!hit||Date.now()-hit.at>=10000)&&!earningsRequests.has(key)){
    const request=api('/api/creator/earnings?period='+period).then(data=>{earningsCache.set(key,{at:Date.now(),data});while(earningsCache.size>4)earningsCache.delete(earningsCache.keys().next().value);return data;}).finally(()=>earningsRequests.delete(key));
    earningsRequests.set(key,request);
   }
   const d=earningsRequests.has(key)?await earningsRequests.get(key):hit.data;
   if(version!==sequence||actor!==S.boot.me?.id||S.view!=='earnings')return;
   const t=d.token,stats=t?.stats||{},list=tab==='payments'?d.payments:d.buybacks;
   host.innerHTML=pageHeader('Earnings',`<button class="r-icon-button" data-action="cr-refresh" aria-label="Refresh earnings">${icon('repeat-2')}</button>`)+`<div class="cr-earnings"><div class="cr-periods" role="group" aria-label="Payment period">${[['24h','24h'],['7d','7d'],['30d','30d'],['all','All time']].map(([id,label])=>`<button data-action="cr-period" data-id="${id}" aria-pressed="${period===id}">${label}</button>`).join('')}</div><section class="cr-paid"><small>Paid to you</small><h2>${raw(d.totals.creatorRaw)} <span>USDC</span></h2><div class="cr-paid-sub"><span>${d.totals.payments} finalized payment${d.totals.payments===1?'':'s'}</span><span>Monad</span></div><div class="cr-paid-breakdown"><span>Algorithm sales<b>${usdc(d.totals.grossRaw)}</b></span><span>Reserved for buyback<b>${usdc(d.totals.reservedRaw)}</b></span></div></section>${t?`<section class="cr-vault"><div class="cr-section-head"><h2>${esc(t.symbol)} buybacks</h2><small>All time</small></div><div class="cr-vault-stats"><span><small>Spent</small><b>${usdc(stats.quoteSpent)}</b></span><span><small>Tokens burned</small><b>${raw(stats.tokensBurned,18)}</b></span><span><small>Queued</small><b>${usdc(stats.pendingBuyback)}</b></span></div>${allocation(t)}<p class="ct-status" data-buyback-state="${buybackStatus(t).state}">${esc(buybackStatus(t).text)}</p><div class="cr-vault-foot"><small>${t.stale?'Last observed ':'Observed '}${stamp(t.verifiedAt)}${stats.paused?' · Paused':''}</small><button data-action="community-token">Manage token ${icon('chevron')}</button></div></section>`:''}<section class="cr-receipts"><div class="cr-section-head"><h2>Activity</h2><small>Recorded ${stamp(d.fetchedAt)}</small></div><div class="cr-receipt-tabs" role="group" aria-label="Earnings activity">${[['payments','Payments'],['buybacks','Buybacks']].map(([id,label])=>`<button data-action="cr-tab" data-id="${id}" aria-pressed="${tab===id}">${label}</button>`).join('')}</div>${list.length?list.map(p=>tab==='payments'?`<article class="cr-payment"><div><b>${usdc(p.creatorRaw)} paid</b><button data-action="feed-detail" data-id="${esc(p.feed)}">${esc(p.feedName)}</button><small>${stamp(p.recordedAt)}</small></div><a class="r-icon-button" href="https://monadvision.com/tx/${esc(p.tx)}" target="_blank" rel="noopener noreferrer" aria-label="View payment transaction">${icon('external')}</a><details><summary>Allocation${icon('down')}</summary><div><span>Sale</span><b>${usdc(p.grossRaw)}</b></div><div><span>Paid to creator</span><b>${usdc(p.creatorRaw)}</b></div><div><span>Reserved for buyback</span><b>${usdc(p.reservedRaw)}</b></div></details></article>`:`<article class="cr-payment"><div><b>${usdc(p.quoteRaw)} spent</b><span>${raw(p.burnedRaw,18)} ${p.burnMethod==='dead_address'?'tokens sent to burn address':'tokens burned'}</span><small>${stamp(p.recordedAt)}</small></div><a class="r-icon-button" href="https://monadvision.com/tx/${esc(p.tx)}" target="_blank" rel="noopener noreferrer" aria-label="View buyback transaction">${icon('external')}</a></article>`).join(''):`<div class="cr-empty"><p>${tab==='payments'?'No finalized payments in this period':'No payment-linked buybacks in this period'}</p>${tab==='payments'?'<button class="r-btn" data-action="cr-algorithms">Your algorithms</button>':''}</div>`}${d.hasMorePayments&&tab==='payments'?'<small class="cr-coverage">Showing the latest 50 payments. Totals include all matching payments.</small>':''}<small class="cr-coverage">${tab==='payments'?'Finalized Rally feed payments. Periods use receipt recording time.':'Payment-linked events only. Vault totals above include other on-chain buybacks.'}</small></section>${feedList(ownFeeds())}</div>`;
   afterEarnings?.();
   if(oldScroll)window.scrollTo({top:oldScroll,behavior:'instant'});
  }catch(e){if(version===sequence&&S.view==='earnings'&&actor===S.boot.me?.id)host.innerHTML=pageHeader('Earnings')+empty('Couldn’t load earnings',esc(e.message),'<button class="r-btn" data-action="cr-refresh">Retry</button>');}
  finally{if(version===sequence||S.view!=='earnings')host.removeAttribute('aria-busy');}
 }
 async function handle(action,id){
  if(action==='cr-community-setup'){if(!S.boot.me)await needAccount(()=>navigate('launchpad'));else await openCommunityToken();return true;}
  if(action==='cr-community-open'){
   const t=S.boot.communityToken?.token;if(!t)return true;
   closeModal();S.community=t.community;S.communityTab=['posts','agents','algorithms','revenue'].includes(id)?id:'posts';
   if(S.view==='community'&&new URLSearchParams(location.search).get('id')===t.community)await render();else await navigate('community');return true;
  }
  if(action==='cr-token-buy'||action==='cr-token-sell'){
   const t=communityToken(S.community);if(t)trade(t.address,null,action==='cr-token-sell'?'sell':'buy');return true;
  }
  if(action==='cr-period'){if(!['24h','7d','30d','all'].includes(id))return true;period=id;await earnings();return true;}
  if(action==='cr-tab'){if(!['payments','buybacks'].includes(id))return true;tab=id;await earnings();return true;}
  if(action==='cr-refresh'){await earnings(true);return true;}
  if(action==='cr-creator-algorithms'){S.profile=id;S.profileTab='feeds';await navigate('profile');return true;}
  if(action==='cr-algorithms'){S.feedFilter='yours';await navigate('feeds');return true;}
  if(action==='cr-share'){
   if(!S.boot.me)return true;
   const shareURL=location.origin+'/?view=profile&id='+encodeURIComponent(S.boot.me.id);
   try{await navigator.clipboard.writeText(shareURL);notify('Profile link copied');}catch{notify('Could not copy link. Open your profile to share it.');}return true;
  }
  return false;
 }
 return {preview,updatePreview,account,publicToken,earnings,handle,buybackStatus,communityEntry,communityToken,communityHeader,communitySection};
}
