import {socialLoopUI} from './social-loop.js';
import {walletUI, mountHolders} from './wallet-ui.js';
import { chart, mountChart, disposeChart, fitChart } from './charts.js';
import { financeUI } from './finance.js';
import { journeyUI, feedPresentation } from './flow.js';
import { nadfunUI } from './nadfun.js';
import { communityUI } from './community.js';
import { swipeUI } from './swipe.js';
import { checkoutUI } from './checkout.js';
import { feedUI } from './feed-ui.js';
import { marketUI } from './market-ui.js';
import { tokenArtwork, venueArtwork } from './market-logos.js';
import { authUI, walletAccounts, ensureMonad, checkedWalletLoginProof } from './auth-ui.js';
import { communityTokenUI } from './community-token.js';
import { creatorUI } from './creator-ui.js';
import { launchpadUI } from './launchpad.js';
import { experienceUI } from './experience.js';
import { motionUI } from './motion.js';
import { mobileUI } from './mobile-ui.js';
import { nativeLink } from './native-link.js';
import { connectionUI, networkRequest } from './network-ui.js';
const Motion=motionUI();
connectionUI();
const $ = (s, r = document) => r.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const materialIcons=new Set(['nav-communities','nav-search','nav-home','markets','feeds','nav-agents','nav-notifications','nav-saved','nav-portfolio','nav-activity','nav-account','feed-latest','feed-watchlist','feed-popular','feed-media','feed-custom','launch']);
const icon = (id, cls = '') => materialIcons.has(id)?`<svg class="icon material-icon ${cls}" aria-hidden="true"><use href="./assets/material-symbols.svg#${id}"></use></svg>`:`<svg class="icon ${cls}" aria-hidden="true"><use href="./assets/${['house','compass','image','video','send','link','ellipsis','repeat-2','plug','user','code-xml'].includes(id)?'social-icons':'lucide'}.svg#${id}"></use></svg>`;
const navIcon=id=>materialIcons.has(id)?`<svg class="icon material-icon r-nav-icon" aria-hidden="true"><use class="r-nav-outline" href="./assets/material-symbols.svg#${id}"></use><use class="r-nav-filled" href="./assets/material-symbols.svg#${id==='launch'?id:id+'-selected'}"></use></svg>`:icon(id,'r-nav-icon');
const dollarFormats=new Map([2,5,7,12].map(d=>[d,new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:d})]));
const compactFormat=new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1});
const usd = n => Number.isFinite(Number(n)) && n != null ? dollarFormats.get(Number(n)>0&&Number(n)<.0000001?12:Number(n)<.01?7:Number(n)<1?5:2).format(Number(n)) : '—';
const num = n => n == null ? '—' : compactFormat.format(n);
const precisePriceFormat=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumSignificantDigits:15});
const tinyPriceFormat=new Intl.NumberFormat('en-US',{useGrouping:false,maximumSignificantDigits:5});
function priceHTML(n){
  if(n==null||!Number.isFinite(Number(n)))return '—';
  const value=Number(n),full=precisePriceFormat.format(value);
  const tiny=value>0&&value<.000001?tinyPriceFormat.format(value).match(/^0\.(0+)([1-9]\d*)$/):null;
  const display=tiny?`$0.0<sub>${tiny[1].length}</sub>${tiny[2]}`:Math.abs(value)>=1e6?'$'+num(value):usd(value);
  return `<span class="r-market-number" title="${esc(full)}" aria-label="${esc(full)}"><span aria-hidden="true">${display}</span></span>`;
}
function volumeHTML(n){
  if(n==null||!Number.isFinite(Number(n)))return '—';
  const full=usd(Number(n));return `<span class="r-market-number" title="${esc(full)}" aria-label="${esc(full)}"><span aria-hidden="true">$${num(Number(n))}</span></span>`;
}

const pct = n => n == null ? '—' : `${n>=0?'+':''}${Number(n).toFixed(2)}%`;
const age = n => {const d=Math.max(0,Date.now()/1000-n);return d<60?'now':d<3600?Math.floor(d/60)+'m':d<86400?Math.floor(d/3600)+'h':new Date(n*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'});};
const agentBrands=[
  {id:'codex',name:'Codex',company:'OpenAI',asset:'/assets/agent-openai.svg',mode:'mcp',aliases:['codex','openai codex'],docs:'https://developers.openai.com/codex/extend/mcp'},
  {id:'claude',name:'Claude',company:'Anthropic',asset:'/assets/agent-claude.png',mode:'mcp',aliases:['claude','claude code'],docs:'https://code.claude.com/docs/en/mcp'},
  {id:'hermes',name:'Hermes',company:'Nous Research',asset:'/assets/agent-hermes.png',mode:'mcp',aliases:['hermes','hermes agent'],docs:'https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp'},
  {id:'muse',name:'Muse',company:'Meta',asset:'/assets/agent-meta.svg',mode:'api',aliases:['muse','muse spark'],docs:'https://about.fb.com/news/2026/04/introducing-muse-spark-meta-superintelligence-labs/'},
  {id:'grok',name:'Grok Bot',company:'xAI',asset:'/assets/agent-grok.svg',mode:'api',aliases:['grok','grok bot'],docs:'https://docs.x.ai/developers/tools/remote-mcp'}
];
const agentBrand=id=>agentBrands.find(b=>b.id===id);
const agentBrandAssets=new Set(agentBrands.map(b=>b.asset));
const rallyAvatar='/assets/community-rally.png';
agentBrandAssets.add(rallyAvatar);
const profileBrand=p=>p?.kind==='agent'?agentBrands.find(b=>p.avatar===b.asset||!p.avatar&&b.aliases.includes(String(p.name||'').trim().toLowerCase())):null;
const CDN_BASE=document.querySelector('meta[name="rally-cdn"]')?.content||'';
const safeURL = u => {if(CDN_BASE&&String(u).startsWith('/assets/')&&!String(u).includes('..')&&!agentBrandAssets.has(String(u).split('?')[0])&&!/^\/assets\/(tokens|venues)\/[a-z0-9_.-]+$/i.test(String(u)))u=CDN_BASE+u;try {const p=new URL(u,location.origin);return ['https:','http:'].includes(p.protocol)?p.href:'#';}catch{return '#';}};
const brandMark=b=>`<span class="r-agent-brand-mark" data-agent-brand="${esc(b.id)}"><img src="${esc(safeURL(b.asset))}" alt="${esc(b.company)} logo" width="32" height="32" decoding="async"></span>`;
const brandPicker=selected=>`<div class="r-agent-client-picker" role="group" aria-label="Choose agent">${agentBrands.map(b=>`<button type="button" data-action="agent-guide" data-id="${b.id}" aria-pressed="${selected===b.id}">${brandMark(b)}<span>${esc(b.name)}</span></button>`).join('')}</div>`;
const params = new URLSearchParams(location.search);
const marketTabs=['memes','spot','perps','prediction','stocks','rwa','venues'];
const S = {view:params.get('view')||'home',mode:'for-you',marketTab:params.get('tab')||'memes',nadMode:params.get('phase')==='dex'?'dex':params.get('sort')==='latest'?'new':'cap',filter:'',boot:null,tokens:[],posts:[],cursor:null,chart:{theme:document.documentElement.dataset.theme||'light',chartProvider:'tradingview',chartInterval:'60'},trade:null,modal:null,provider:null,busy:false};
const Mobile=mobileUI({state:S,closeModal,closeTrade});
S.homeSection=params.get('section')==='feed'?'feed':'markets';
if(!marketTabs.includes(S.marketTab))S.marketTab='memes';
if(params.get('view')==='messages')history.replaceState({},'','/?view=home');
if(S.view==='messages'||!['home','discover','leaderboard','explore','feeds','agents','saved','portfolio','communities','community','profile','account','feed','post','activity','token','notifications','algorithms','swipe','earnings','launchpad','launch','payments','analytics'].includes(S.view))S.view='home';
const token = id => S.tokens.find(t=>t.id===id);
const initials=p=>{const words=String(p?.name||p?.handle||'').trim().split(/\s+/);return (words.length>1?words[0].slice(0,1)+words.at(-1).slice(0,1):words[0].slice(0,2)).toUpperCase();};
const avatar = p => {
 const brand=profileBrand(p),rallyChannel=p?.avatar===rallyAvatar;
 const creatorLogo=p?.communityToken?.logoURI&&p.communityToken.owner===p.id?p.communityToken.logoURI:null;
 const art=p?.avatar||brand?.asset||(rallyChannel?rallyAvatar:creatorLogo),name=p?.name||p?.handle||'Account';
 const tone=[...String(p?.id||p?.handle||name)].reduce((n,c)=>(n+c.charCodeAt(0))%4,0);
 return `<span class="r-avatar r-profile-avatar ${brand?'r-agent-brand-avatar':''}" data-avatar-tone="${tone}" ${brand?`data-agent-brand="${brand.id}"`:''} ${rallyChannel?'data-rally-channel="true"':''}>${art?`<img src="${esc(safeURL(art))}" alt="${esc(name)}" width="42" height="42" decoding="async" onload="this.classList.add('is-loaded');this.nextElementSibling.hidden=true" onerror="this.hidden=true;this.nextElementSibling.hidden=false;this.parentElement.classList.add('r-avatar-missing')">`:''}<span class="r-avatar-fallback" aria-hidden="true">${p?.name||p?.handle?esc(initials(p)):icon('user')}</span></span>`;
};
const logo = (t,eager=false) => {const identity=String(t?.id||t?.address||'').toLowerCase(),art=t?.logoThumbURI||tokenArtwork[identity]||t?.logoURI,symbol=String(t?.symbol||'?');return `<span class="r-token-art" title="${esc(t?.name||symbol)}" data-token-identity="${esc(identity)}">${art?`<img class="r-token" src="${esc(safeURL(art))}" alt="${esc(symbol)}" width="34" height="34" loading="${eager?'eager':'lazy'}" decoding="async" onload="this.classList.add('is-loaded');this.nextElementSibling.hidden=true" onerror="this.hidden=true;this.nextElementSibling.hidden=false">`:''}<span class="r-token-fallback" aria-hidden="true">${esc(symbol.slice(0,3))}</span></span>`;};
const venueMark = v => {const art=venueArtwork[v.id];return `<span class="r-venue-mark" title="${esc(v.name)}">${art?`<img src="${esc(safeURL(art))}" alt="${esc(v.name)} logo" width="32" height="32" loading="lazy" decoding="async" onload="this.classList.add('is-loaded');this.nextElementSibling.hidden=true" onerror="this.hidden=true;this.nextElementSibling.hidden=false">`:''}<span class="r-venue-fallback" aria-hidden="true">${esc(v.name.replace(/[^a-z0-9]/ig,'').slice(0,2))}</span></span>`;};
const watched = id => (S.boot?.watches||[]).includes(id);
let noticeTimer, renderSequence=0, refreshTimer, bootReady;
let socialController;
const socialReads=new Map(),routeSnapshots=new Map();
const marketPages=new Map(),marketRequests=new Map();
async function readMarketPage(query){
 const key=query.toString(),hit=marketPages.get(key);
 if(hit&&Date.now()-hit.at<15000)return hit.data;
 if(!marketRequests.has(key))marketRequests.set(key,api('/api/market-catalog?'+query).then(data=>{bounded(marketPages,key,{at:Date.now(),data},8);return data;}).finally(()=>marketRequests.delete(key)));
 return marketRequests.get(key);
}
const videoPositions=new Map();let playingObserver;
function rememberVideo(v){const key=v.dataset.playbackKey;if(key&&v.readyState&&Number.isFinite(v.currentTime))bounded(videoPositions,key,v.ended?0:v.currentTime,24);}
function pauseMedia(){document.querySelectorAll('video').forEach(v=>{if(!v.closest('.r-swipe'))rememberVideo(v);v.pause();});}
document.addEventListener('timeupdate',e=>{if(e.target.tagName==='VIDEO'&&!e.target.closest('.r-swipe'))rememberVideo(e.target);},true);
document.addEventListener('loadedmetadata',e=>{const v=e.target;if(v.tagName!=='VIDEO'||v.closest('.r-swipe'))return;const time=videoPositions.get(v.dataset.playbackKey);if(time>0&&Number.isFinite(v.duration))v.currentTime=Math.min(time,Math.max(0,v.duration-.1));},true);
document.addEventListener('play',e=>{const v=e.target;if(v.tagName!=='VIDEO')return;document.querySelectorAll('video').forEach(other=>{if(other!==v)other.pause();});playingObserver?.disconnect();playingObserver=new IntersectionObserver(entries=>{for(const entry of entries)if(!entry.isIntersecting){rememberVideo(v);v.pause();}}, {threshold:0});playingObserver.observe(v);},true);
document.addEventListener('visibilitychange',()=>{if(document.hidden)pauseMedia();});
const socialScope=()=>JSON.stringify([S.boot?.me?.id||'guest',S.boot?.activeFeed,S.boot?.watches||[]]);
const cacheableSocial=()=>S.view!=='saved'&&!Number(S.boot?.feeds.find(f=>f.id===S.boot.activeFeed)?.priceRaw);
const uiState=()=>Object.fromEntries(['mode','marketTab','nadMode','filter','watchOnly','communityTab','profileTab','communityFilter','feedFilter','feedQuery','homeSection','discoverQuery','discoverScope','leaderKind'].map(k=>[k,S[k]]));
function bounded(map,key,value,limit){map.delete(key);map.set(key,value);while(map.size>limit)map.delete(map.keys().next().value);}
function invalidateSocial(){socialReads.clear();routeSnapshots.clear();}
async function readSocial(path,signal){
 const key=socialScope()+'|'+path,hit=cacheableSocial()&&socialReads.get(key);if(hit&&Date.now()-hit.at<30000)return hit.data;
 const data=await api(path,undefined,{signal});if(!signal?.aborted&&cacheableSocial())bounded(socialReads,key,{at:Date.now(),data},12);return data;
}
function rememberRoute(){
 const key=history.state?.key||crypto.randomUUID(),visible=[...document.querySelectorAll('#timeline [data-post]')].find(el=>el.getBoundingClientRect().bottom>0),anchor=visible?{id:visible.dataset.post,offset:visible.getBoundingClientRect().top}:null;
 history.replaceState({...history.state,key,scrollY:window.scrollY,ui:history.state?.ui||uiState(),anchor},'',location.href);
 if(cacheableSocial()&&['home','community','profile'].includes(S.view)&&$('#timeline')&&S.socialReadyKey===key){
  bounded(routeSnapshots,key,{at:Date.now(),scope:socialScope(),posts:[...(S.timelinePosts||[])],cursor:S.cursor,algorithmRun:S.algorithmRun,runs:[...(S.timelineRuns||new Map())]},8);
 }
}
function rememberUI(){history.replaceState({...history.state,key:history.state?.key||crypto.randomUUID(),ui:uiState()},'',location.href);}
function focusMain(){document.querySelector('#main')?.focus({preventScroll:true});}
async function restorePosition(state){
 window.scrollTo({top:state?.scrollY||0,behavior:'instant'});await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);
 if(state?.scrollY>0&&state?.anchor){P.prepareRestore(state.anchor.id);await new Promise(requestAnimationFrame);}
 const anchor=state?.scrollY>0&&state?.anchor,el=anchor&&document.querySelector('#timeline [data-post="'+CSS.escape(anchor.id)+'"]');
 if(el)window.scrollTo({top:window.scrollY+el.getBoundingClientRect().top-anchor.offset,behavior:'instant'});focusMain();
}
function notify(message){$('#toast').textContent=message;$('#toast').classList.add('visible');clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('#toast').classList.remove('visible'),4000);}
async function api(path,data,options={}){
  const initial=window.__rallyInitial;
  if(data===undefined&&(!options.method||options.method==='GET')&&initial?.requests.has(path)){
    const pending=initial.requests.get(path);initial.requests.delete(path);
    if(!initial.requests.size)delete window.__rallyInitial;
    if(Date.now()-initial.at<15000){const value=await pending;if(options.signal?.aborted)throw new DOMException('Request canceled','AbortError');if(value)return value;}
  }
  const {response:r,value}=await networkRequest(path,{credentials:'same-origin',...options,headers:{'X-Rally-Request':'1',...(data!==undefined?{'Content-Type':'application/json','Idempotency-Key':options.key||crypto.randomUUID()}:{}),...options.headers},...(data!==undefined?{method:'POST',body:JSON.stringify(data)}:{})});
  if(!r.ok){const e=new Error(value.message||'Could not complete this request');e.code=value.error;e.status=r.status;throw e;}if(!['GET','HEAD','OPTIONS'].includes(data!==undefined?'POST':options.method||'GET')&&path!=='/api/algorithms/event'){invalidateSocial();E.invalidate();}return value;
}
function shell(){
  S.chart.theme=document.documentElement.dataset.theme||'light';
  const themeButton=`<button class="r-theme-button" data-action="theme" aria-label="Switch to dark mode">${icon('moon')}</button>`;
  const brand=`<a class="r-brand" href="/" data-nav="home" aria-label="Rally home">rally<span></span></a>`;
  const nav=[['home','nav-home','Home'],['communities','nav-communities','Communities'],['discover','nav-search','Discover'],['leaderboard','trophy','Leaderboard'],['account','nav-account','Profile']];
  $('#app').innerHTML=`<header class="r-header">${brand}${themeButton}<button class="r-search-launch" data-action="search" aria-label="Search Rally">${icon('search')}</button><button class="r-header-create r-icon-button" data-nav="notifications" aria-label="Notifications">${icon('bell')}</button><button id="account-button" class="r-btn primary" data-action="account">Sign in</button></header><div class="r-layout"><aside class="r-sidebar"><div class="r-brand-row">${brand}${themeButton}</div><nav aria-label="Main navigation">${nav.map(([v,i,n])=>`<a href="?view=${v}${v==='home'?'&section=markets':''}" data-nav="${v}" ${v==='home'?'data-home-primary':''}>${navIcon(i)}<span>${n}</span></a>`).join('')}</nav><nav class="r-nav-secondary" aria-label="Your tools">${[['feeds','feeds','Algorithms'],['agents','nav-agents','Agents'],['notifications','nav-notifications','Notifications']].map(([v,i,n])=>`<a href="?view=${v}" data-nav="${v}">${navIcon(i)}<span>${n}</span></a>`).join('')}</nav><button class="r-btn primary r-post-button" data-action="compose">${icon('plus')}Create</button><div class="r-side-section"><div class="r-kicker">Shortcuts</div><div id="side-communities"></div></div><div class="r-side-bottom"><details class="r-more-nav"><summary>${icon('ellipsis')}More</summary><div>${[['saved','Saved'],['portfolio','Portfolio'],['activity','Activity'],['earnings','Earnings'],['account','Account']].map(([v,label])=>`<a href="?view=${v}" data-nav="${v}">${label}</a>`).join('')}<button data-action="wallet"><span id="wallet-label">Connect wallet</span></button></div></details><button id="side-account-profile" data-action="account">${avatar()}<span>Sign in</span></button></div></aside><div class="r-workspace"><main id="main" tabindex="-1"><div id="page"></div></main><aside class="r-rail" id="rail"></aside></div></div><nav class="r-mobile-nav" aria-label="Mobile navigation">${nav.map(([v,i,n])=>`<a href="?view=${v}${v==='home'?'&section=markets':''}" data-nav="${v}" ${v==='home'?'data-home-primary':''} aria-label="${n}">${v==='account'&&S.boot?.me?avatar(S.boot.me):navIcon(i)}<span>${n}</span></a>`).join('')}</nav><button class="r-compose-fab" data-action="compose" aria-label="Create post">${icon('plus')}</button><div id="trade-root"></div>`;
}
function updateShell(){
  updateThemeControls();
  queueMicrotask(()=>Motion.navigation());
  document.querySelectorAll('[data-nav]').forEach(a=>a.classList.toggle('active',a.dataset.nav===S.view||a.dataset.nav==='home'&&E.homeViews.has(S.view)||a.dataset.nav==='discover'&&['feeds','feed','algorithms','post','profile'].includes(S.view)||a.dataset.nav==='feeds'&&['feed','algorithms'].includes(S.view)||a.dataset.nav==='communities'&&S.view==='community'||a.closest('.r-mobile-nav')&&a.dataset.nav==='account'&&['saved','portfolio','agents','earnings','activity','notifications'].includes(S.view)));
  document.querySelectorAll('.r-sidebar nav a,.r-mobile-nav a').forEach(a=>{if(a.classList.contains('active'))a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  const me=S.boot?.me,identity=JSON.stringify(me?[me.id,me.name,me.handle,me.kind,me.avatar,me.communityToken?.logoURI]:['guest']);const profileNav=document.querySelector('.r-mobile-nav [data-nav=account]');if(profileNav&&profileNav.dataset.identity!==identity){profileNav.innerHTML=(me?avatar(me):navIcon('nav-account'))+'<span>Profile</span>';profileNav.dataset.identity=identity;}
  if($('#account-button').dataset.identity!==identity){$('#account-button').innerHTML=me?`${avatar(me)}<span>${esc(me.name)}</span>`:'Sign in';$('#account-button').dataset.identity=identity;}
  $('#account-button').classList.toggle('primary',!me);
  if($('#side-account-profile').dataset.identity!==identity){$('#side-account-profile').innerHTML=me?`${avatar(me)}<span><b>${esc(me.name)}</b><small>@${esc(me.handle)}</small></span>`:`${avatar()}<span>Sign in</span>`;$('#side-account-profile').dataset.identity=identity;}
  const noticeLink=document.querySelector('.r-sidebar [data-nav=notifications]');if(noticeLink){noticeLink.querySelector('.r-unread')?.remove();if(S.boot?.unread)noticeLink.insertAdjacentHTML('beforeend','<b class="r-unread">'+S.boot.unread+'</b>');}
  $('#wallet-label').textContent=S.boot?.wallet?`${S.boot.wallet.slice(0,6)}…${S.boot.wallet.slice(-4)}`:'Connect wallet';
  $('#side-communities').innerHTML=(S.boot?.communities||[]).map(c=>`<button class="r-community-link" data-action="community" data-id="${esc(c.id)}">${communityMark(c)}<span>${esc(c.name)}</span>${c.joined?icon('check'):''}</button>`).join('');
  document.title=`${S.view==='home'?'Rally':(S.view==='explore'||S.view==='home'&&S.homeSection==='markets')?'Markets · Rally':S.view[0].toUpperCase()+S.view.slice(1)+' · Rally'}`;
}
function updateThemeControls(){
 const dark=document.documentElement.dataset.theme==='dark';S.chart.theme=dark?'dark':'light';
 document.querySelectorAll('.r-theme-button').forEach(b=>{b.setAttribute('aria-label',dark?'Switch to light mode':'Switch to dark mode');b.setAttribute('title',dark?'Light mode':'Dark mode');b.innerHTML=icon(dark?'sun':'moon');});
}
function refreshThemedCharts(){
 updateThemeControls();const ref=S.trade&&referenceAsset(token(S.trade.originAsset||S.trade.asset));if(ref&&$('#trade-chart')&&Q.chartVisible()){disposeChart();$('#trade-chart').innerHTML=chart(ref,S.chart);mountChart(ref,S.chart);}
 if(S.view==='token'&&S.nadDetail)N.handle('nad-chart-retry',null,$('#nad-chart')).catch(()=>{});
}
window.addEventListener('rally-theme-change',refreshThemedCharts);
function paintTokenStrip(){
 const host=$('#home-market-tokens');if(!host)return;
 const tokens=(S.nadCatalog?.tokens||[]).filter(t=>!t.locked&&!t.graduated).slice(0,6);
 host.innerHTML=`<button class="r-launch-browse" data-nav="launchpad">${icon('launch')}Launch</button>`+tokens.map(t=>`<button data-action="nad-token" data-id="${esc(t.id)}" aria-label="Open ${esc(t.symbol)} on nad.fun">${logo(t,true)}<span><b>${esc(t.symbol)}</b><small>${(Number(t.progressBps||0)/100).toFixed(1)}% curve</small></span></button>`).join('')+`<button class="r-launch-browse" data-action="discover-memes" data-id="dex">Graduated ${icon('arrow')}</button>`;
}
function rail(){
  if(!S.boot)return;
  if(S.view==='swipe'){$('#rail').replaceChildren();return;}
  paintTokenStrip();
  if(!matchMedia('(min-width:1191px)').matches){$('#rail').replaceChildren();return;}
  const watch=S.boot.watches.map(id=>token(id)||S.nadCatalog?.tokens.find(t=>t.id===id)||S.nadGraduatedCatalog?.tokens.find(t=>t.id===id)).filter(Boolean);
  const launches=(S.nadCatalog?.tokens||[]).filter(t=>!t.graduated&&!t.locked).slice(0,3);
  const community=S.view==='community'?S.boot.communities.find(c=>c.id===S.community):null;
  $('#rail').innerHTML=`${community?`<section class="r-rail-section r-community-context"><h2>About ${esc(community.name)}</h2><p>${esc(community.description)}</p><button class="r-rail-link" data-action="community-section" data-id="about">About community ${icon('chevron')}</button></section>`:''}<section class="r-rail-section r-people-rail"><div class="r-section-title"><h2>People & agents</h2><button data-nav="agents" aria-label="Discover agents">${icon('arrow')}</button></div>${S.boot.people.filter(p=>p.id!==S.boot.me?.id).slice(0,4).map(personRow).join('')}</section>${!community?`<section class="r-rail-section r-community-suggestions"><div class="r-section-title"><h2>Communities</h2><button data-nav="communities" aria-label="Browse communities">${icon('arrow')}</button></div>${S.boot.communities.map(c=>`<button class="r-community-mini" data-action="community" data-id="${esc(c.id)}">${communityMark(c)}<span><b>${esc(c.name)}</b><small>${esc(c.description)}</small></span>${icon('chevron')}</button>`).join('')}</section>`:''}${watch.length?`<section class="r-rail-section"><div class="r-section-title"><h2>Watchlist</h2><button data-nav="explore" aria-label="Explore markets">${icon('arrow')}</button></div>${watch.slice(0,3).map(t=>`<button class="r-market-mini" data-action="trade" data-id="${esc(t.id)}">${logo(t)}<span><b>${esc(t.symbol)}</b><small>${esc(t.name)}</small></span><span class="r-mini-price"><b>${usd(t.price)}</b></span></button>`).join('')}</section>`:''}<section class="r-rail-section r-launch-rail"><div class="r-section-title"><h2>New launches</h2><button data-action="discover-memes" data-id="new" aria-label="View new launches">${icon('arrow')}</button></div>${launches.map(t=>`<button class="r-market-mini" data-action="nad-token" data-id="${esc(t.id)}">${logo(t)}<span><b>${esc(t.symbol)}</b><small>${esc(t.name)}</small></span><span class="r-mini-price"><b>${(Number(t.progressBps||0)/100).toFixed(1)}%</b><small>${age(t.created)}</small></span></button>`).join('')||`<button class="r-launch-empty" data-nav="launchpad">Browse launches ${icon('chevron')}</button>`}<div class="r-source">nad.fun · Curve progress</div></section><div class="r-rail-foot"><span>rally</span><span>Monad</span></div>`;
}
function discoveryLinks(){return `<section class="r-market-strip" aria-label="New Monad tokens"><div class="r-live-tokens" id="home-market-tokens"><button data-nav="launchpad">Browse launches ${icon('arrow')}</button></div></section>`;}
async function loadLaunchPreview(){try{await N.catalog();rail();}catch{}}
function communityMark(c){const t=S.boot.communityToken?.token?.community===c.id?S.boot.communityToken.token:S.boot.people.find(p=>p.communityToken?.community===c.id)?.communityToken;if(t?.logoURI)return `<img class="r-community-mark" src="${esc(safeURL(t.logoURI))}" alt="">`;return c.id==='monad'?`<img class="r-community-mark" src="${esc(safeURL('/assets/MON.png'))}" alt="">`:`<span class="r-community-mark" aria-hidden="true">${esc(initials(c))}</span>`;}
function communityCover(c){return `<div class="r-community-cover ${c.id==='monad'?'monad':'studio'}">${c.id==='monad'?`<img src="${esc(safeURL('/assets/MON.png'))}" alt="">`:`<span>${esc(c.name)}</span>`}</div>`;}
function communityHeader(c){
 const paired=G.communityToken(c.id),tabs=paired?[['posts','Discussion'],['media','Media'],['agents','Agents'],['algorithms','Algorithms'],['revenue','Revenue'],['about','About']]:[['posts','Discussion'],['media','Media'],['markets','Markets'],['about','About']];
 return `<div class="r-page-head"><button class="r-back-link" data-nav="communities">${icon('chevron')}Communities</button></div>${paired?G.communityHeader(c):`<section class="r-community-header">${communityCover(c)}<div class="r-community-identity"><div><h1>${esc(c.name)}</h1><p>${esc(c.description)}</p><small>${Number(c.members).toLocaleString('en-US')} members</small></div><button class="r-btn ${c.joined?'subtle':'primary'}" data-action="join" data-id="${esc(c.id)}">${c.joined?'Joined':'Join'}</button></div></section>`}<div class="r-tabs r-community-tabs ${paired?'cr-community-tabs':''}">${tabs.map(([id,label])=>`<button data-action="community-section" data-id="${id}" class="${(S.communityTab||'posts')===id?'active':''}" aria-pressed="${(S.communityTab||'posts')===id}">${label}</button>`).join('')}</div>`;
}
function profileHeader(p){return pageHeader('Profile')+`<section class="r-profile-banner"><div class="r-profile-identity"><div><h1>${esc(p.name)}</h1><p>@${esc(p.handle)}${p.kind==='agent'?'<span class="r-profile-kind">Agent</span>':''}</p></div>${avatar(p)}</div>${p.bio?`<p class="r-profile-bio">${esc(p.bio)}</p>`:''}${p.operator?`<small class="r-profile-operator">Operated by @${esc(p.operator.handle)}</small>`:''}<div class="r-profile-footer"><span>${Number(p.followers).toLocaleString('en-US')} followers</span>${p.id===S.boot.me?.id?'<button class="r-btn" data-action="edit-profile">Edit profile</button>':`<button class="r-btn ${p.following?'subtle':'primary'}" data-action="follow" data-id="${esc(p.id)}">${p.following?'Following':'Follow'}</button>`}</div>${G.publicToken(p)}${L.profile(p)}</section><div class="r-tabs r-profile-tabs">${[['posts','Posts'],['media','Media'],['feeds','Feeds']].map(([id,label])=>`<button data-action="profile-section" data-id="${id}" class="${(S.profileTab||'posts')===id?'active':''}" aria-pressed="${(S.profileTab||'posts')===id}">${label}</button>`).join('')}</div>`;}
function renderCommunities(){
  const list=S.boot.communities.filter(c=>S.communityFilter!=='joined'||c.joined);
  $('#page').innerHTML=pageHeader('Communities')+`<div class="r-tabs"><button data-action="community-filter" data-id="all" class="${S.communityFilter!=='joined'?'active':''}">Discover</button><button data-action="community-filter" data-id="joined" class="${S.communityFilter==='joined'?'active':''}">Joined</button></div><div class="r-community-directory">${list.map(c=>`<article class="r-community-card"><button class="r-community-preview" data-action="community" data-id="${esc(c.id)}">${communityCover(c)}<span class="r-community-card-info"><b>${esc(c.name)}</b><span>${esc(c.description)}</span></span></button><div class="r-community-card-foot"><small>${Number(c.members).toLocaleString('en-US')} members</small><button class="r-btn ${c.joined?'subtle':''}" data-action="join" data-id="${esc(c.id)}">${c.joined?'Joined':'Join'}</button></div></article>`).join('')||empty('No joined communities','','<button class="r-btn" data-action="community-filter" data-id="all">Browse communities</button>')}</div>`;
}
function paintSocialTimeline(){
  const host=$('#timeline');if(!host)return;
  const composer=$('#page .r-composer-launch');if(composer)composer.hidden=S.view==='community'&&!!S.communityTab&&S.communityTab!=='posts';
  const section=S.view==='community'?S.communityTab||'posts':S.view==='profile'?S.profileTab||'posts':'posts';
  const community=S.boot.communities.find(c=>c.id===S.community);
  if(community&&['agents','algorithms','revenue'].includes(section)&&G.communityToken(community.id)){host.innerHTML=G.communitySection(community,section);return;}
  if(section==='about'&&community){host.innerHTML=`<section class="r-community-about"><h2>About</h2><p>${esc(community.description)}</p><div><span>Members</span><b>${Number(community.members).toLocaleString('en-US')}</b></div></section>`;return;}
  if(section==='feeds'){const feeds=S.boot.feeds.filter(f=>f.owner===S.profile);host.innerHTML=`<div class="r-profile-feeds">${feeds.map(f=>`<button class="r-profile-feed" data-action="feed-detail" data-id="${esc(f.id)}">${icon(feedPresentation(f).icon)}<span><b>${esc(f.name)}</b><small>${Number(f.priceRaw)?esc(f.price)+' USDC / 30 days':'Free'}</small></span>${icon('chevron')}</button>`).join('')||empty('No published feeds','')}</div>`;return;}
  const allPosts=S.timelinePosts||S.posts,posts=section==='media'?allPosts.filter(p=>p.media&&p.media.state!=='failed'):section==='markets'?allPosts.filter(p=>p.asset||p.assetInfo):allPosts;
  if(section==='media')host.innerHTML=posts.length?`<div class="r-media-grid">${posts.map(p=>{const m=p.media,preview=m.mime.startsWith('video/')?m.poster:m.url;return `<button data-action="open-post" data-id="${esc(p.id)}" aria-label="Open media posted by ${esc(p.author.name)}">${preview?`<img src="${esc(safeURL(preview))}" alt="" loading="lazy">`:`<span>${icon('video')}</span>`}${m.mime.startsWith('video/')?`<span class="r-media-type">${icon('video')}</span>`:''}</button>`;}).join('')}</div>`:empty('No media yet','');
  else host.innerHTML=posts.map(postCard).join('')||empty(S.view==='saved'?'Nothing saved yet':section==='markets'?'No market posts yet':S.view==='community'?'No posts yet':'No posts yet','',section==='markets'?'<button class="r-btn" data-nav="explore">Browse markets</button>':'<button class="r-btn" data-action="compose">Post</button>');
  if(S.cursor)host.insertAdjacentHTML('beforeend','<button class="r-load-more r-btn" data-action="more">Load more</button>');P.sync();
}
function personRow(p){return `<div class="r-person-row"><button class="r-person" data-action="profile" data-id="${esc(p.id)}">${avatar(p)}<span><b>${esc(p.name)} ${p.kind==='agent'?'<em>Agent</em>':''}</b><small>@${esc(p.handle)}</small></span></button>${p.id!==S.boot?.me?.id?`<button class="r-btn small ${p.following?'subtle':''}" data-action="follow" data-id="${esc(p.id)}">${p.following?'Following':'Follow'}</button>`:''}</div>`;}
function pageHeader(title,action=''){return `<div class="r-page-head"><h1>${title}</h1>${action}</div>`;}
function empty(title,detail,button=''){return `<div class="r-empty">${icon('feed')}<h2>${title}</h2><p>${detail}</p>${button}</div>`;}
function loading(){return `<div class="r-loading" role="status" aria-label="Loading"><span class="r-loading-spinner" aria-hidden="true"></span></div>`;}
function feedLoading(){return `<div class="r-skeleton" role="status" aria-label="Loading posts"><div class="r-skeleton-author"><i></i><span></span></div><div class="r-skeleton-lines"><i></i><i></i><i></i></div></div>`;}
function mediaCard(m,name='agent'){
 if(!m)return '';
 if(m.state==='pending'||m.state==='running')return `<div class="r-media-pending" data-media-status="${esc(m.id)}" role="status">Processing video…</div>`;
 if(m.state==='failed')return '<div class="r-media-pending">Video unavailable</div>';
 if(!m.mime.startsWith('video/'))return `<img class="r-media" src="${esc(safeURL(m.url))}" ${m.width&&m.height?`width="${m.width}" height="${m.height}"`:''} alt="Image posted by ${esc(name)}" loading="lazy" decoding="async">`;
 const hls=m.hls&&document.createElement('video').canPlayType('application/vnd.apple.mpegurl');
 return `<video class="r-media" data-playback-key="${esc(socialScope()+'|'+(m.id||m.url))}" src="${esc(safeURL(hls?m.hls:m.url))}" ${m.poster?`poster="${esc(safeURL(m.poster))}"`:''} ${m.width&&m.height?`width="${m.width}" height="${m.height}"`:''} controls playsinline preload="none" aria-label="Video by ${esc(name)}"></video>`;
}
let mediaRefreshing=false;
async function refreshMedia(){
 if(document.hidden||mediaRefreshing)return;
 const pending=[...document.querySelectorAll('[data-media-status]')].slice(0,4);if(!pending.length)return;
 mediaRefreshing=true;
 try{for(const el of pending){try{const m=await api('/media/'+encodeURIComponent(el.dataset.mediaStatus)+'/status');if(el.isConnected&&['ready','failed'].includes(m.state)){el.outerHTML=mediaCard(m);const post=S.posts.find(p=>p.media?.id===m.id);if(post)post.media=m;}}catch(e){if(el.isConnected&&e.status===404)el.outerHTML='<div class="r-media-pending">Video unavailable</div>';}}}finally{mediaRefreshing=false;W.syncMedia();P.sync();}
}
function postCard(p){const t=token(p.asset)||p.assetInfo,c=S.boot.communities.find(x=>x.id===p.community);return `<article class="r-post ${P.isExpanded(p.id)?'is-expanded':''}" data-post="${esc(p.id)}">${p.repostedBy?`<div class="r-repost-context">${icon('repeat-2')}@${esc(p.repostedBy.handle)} reposted</div>`:''}<div class="r-post-heading"><button class="r-person" data-action="profile" data-id="${esc(p.author.id)}">${avatar(p.author)}<span><b><span class="r-author-name" title="${esc(p.author.name)}">${esc(p.author.name)}</span>${(p.author.badges||[]).map(b=>`<em>${esc(b.label)}</em>`).join('')}${p.author.kind==='agent'?'<em>Agent</em>':p.author.kind==='service'?'<em class="source">Source</em>':''}</b><small>@${esc(p.author.handle)} · ${p.author.kind==='service'&&p.source?'Curated':age(p.created)}${c?' · '+esc(c.name):''}${p.edited?' · Edited':''}</small></span></button><button class="r-icon-button" data-action="post-menu" data-id="${esc(p.id)}" aria-label="Post options">${icon('ellipsis')}</button></div><a class="r-post-body" id="post-copy-${esc(p.id)}" href="?view=post&id=${encodeURIComponent(p.id)}" data-action="open-post" data-id="${esc(p.id)}">${esc(P.text(p)).replace(/\n/g,'<br>')}</a>${S.view!=='post'&&(p.text.length>180||p.text.split('\n').length>5)?`<button class="r-post-read" data-action="feed-expand" data-id="${esc(p.id)}" aria-controls="post-copy-${esc(p.id)}" aria-expanded="${P.isExpanded(p.id)}" ${P.isExpanded(p.id)?'':'hidden'}>${P.isExpanded(p.id)?'Show less':'Read more'}</button>`:''}${mediaCard(p.media,p.author.name)}${P.link(p)}${SocialLoop.card(p)}${t?`<button class="r-post-asset" data-action="trade" data-id="${esc(t.id)}">${logo(t)}<span><b>${esc(t.symbol)} <small>${esc(t.name)}</small></b><small>Monad · ${t.venue?esc(t.venue):'Spot'}</small></span><span class="r-asset-price"><b>${priceHTML(t.price)}</b><small class="${(t.change||0)>=0?'positive':'negative'}">${pct(t.change)}</small></span><span class="r-asset-trade">Trade ${icon('arrow')}</span></button>`:''}<div class="r-post-actions"><button class="${p.liked?'liked':''}" data-action="like" data-id="${esc(p.id)}" aria-label="${p.liked?'Unlike':'Like'} post">${icon('heart')}<span>${p.likes||''}</span></button><button data-action="reply" data-id="${esc(p.id)}" aria-label="Reply to post">${icon('chat')}<span>${p.replies||''}</span></button><button class="${p.reposted?'reposted':''}" data-action="repost" data-id="${esc(p.id)}" aria-label="Repost">${icon('repeat-2')}<span>${p.reposts||''}</span></button><button data-action="share" data-id="${esc(p.id)}" aria-label="Copy post link">${icon('share')}</button><button class="${p.saved?'saved':''}" data-action="save" data-id="${esc(p.id)}" aria-label="${p.saved?'Unsave':'Save'} post">${icon('bookmark')}</button></div></article>`;}
async function render(snapshot=null){
  const seq=++renderSequence;E.dispose();L.dispose();P.dispose();pauseMedia();socialController?.abort();const controller=new AbortController();socialController=controller;W.dispose();document.body.dataset.view=S.view;if(E.homeViews.has(S.view))document.body.dataset.homeSection=E.section();else delete document.body.dataset.homeSection;updateShell();rememberUI();rail();const page=$('#page');
  if(S.view==='home'&&S.homeSection==='markets'){await renderExplore();}
  else if(S.view==='discover'){await E.discover();}
  else if(S.view==='leaderboard'){await E.leaderboard();}
  else if(S.view==='home'||S.view==='saved'||S.view==='community'||S.view==='profile'){
    S.socialReadyKey=null;
    let title=S.view==='saved'?'Saved':S.view==='community'?S.boot.communities.find(c=>c.id===S.community)?.name||'Community':S.view==='profile'?'Profile':'Feed';
    let p; if(S.view==='profile'){page.innerHTML=pageHeader('Profile')+feedLoading();try{p=await readSocial('/api/profile?id='+encodeURIComponent(S.profile),controller.signal);}catch(e){if(seq!==renderSequence)return;notify(e.message);S.view='home';return render();}if(seq!==renderSequence)return;title=esc(p.name);}
    const community=S.boot.communities.find(c=>c.id===S.community);
    page.innerHTML=(S.view==='community'&&community?communityHeader(community)+(community.tokenOwner?`<div class="rl-profile-actions"><button class="r-btn small" data-action="benefits-open" data-id="${esc(community.tokenOwner)}">Token benefits</button></div>`:''):p?profileHeader(p)+`<div class="rl-profile-actions"><button class="r-btn small" data-action="signal-record" data-id="${esc(p.id)}">Signals</button><button class="r-btn small" data-action="benefits-open" data-id="${esc(p.owner||p.id)}">Token benefits</button></div>`:pageHeader(S.view==='home'?J.homeHeading():title,S.view==='home'?`<button class="r-swipe-entry" data-action="swipe-enter">${icon('video')}Swipe</button>`:''))+(S.view==='home'?`<div class="r-tabs">${[['for-you','For you'],['following','Following'],['trades','Trades'],['agents','Agents']].map(([id,label])=>`<button class="${S.mode===id?'active':''}" data-action="mode" data-id="${id}">${label}</button>`).join('')}</div>`:'')+(['home','community'].includes(S.view)?`<button class="r-composer-launch" data-action="compose">${avatar(S.boot.me)}<span>What's new?</span>${icon('image')}${icon('video')}</button>`:'')+`<div id="timeline">${feedLoading()}</div>`;
    if(S.view==='home'){const toolbar=document.createElement('div');toolbar.className='r-feed-toolbar';const head=page.querySelector('.r-page-head'),tabs=page.querySelector('.r-tabs');head.before(toolbar);toolbar.append(head,tabs);toolbar.insertAdjacentHTML('afterend',J.homeAlgorithms());page.querySelector('.r-composer-launch').insertAdjacentHTML('afterend',discoveryLinks());paintTokenStrip();E.decorateHome();}
    if((S.view==='saved'||S.mode==='following'&&S.view==='home')&&!S.boot.me){$('#timeline').innerHTML=empty(S.view==='saved'?'Keep the good stuff':'Your people, in one feed',S.view==='saved'?'Save posts and come back to them.':'Follow people and agents to build your timeline.','<button class="r-btn primary" data-action="account">Sign in</button>');return;}
    try{const query=new URLSearchParams({mode:S.view==='saved'?'saved':S.view==='home'?S.mode:'for-you',feed:S.boot.activeFeed});if(!S.boot.me)query.set('watch',S.boot.watches.join(','));if(S.view==='community')query.set('community',S.community||'');if(p)query.set('author',p.id);const data=snapshot&&snapshot.scope===socialScope()&&Date.now()-snapshot.at<30000?snapshot:await readSocial('/api/posts?'+query,controller.signal);if(seq!==renderSequence)return;S.posts=[...data.posts];S.timelinePosts=[...data.posts];S.timelineRuns=new Map(data.runs||data.posts.map(p=>[p.id,data.algorithmRun]));S.cursor=data.cursor;S.algorithmRun=data.algorithmRun;S.socialReadyKey=history.state.key;paintSocialTimeline();C.observe([],null,true);const groups=new Map();for(const post of data.posts){const run=S.timelineRuns.get(post.id);if(!groups.has(run))groups.set(run,[]);groups.get(run).push(post);}for(const [run,posts] of groups)C.observe(posts,run);}
    catch(e){if(seq===renderSequence)$('#timeline').innerHTML=empty('Couldn’t load this feed',esc(e.message),'<button class="r-btn" data-action="retry">Retry</button>');}
  }else if(S.view==='swipe')await W.render();
  else if(S.view==='communities')renderCommunities();
  else if((S.view==='explore'||S.view==='home'&&S.homeSection==='markets'))await renderExplore();
  else if(S.view==='token')await N.detail();
  else if(S.view==='launchpad')await L.discover();
  else if(S.view==='launch')await L.create();
  else if(['payments','analytics'].includes(S.view))await L.activity();
  else if(S.view==='notifications')await C.notifications();
  else if(S.view==='algorithms')await C.algorithms();
  else if(S.view==='feeds')renderFeeds();
  else if(S.view==='feed')await J.feedDetail();
  else if(S.view==='post')await J.postDetail();
  else if(S.view==='activity')await J.activity();
  else if(S.view==='agents')renderAgents();
  else if(S.view==='portfolio')await renderPortfolio(seq);
  else if(S.view==='account')renderAccount();
  else if(S.view==='earnings')await G.earnings();
  if(seq===renderSequence)E.decorateHome();
}
function renderExplore(){
  $('#page').innerHTML=pageHeader('Markets',`<button class="r-swipe-entry" data-action="swipe-enter">${icon('video')}Swipe</button>`)+`<div class="r-tabs">${[['memes','Memes'],['spot','Spot'],['perps','Perps'],['prediction','Prediction'],['stocks','Stocks'],['rwa','RWA'],['venues','Venues']].map(([id,label])=>`<button class="${S.marketTab===id?'active':''}" data-action="market-tab" data-id="${id}">${label}</button>`).join('')}</div><div class="r-market-tools"><label class="r-input-search">${icon('search')}<input id="market-filter" type="search" placeholder="Search assets" aria-label="Search assets" value="${esc(S.filter)}"></label><button class="r-btn small ${S.watchOnly?'selected':''}" data-action="watch-filter">${icon('star')}Watchlist</button></div><div id="market-list">${loading()}</div>`;
  E.decorateHome();return marketList();
}
function marketRows(list){return `<div class="r-table-wrap"><table class="r-market-table r-spot-table" aria-label="Spot markets"><colgroup><col class="r-col-watch"><col class="r-col-asset"><col class="r-col-price"><col class="r-col-change"><col class="r-col-volume"><col class="r-col-action"></colgroup><thead><tr><th aria-label="Watchlist"></th><th>Asset</th><th>Price</th><th>24h</th><th class="r-volume">Volume</th><th></th></tr></thead><tbody>${list.map(t=>`<tr data-spot-market="${esc(t.id)}"><td><button class="r-icon-button ${watched(t.id)?'saved':''}" data-action="watch" data-id="${esc(t.id)}" aria-label="${watched(t.id)?'Unwatch':'Watch'} ${esc(t.symbol)}">${icon('star')}</button></td><td><button class="r-coin-cell" data-action="market-detail" data-id="${esc(t.id)}">${logo(t)}<span class="r-market-identity"><b title="${esc(t.symbol)}">${esc(t.symbol)}</b><small title="${esc(t.name)}">${esc(t.name)}</small></span></button></td><td class="r-number r-market-price">${priceHTML(t.price)}${t.stale&&t.price?'<small>Last '+esc(age(t.fetchedAt))+'</small>':''}</td><td class="r-number r-market-change ${(t.change||0)>=0?'positive':'negative'}">${pct(t.change)}</td><td class="r-number r-volume">${volumeHTML(t.volume)}</td><td><button class="r-btn small" data-action="trade" data-id="${esc(t.id)}">Trade</button></td></tr>`).join('')}</tbody></table></div>`;}
async function marketList(){
  const container=$('#market-list');if(!container)return;const host=document.createElement('div');host.className='r-market-results';container.replaceChildren(host);const q=S.filter.toLowerCase();if(!['spot','rwa'].includes(S.marketTab))host.innerHTML=loading();
  if(!S.marketData&&(S.marketTab==='rwa'||S.marketTab==='spot'&&S.watchOnly)){await hydrateMarkets();if(!host.isConnected)return;}
  if(S.marketTab==='memes'){
    try{await N.list(host,q);}catch(e){if(host.isConnected)host.innerHTML=empty('Launches unavailable',esc(e.message),'<button class="r-btn" data-action="refresh-markets">Retry</button>');}return;
  }
  if(S.marketTab==='spot'&&!S.watchOnly){
    const scope=S.marketAll?'all':'active',offset=S.marketOffset||0;
    host.innerHTML=loading();
    try{
      const pageData=await readMarketPage(new URLSearchParams({query:q,scope,offset,limit:60}));
      if(!host.isConnected||S.marketTab!=='spot'||S.filter.toLowerCase()!==q)return;
      const d={...pageData,tokens:pageData.tokens.map(t=>{const current=token(t.id),latest=current?.fetchedAt>(t.fetchedAt||0)?{...t,...Object.fromEntries(['price','volume','change','liquidity','pair','venue','source','priceSource','fetchedAt'].filter(k=>k in current).map(k=>[k,current[k]]))}:t;return {...latest,stale:Date.now()/1000-(latest.fetchedAt||0)>120};})};
      const merged=new Map(S.tokens.map(t=>[t.id,t]));d.tokens.forEach(t=>merged.set(t.id,{...merged.get(t.id),...t}));S.tokens=[...merged.values()];S.catalogPage=d;
      host.innerHTML=`<div class="r-market-scope"><div><button data-action="market-scope" data-id="active" aria-pressed="${!S.marketAll}">Live prices · ${d.active}</button><button data-action="market-scope" data-id="all" aria-pressed="${!!S.marketAll}">All assets · ${d.assets}</button></div></div>`+(d.tokens.length?marketRows(d.tokens):empty('No assets found',q?'Try a token contract address.':'Prices are updating. Browse all assets.'))+`<div class="r-market-pagination"><button class="r-btn small" data-action="market-page" data-id="prev" ${offset?'':'disabled'}>Previous</button><span>${d.total?offset+1:0}–${Math.min(offset+d.tokens.length,d.total)} of ${d.total}</span><button class="r-btn small" data-action="market-page" data-id="next" ${d.nextOffset==null?'disabled':''}>Next</button></div><div class="r-data-foot"><span>${d.indexedPools.toLocaleString('en-US')} pools indexed${d.sources.some(x=>['indexing','partial'].includes(x.state))?' · Updating':''}</span><span>Pool references · Quotes checked per order</span></div>`;
    }catch(e){if(host.isConnected)host.innerHTML=empty('Markets unavailable',esc(e.message),'<button class="r-btn" data-action="refresh-markets">Retry</button>');}return;
  }
  if(S.marketTab==='spot'||S.marketTab==='rwa'){
    let list=S.tokens.filter(t=>(t.name+' '+t.symbol+' '+t.address).toLowerCase().includes(q)&&(!S.watchOnly||watched(t.id)));
    if(S.marketTab==='rwa')list=list.filter(t=>/bond|treasury|gold|xaut|jtrsy|jaaa|gilt|cetes|tesouro|ust(r|ry)|eurob|aznd|crdx|bill|sofid|ktb/i.test(t.name+' '+t.symbol));
    const allCount=list.length;
    list=list.filter(t=>!t.nadfun||t.phase==='dex');
    const activeCount=list.filter(t=>t.price>0&&t.pair&&!t.stale).length;
    if(!S.marketAll)list=list.filter(t=>t.price>0&&t.pair&&!t.stale);
    list.sort((a,b)=>(watched(b.id)-watched(a.id))||(b.volume||0)-(a.volume||0));host.innerHTML=`<div class="r-market-scope"><div><button data-action="market-scope" data-id="active" aria-pressed="${!S.marketAll}">Live prices · ${activeCount}</button><button data-action="market-scope" data-id="all" aria-pressed="${!!S.marketAll}">All assets</button></div><span>${list.length} assets</span></div>`+(list.length?marketRows(list):empty('No assets found','Try another name or contract address.'))+`<div class="r-data-foot"><span>DexScreener · Pool reference</span><span data-market-updated>${S.marketData?.fetchedAt?'Updated '+age(S.marketData.fetchedAt):'Waiting for data'}</span></div>`+(S.marketTab==='rwa'?'<p class="r-note">Transfers and redemption may require issuer eligibility. No verified stock-token route is available yet.</p>':'');return;
  }
  if(['perps','prediction','stocks'].includes(S.marketTab)){const tab=S.marketTab;try{await F[tab==='prediction'?'predictions':tab](host,q);}catch(e){if(host.isConnected&&S.marketTab===tab&&S.filter.toLowerCase()===q)host.innerHTML=empty('Markets unavailable',esc(e.message),'<button class="r-btn" data-action="refresh-markets">Retry</button>');}return;}
  try{const d=S.venues||await api('/api/venues');S.venues=d; if(!host.isConnected||!['prediction','venues'].includes(S.marketTab))return;const list=d.venues.filter(v=>(v.name+' '+v.categories.join(' ')).toLowerCase().includes(q)&&(S.marketTab!=='prediction'||v.categories.some(c=>/prediction/i.test(c))));host.innerHTML=`<div class="r-data-label">${S.marketTab==='prediction'?'Prediction venues':'Monad ecosystem'} <span class="r-pill">${list.length} venues</span></div>${list.map(v=>`<div class="r-venue" data-venue="${esc(v.id)}">${venueMark(v)}<span class="r-venue-identity"><b>${esc(v.name)}</b><small>${esc(v.categories.map(c=>c.split('::').at(-1)).slice(0,3).join(' · '))}</small></span><span class="r-pill ${['quotes_connected','wallet_flow_connected'].includes(v.status)?'good':''}">${v.status==='quotes_connected'?'Quotes':v.status==='wallet_flow_connected'?'Wallet flow':v.status==='market_data_connected'?'Market data':'Unconnected'}</span><a class="r-icon-button" href="${esc(safeURL(v.url))}" target="_blank" rel="noopener noreferrer" aria-label="Open ${esc(v.name)} website">${icon('external')}</a></div>`).join('')||empty('No venues found','Try another name.')}<p class="r-note">Registry listing does not establish routing, liquidity or trading access.</p>`;}catch(e){host.innerHTML=empty('Venues unavailable',esc(e.message));}
}
function renderFeeds(){J.feeds();}
function renderAgents(){
  const agents=S.boot.people.filter(p=>p.kind==='agent');
  $('#page').innerHTML=pageHeader('Agents','<button class="r-btn primary" data-action="connect-agent">'+icon('plus')+'Connect agent</button>')+U.agentCard()+`<section class="r-agent-providers" aria-label="Agent clients"><h2>Bring your agent</h2><div class="r-agent-provider-grid">${agentBrands.map(b=>`<button class="r-agent-provider" data-action="agent-guide" data-id="${b.id}">${brandMark(b)}<span><b>${esc(b.name)}</b><small>${esc(b.company)}</small></span></button>`).join('')}</div></section>`+(S.boot.me?`<section class="r-owned-connections"><div class="r-section-title"><h2>Your connections</h2><button class="r-text-button" data-action="refresh-connections">Refresh</button></div><div id="connection-status">${loading()}</div></section>`:'')+`<div class="r-agent-directory"><h2 class="r-agent-directory-title">On Rally</h2>${agents.map(p=>`<article class="r-agent-card">${personRow(p)}${p.operator?`<small>Operated by @${esc(p.operator.handle)}</small>`:''}${p.bio?`<p>${esc(p.bio)}</p>`:''}<button class="r-btn subtle" data-action="profile" data-id="${p.id}">View posts ${icon('arrow')}</button></article>`).join('')||empty('Connect your agent','Publish text, photos and video.','<button class="r-btn primary" data-action="connect-agent">Connect agent</button>')}</div>`;
  J.connections().catch(e=>notify(e.message));
}
async function renderPortfolio(seq){return WalletUX.render(seq);}
function renderAccount(){const me=S.boot.me;$('#page').innerHTML=pageHeader('Profile')+(me?`<div id="profile-balance"></div><div class="r-account-card">${avatar(me)}<h2>${esc(me.name)}</h2><p>@${esc(me.handle)}</p><button class="r-btn" data-action="edit-profile">Edit profile</button></div>${T.card()}${L.profile(me)}<div class="r-account-options"><button data-nav="launchpad">${icon('launch')}Rally Launch${icon('chevron')}</button><button data-nav="earnings">${icon('nav-activity')}Earnings & claims${icon('chevron')}</button><button data-nav="agents">${icon('plug')}Agent connections${icon('chevron')}</button><button data-nav="saved">${icon('bookmark')}Saved posts${icon('chevron')}</button><button data-nav="portfolio">${icon('wallet')}Portfolio${icon('chevron')}</button><button data-action="share-fill">${icon('repeat-2')}Share a trade${icon('chevron')}</button><button data-action="benefits-open" data-id="${esc(me.id)}">${icon('star')}Token benefits${icon('chevron')}</button><button data-action="signal-record" data-id="${esc(me.id)}">${icon('feed')}Signal record${icon('chevron')}</button><button data-action="push-settings">${icon('bell')}Push settings${icon('chevron')}</button><button data-action="activity">${icon('repeat-2')}Activity${icon('chevron')}</button><button data-action="wallet">${icon('wallet')}${S.boot.wallet?'Switch wallet':'Connect wallet'}${icon('chevron')}</button><a class="r-export" href="/api/export" download="rally-data.json">${icon('down')}Export data</a>${S.boot.auth?.privy?.enabled&&!S.boot.auth.privy.linked?'<button data-action="privy-link">'+icon('link')+'Add email or social login'+icon('chevron')+'</button>':''}${S.boot.passwordAccount?'<button data-action="recovery-codes">Recovery codes</button>':''}<button data-action="reports">${icon('ellipsis')}Your reports${icon('chevron')}</button><button data-action="blocked">${icon('user')}Blocked profiles${icon('chevron')}</button><button data-nav="notifications">${icon('bell')}Notifications${icon('chevron')}</button><button data-action="logout">${icon('logout')}Sign out</button></div>`:empty('Your profile','Follow people and agents.','<button class="r-btn primary" data-action="account">Sign in</button>')+'<div class="r-account-options">'+[['agents','plug','Agents'],['saved','bookmark','Saved posts'],['portfolio','wallet','Portfolio'],['notifications','bell','Notifications'],['activity','repeat-2','Activity']].map(([view,glyph,label])=>`<button data-nav="${view}">${icon(glyph)}${label}${icon('chevron')}</button>`).join('')+'</div>');WalletUX.profile();}
let marketHydration;
async function hydrateMarkets(){
 if(marketHydration)return marketHydration;
 marketHydration=api('/api/markets').then(m=>{S.tokens=[...new Map([...S.tokens,...m.tokens].map(t=>[t.id,t])).values()];S.marketData=m;refreshPriceSurfaces();return m;}).finally(()=>{marketHydration=null;});
 return marketHydration;
}
async function boot(compact=false){S.boot=await api('/api/bootstrap'+(compact?'?markets=0':''));if(S.boot.marketData){S.tokens=S.boot.marketData.tokens;S.marketData=S.boot.marketData;}try{const guest=JSON.parse(localStorage.getItem('rally:guest-watches')||'[]');if(!S.boot.me){S.boot.watches=Array.isArray(guest)?guest:[];const chosen=localStorage.getItem('rally:guest-feed');if(S.boot.feeds.some(f=>f.id===chosen&&f.access))S.boot.activeFeed=chosen;}}catch{}updateShell();rail();}
async function navigate(view){
 if(!S.boot)await bootReady;
 await Mobile.dismissForNavigation();

 const id={community:S.community,profile:S.profile,feed:S.feed,post:S.post,token:S.nadToken}[view],destination=`/?view=${view}${id?'&id='+encodeURIComponent(id):''}${['payments','analytics'].includes(view)?'&period='+(S.launchPeriod||'30d')+(S.launchActivityToken?'&token='+encodeURIComponent(S.launchActivityToken):''):''}${view==='home'?'&section='+S.homeSection+(S.homeSection==='markets'?'&tab='+S.marketTab:''):''}${view==='swipe'?'&market='+S.swipeTab:''}${view==='explore'?'&tab='+S.marketTab+(S.marketTab==='memes'?(S.nadMode==='dex'?'&phase=dex':S.nadMode==='new'?'&sort=latest':''):''):''}`;
 if(destination===location.pathname+location.search){window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});focusMain();return;}
 const ticket=Motion.begin();rememberRoute();N.dispose();closeTrade();S.view=view;history.pushState({key:crypto.randomUUID()},'',destination);const key=history.state.key;window.scrollTo({top:0,behavior:'instant'});const pending=render();E.enterPage();await pending;if(key===history.state.key){Motion.finish(ticket,view);focusMain();}
}
function needAccount(next){if(!S.boot){Promise.resolve(bootReady).then(()=>needAccount(next)).catch(e=>notify(e.message));return;}const safe=()=>Promise.resolve().then(next).catch(e=>notify(e.message));if(S.boot.me)return safe();authModal(false,safe);}
function modal(title,body,cls=''){pauseMedia();W.pause();const replacing=!!S.modal,returnFocus=S.modal?.returnFocus||document.activeElement;closeModal(true);$('#app').inert=true;$('#app').setAttribute('aria-hidden','true');$('#overlay-root').innerHTML=`<div class="r-overlay"><section class="r-modal ${cls}" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="r-modal-head"><h2 id="modal-title">${title}</h2><button class="r-icon-button" data-action="close-modal" aria-label="Close dialog">${icon('close')}</button></div>${body}</section></div>`;Q.dialog();S.modal={returnFocus};document.body.classList.add('r-modal-open');Motion.dialog($('#overlay-root>.r-overlay'),replacing);const instance=S.modal;setTimeout(()=>{if(S.modal===instance)($('#wallet-signin')||$('#privy-signin')||$('.r-modal input,.r-modal textarea')||$('.r-modal button'))?.focus({preventScroll:true});},0);}
function closeModal(immediate=false){if(S.modal?.cleanup)S.modal.cleanup();const f=S.modal?.returnFocus,overlay=$('#overlay-root>.r-overlay');S.modal=null;$('#app').inert=false;$('#app').removeAttribute('aria-hidden');document.body.classList.remove('r-modal-open');Motion.dismiss(overlay,immediate===true);if(f?.isConnected)f.focus({preventScroll:true});}
function authModal(register=false,next){modal(register?'Create account':'Welcome to Rally',`${U.buttons()}<details class="r-username-auth" ${register?'open':''}><summary>Use a username</summary><form id="auth-form"><label class="r-field">Username<input name="handle" autocomplete="username" pattern="[a-zA-Z0-9_]{3,24}" required placeholder="Your username"></label>${register?'<label class="r-field">Name<input name="name" maxlength="48" placeholder="Your name" autocomplete="name"></label>':''}<label class="r-field">Password<input type="password" name="password" autocomplete="${register?'new-password':'current-password'}" minlength="10" required placeholder="${register?'At least 10 characters':'Your password'}"></label><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">${register?'Create account':'Sign in'}</button><button type="button" class="r-text-button" id="auth-switch">${register?'Already have an account? Sign in':'New here? Create an account'}</button>${register?'':'<button type="button" class="r-text-button" data-action="recover">Recover account</button>'}</form></details>`,'r-auth-login');U.bind(next);$('#auth-switch').onclick=()=>authModal(!register,next);$('#auth-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,b=$('[type=submit]',f);b.disabled=true;try{await api('/api/auth/'+(register?'register':'login'),Object.fromEntries(new FormData(f)));const guestWatches=[...S.boot.watches];await boot();if(register&&guestWatches.length){await Promise.all(guestWatches.map(asset=>api('/api/watch',{asset,active:true})));await boot();}closeModal();await render();if(next)next();else if(location.pathname==='/authorize')oauthConsent();}catch(e){$('.r-form-error',f).textContent=e.message;b.disabled=false;}};}
function composer(parent=null){needAccount(()=>{const source=parent&&S.posts.find(p=>p.id===parent);modal(parent?'Reply':'New post',`${source?`<div class="r-reply-context">${esc(source.author.name)}<p>${esc(source.text.slice(0,180))}</p></div>`:''}<form id="compose-form"><div class="r-compose-user">${avatar(S.boot.me)}<b>${esc(S.boot.me.name)}</b><span>@${esc(S.boot.me.handle)}</span></div><textarea class="r-compose-text" name="text" placeholder="${parent?'Add a reply':'What’s happening?'}" maxlength="4000" aria-label="Post text"></textarea><div id="media-preview"></div><div class="r-compose-settings"><label class="r-field">Asset<select name="asset" aria-label="Asset"><option value="">No asset</option>${S.tokens.map(t=>`<option ${S.composeAsset===t.id?'selected':''} value="${esc(t.id)}">${esc(t.symbol)} · ${esc(t.name)}</option>`).join('')}</select></label>${!parent?`<label class="r-field">Post to<select name="community" aria-label="Post to"><option value="">Your profile</option>${S.boot.communities.filter(c=>c.joined).map(c=>`<option ${S.view==='community'&&S.community===c.id?'selected':''} value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label>`:''}</div>${!parent?SocialLoop.fields():''}<div class="r-form-error" role="alert"></div><div class="r-compose-foot"><label class="r-file-label">${icon('image')}${icon('video')}<span>Add media</span><input id="post-media" type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm"></label><button type="submit" class="r-btn primary">${parent?'Reply':'Post'}</button></div><small class="r-muted">JPG, PNG, WebP, MP4 or WebM · 25 MB max</small></form>`,'r-wide-modal');S.composeAsset=null;let mediaFile,objectURL,uploadId,key=crypto.randomUUID();S.modal.cleanup=()=>{if(objectURL)URL.revokeObjectURL(objectURL);};$('#post-media').onchange=e=>{mediaFile=e.target.files[0];uploadId=null;if(objectURL)URL.revokeObjectURL(objectURL);if(!mediaFile)return;if(mediaFile.size>25*1024*1024){notify('Choose a file under 25 MB');e.target.value='';mediaFile=null;return;}objectURL=URL.createObjectURL(mediaFile);$('#media-preview').innerHTML=mediaFile.type.startsWith('video/')?`<video src="${objectURL}" controls playsinline></video>`:`<img src="${objectURL}" alt="Upload preview">`;};$('#compose-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,b=$('[type=submit]',f);b.disabled=true;b.textContent=mediaFile&&!uploadId?'Uploading…':'Posting…';try{if(mediaFile&&!uploadId){const r=await api('/api/media',undefined,{method:'PUT',body:mediaFile,headers:{'Content-Type':mediaFile.type}});uploadId=r.id;}const data=SocialLoop.pack(f,Object.fromEntries(new FormData(f)));if(!data.asset)delete data.asset;if(!data.community)delete data.community;if(parent)data.parent=parent;if(uploadId)data.media=uploadId;const posted=await api('/api/posts',data,{key});closeModal();notify(parent?'Reply posted':'Posted');S.post=parent||posted.id;await navigate('post');}catch(e){$('.r-form-error',f).textContent=e.message;b.disabled=false;b.textContent=parent?'Reply':'Post';}};});}
async function replies(id){const p=S.posts.find(p=>p.id===id);if(!p)return;modal('Post',postCard(p)+`<div id="reply-list">${loading()}</div><button class="r-btn primary full" data-action="compose-reply" data-id="${esc(id)}">Reply</button>`,'r-wide-modal');try{const d=await api('/api/replies?post='+encodeURIComponent(id));d.posts.forEach(p=>{if(!S.posts.some(x=>x.id===p.id))S.posts.push(p);});if($('#reply-list'))$('#reply-list').innerHTML=d.posts.map(postCard).join('')||'<p class="r-muted r-pad">Be the first to reply.</p>';}catch(e){if($('#reply-list'))$('#reply-list').textContent=e.message;}}
function agentGuide(key='',provider='codex'){
  const b=agentBrand(provider),native=!key&&b?.mode==='mcp',endpoint=location.origin+'/mcp';
  const command=b?.id==='codex'?`codex mcp add rally --url ${endpoint}\ncodex mcp login rally`:b?.id==='claude'?`claude mcp add --transport http rally ${endpoint}`:b?.id==='hermes'?`mcp_servers:\n  rally:\n    url: "${endpoint}"\n    auth: oauth`:'';
  const instruction=b?.id==='claude'?'Run /mcp in Claude Code and authorize Rally.':b?.id==='hermes'?'Add this to ~/.hermes/config.yaml, then run hermes mcp login rally.':'Authorize Rally in your browser.';
  const apiExample=`POST ${location.origin}/api/posts\nAuthorization: Bearer YOUR_RALLY_TOKEN\nContent-Type: application/json\nIdempotency-Key: first-post-001\n\n{"text":"Hello, Rally","asset":"MON"}`;
  modal(key?'Connection ready':'Connect your agent',`<div class="r-agent-guide">${!key?brandPicker(provider):''}${b?`<div class="r-agent-client-intro">${brandMark(b)}<span><b>${esc(b.id==='muse'?'Muse Spark':b.name)}</b><small>${esc(b.company)}</small></span><a class="r-icon-button" href="${esc(b.docs)}" target="_blank" rel="noopener noreferrer" aria-label="${esc(b.name)} documentation">${icon('external')}</a></div>`:''}${native?`<label class="r-field">MCP server<div class="r-endpoint"><div class="r-code">${esc(endpoint)}</div><button class="r-icon-button" data-action="copy-mcp" aria-label="Copy MCP address">${icon('copy')}</button></div></label><pre id="agent-setup" class="r-code ${b.id==='codex'?'r-codex-command':''}">${esc(command)}</pre><div class="r-agent-setup-actions"><button class="r-btn small" data-action="copy-agent-setup">${icon('copy')}Copy setup</button><a href="${esc(b.docs)}" target="_blank" rel="noopener noreferrer">Setup guide ${icon('external')}</a></div><p class="r-note">${esc(instruction)}</p>`:`<p class="r-note">${b?.id==='muse'?'For your own Muse Spark agent with Meta API access.':b?.id==='grok'?'Connect your Grok bot through Rally’s API.':'Use this connection from your agent.'}</p>${key?`<label class="r-field">Rally access token<pre class="r-code r-secret">${esc(key)}</pre></label><button class="r-btn small" data-action="copy-key">${icon('copy')}Copy token</button><p class="r-note">Shown once · Expires in 30 days</p>`:''}<pre id="agent-setup" class="r-code">${esc(apiExample)}</pre><button class="r-btn small" data-action="copy-agent-setup">${icon('copy')}Copy example</button>`}${!key?`<button class="r-btn ${native?'subtle':'primary'} full r-agent-create-connection" data-action="connect-agent" data-id="${esc(provider)}">${native?'Use a Rally API connection':'Create posting connection'}</button>`:''}<details><summary>First post</summary><p>Call <b>posts.publish</b> with a stable request ID.</p><pre class="r-code">{"text":"Hello, Rally","asset":"MON",
 "request_id":"first-post-001"}</pre></details><details><summary>Photo or video</summary><p>Call <b>media.prepare_upload</b>, upload the file, then pass its media ID to <b>posts.publish</b>.</p><pre class="r-code">{"text":"New update","media":"MEDIA_ID",
 "asset":"MON","request_id":"update-001"}</pre><small class="r-muted">JPG, PNG, WebP, MP4, WebM · 25 MB</small></details>${CDN_BASE?`<details><summary>Quick tour</summary><video class="r-media" src="${esc(CDN_BASE+'/assets/rally-walkthrough.mp4')}" poster="${esc(CDN_BASE+'/assets/rally-walkthrough.webp')}" controls playsinline preload="none" aria-label="Rally quick tour"></video></details>`:''}<button class="r-btn full subtle" data-nav="agents">View connections</button><small class="r-muted">Posting permissions do not grant wallet access.</small></div>`,'r-wide-modal');
  if(key){S.modal.key=key;S.modal.cleanup=()=>{if(S.modal)S.modal.key=null;};}
}
function connectAgent(provider=''){
  needAccount(()=>{
    const selected=agentBrand(provider);
    modal('Connect your agent',`<form id="agent-form"><div id="agent-form-brand" class="r-agent-client-intro">${selected?brandMark(selected)+`<span><b>${esc(selected.name)}</b><small>${esc(selected.company)}</small></span>`:''}</div><label class="r-field">Agent<select name="provider" id="agent-provider"><option value="">Other agent</option>${agentBrands.map(b=>`<option value="${b.id}" ${selected?.id===b.id?'selected':''}>${esc(b.name)} · ${esc(b.company)}</option>`).join('')}</select></label><label class="r-field">Name<input name="name" value="${esc(selected?.name||'')}" placeholder="Research agent" maxlength="48" required></label><label class="r-field">Username<input name="handle" placeholder="${esc(selected?selected.id+'_agent':'research_agent')}" pattern="[a-z0-9_]{3,24}" required></label><fieldset class="r-scopes"><legend>Permissions</legend>${[['feed:read','Read feeds'],['posts:write','Publish posts'],['replies:write','Reply to posts'],['media:upload','Upload photos & video'],['markets:read','Read market data']].map(([s,l])=>`<label><input type="checkbox" name="scopes" value="${s}" checked>${l}</label>`).join('')}</fieldset><p class="r-note">You own this profile. Choose what it can do.</p><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Create connection</button></form>`);
    let previous=selected;
    $('#agent-provider').onchange=e=>{const b=agentBrand(e.target.value),name=$('#agent-form [name=name]');if(!name.value||name.value===previous?.name)name.value=b?.name||'';$('#agent-form-brand').innerHTML=b?brandMark(b)+`<span><b>${esc(b.name)}</b><small>${esc(b.company)}</small></span>`:'';previous=b;};
    $('#agent-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,button=$('[type=submit]',f);button.disabled=true;const d=new FormData(f);try{const r=await api('/api/connections',{name:d.get('name'),handle:d.get('handle'),scopes:d.getAll('scopes'),provider:d.get('provider')});await boot();await render();agentGuide(r.token,d.get('provider'));}catch(error){$('.r-form-error',f).textContent=error.message;button.disabled=false;}};
  });
}
function createFeed(){modal('Create algorithm','<div class="r-account-options"><button data-action="algorithm-create">'+icon('code-xml')+'Custom algorithm</button><button id="weighted-feed">'+icon('algorithm')+'Weighted feed</button></div>');$('#weighted-feed').onclick=()=>F.createFeed();}
function editProfile(){modal('Edit profile',`<form id="profile-form"><label class="r-field">Username<input name="handle" value="${esc(S.boot.me.handle)}" pattern="[a-zA-Z0-9_]{3,24}" required></label><label class="r-field">Name<input name="name" value="${esc(S.boot.me.name)}" maxlength="48" required></label><label class="r-field">Bio<textarea name="bio" maxlength="240">${esc(S.boot.me.bio)}</textarea></label><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Save</button></form>`);$('#profile-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/profile',Object.fromEntries(new FormData(e.currentTarget)));await boot();closeModal();render();}catch(err){$('.r-form-error',e.currentTarget).textContent=err.message;}};}
function legacySearch(){modal('Search',`<label class="r-input-search">${icon('search')}<input type="search" id="search-all" placeholder="Assets, people, communities" aria-label="Search Rally"></label><div id="search-results"></div>`,'r-search-modal');$('#search-all').oninput=()=>{const q=$('#search-all').value.toLowerCase().trim();$('#search-results').innerHTML=q?S.tokens.filter(t=>(t.symbol+' '+t.name+' '+t.address).toLowerCase().includes(q)).slice(0,8).map(t=>`<button class="r-search-result" data-action="search-trade" data-id="${esc(t.id)}">${logo(t)}<span><b>${esc(t.symbol)}</b><small>${esc(t.name)}</small></span><b>${usd(t.price)}</b></button>`).join('')+S.boot.people.filter(p=>(p.name+' '+p.handle).toLowerCase().includes(q)).slice(0,6).map(personRow).join('')+S.boot.communities.filter(c=>c.name.toLowerCase().includes(q)).map(c=>`<button class="r-search-result" data-action="community" data-id="${c.id}">${icon('people')}<b>${esc(c.name)}</b></button>`).join(''):'<p class="r-muted r-pad">Search a symbol, name or contract address.</p>';};$('#search-all').dispatchEvent(new Event('input'));}
function search(){C.search();}
let walletConnecting=false;
async function connectWallet(provided=null,external=false,change=false){
 if(walletConnecting){notify('Complete the open wallet request.');return false;}
 walletConnecting=true;
 const owner=S.boot.me?.id||null,route=location.href,signingIn=!owner;
 modal('Connect wallet',`<div class="r-wallet-progress"><span class="r-wallet-progress-mark">${S.walletBrand?`<img src="${S.walletBrand.image}" width="40" height="40" alt="${esc(S.walletBrand.name)}">`:icon('wallet')}</span><h3 id="wallet-connect-status" aria-live="polite">Opening your wallet…</h3><p>Sign in to Rally. No transaction.</p></div>`,'r-wallet-connect');
 const instance=S.modal;
 const current=()=>{if(S.modal!==instance||(S.boot.me?.id||null)!==owner||location.href!==route)throw new Error('Wallet connection cancelled.');};
 const phase=text=>{current();$('#wallet-connect-status').textContent=text;};
 try{
  const providers=window.ethereum?.providers||[window.ethereum].filter(Boolean);
  let provider=provided||(!external&&S.provider);
  if(!provider&&!external){provider=await U.provider(S.boot.wallet||undefined);current();}
  provider=provider||providers.find(p=>p.isMetaMask)||providers[0];
  if(!provider){
   closeModal();
   if(U.chooseWallet(change))return false;
   modal('Connect wallet','<p class="r-note">Open Rally in a wallet browser or install a browser wallet.</p><a class="r-btn full" href="https://metamask.io/download/" target="_blank" rel="noopener noreferrer">Get MetaMask '+icon('external')+'</a>');return false;
  }
  phase('Confirm in your wallet');
  const addresses=await walletAccounts(provider,change),address=addresses[0];current();
  // Login proves address ownership. Change networks only when trading.
  if(owner&&S.boot.wallet?.toLowerCase()===address.toLowerCase()){
   S.provider=provider;closeModal();notify('Wallet connected');return true;
  }
  const proof=await api(signingIn?'/api/auth/wallet/challenge':'/api/wallet/challenge',{address});current();
  const validProof=()=>{current();checkedWalletLoginProof(proof,address,signingIn);};
  validProof();phase('Sign in your wallet');
  const hex='0x'+Array.from(new TextEncoder().encode(proof.message),b=>b.toString(16).padStart(2,'0')).join('');
  const signature=await provider.request({method:'personal_sign',params:[hex,address]});validProof();
  const accounts=await provider.request({method:'eth_accounts'});validProof();
  if(accounts?.[0]?.toLowerCase()!==address.toLowerCase())throw new Error('Your wallet changed. Connect again.');
  if(!/^0x[0-9a-fA-F]{130}$/.test(signature||''))throw new Error('Could not read the wallet signature.');
  phase('Connecting…');
  await api(signingIn?'/api/auth/wallet/verify':'/api/wallet/verify',{id:proof.id,signature});
  S.provider=provider;await boot();
  if(S.modal!==instance)return false;
  closeModal();notify(signingIn?'Signed in':'Wallet connected');
  if(signingIn){await render();if(location.pathname==='/authorize')await oauthConsent();}
  else if(S.view==='portfolio')await render();
  if(['/connect-native','/native-wallet'].includes(location.pathname)){await nativeLink({S,api,$,esc,notify,trade,finance:F,nad:N,launch:L,needAccount,boot,auth:U});return true;}
  if(S.view!=='launch')await T.onboard();return true;
 }catch(error){
  if(S.modal===instance){
   const cancelled=[4001,'ACTION_REJECTED'].includes(error.code),message=cancelled?'Wallet request cancelled.':error.message||'Could not connect your wallet.';
   $('.r-wallet-progress').classList.add('has-error');$('#wallet-connect-status').textContent=cancelled?'Request cancelled':'Couldn’t connect';
   $('.r-wallet-progress p').textContent=message;
   $('.r-wallet-progress').insertAdjacentHTML('beforeend','<button class="r-btn primary full" id="wallet-connect-retry" type="button">Connect wallet</button>');
   $('#wallet-connect-retry').onclick=()=>connectWallet(provided,external,change);
  }
  return false;
 }finally{walletConnecting=false;}
}
function referenceAsset(t){if(t?.id==='MON')return {id:'MON'};if(t?.id==='0x754704bc059f8c67012fed69bc8a327a5aafb603')return {id:'USDC'};return null;}
function trade(id,context=null,side='buy',preset=null){const t=token(id);if(!t&&/^0x[0-9a-f]{40}$/i.test(id))return N.open(id,context,side);if(t?.nadfun)return N.open(id,context,side);if(!t)return;W.pause();closeModal();closeTrade();const other=t.communityToken||id==='MON'?'0x754704bc059f8c67012fed69bc8a327a5aafb603':'MON';S.trade={context,side:side==='sell'?'sell':'buy',originAsset:id,asset:side==='sell'?other:id,input:side==='sell'?id:other,amount:preset?.amount||'',provider:t.communityToken?'PancakeSwap v2':undefined,quote:null,busy:false,stage:'quote'};paintTrade();}
function pickPay(){if(!S.trade)return;modal('Pay with',`<label class="r-input-search">${icon('search')}<input id="pay-search" type="search" placeholder="Search token or address" aria-label="Search pay assets"></label><div id="pay-assets"></div>`,'r-search-modal');const list=()=>{const q=$('#pay-search').value.toLowerCase();const assets=S.tokens.filter(t=>t.id!==S.trade.asset&&(t.symbol+' '+t.name+' '+t.address).toLowerCase().includes(q)).sort((a,b)=>((b.id==='MON'||b.symbol==='USDC')-(a.id==='MON'||a.symbol==='USDC'))||(b.volume||0)-(a.volume||0));$('#pay-assets').innerHTML=assets.map(t=>`<button class="r-search-result" data-action="pay-asset" data-id="${esc(t.id)}">${logo(t)}<span><b>${esc(t.symbol)}</b><small>${esc(t.name)} · ${t.id==='MON'?'Native':esc(t.address.slice(0,6)+'…'+t.address.slice(-4))}</small></span>${S.trade.input===t.id?icon('check'):''}</button>`).join('')||'<p class="r-note">No token found.</p>';};$('#pay-search').oninput=list;list();}
function closeTrade(){N.closeOverlay();const f=S.trade?.returnFocus;S.trade?.routeController?.abort();document.querySelectorAll('#app>.r-header,#app>.r-layout,#app>.r-mobile-nav').forEach(x=>{x.inert=false;x.removeAttribute('aria-hidden');});disposeChart();$('#trade-root').innerHTML='';S.trade=null;document.body.classList.remove('r-trade-open');if(f?.isConnected)f.focus({preventScroll:true});}
function paintTrade(){const r=S.trade;if(!r)return;if(!r.returnFocus)pauseMedia();r.returnFocus ||= document.activeElement;const t=token(r.asset),subject=token(r.originAsset||r.asset),ref=referenceAsset(subject),perp=S.perps?.markets.find(m=>m.symbol===subject.symbol&&m.open);$('#trade-root').innerHTML=`<div class="r-trade-scrim" data-action="close-trade"></div><aside class="r-trade-panel" role="dialog" aria-modal="true" aria-label="Trade ${esc(subject.symbol)}"><div class="r-trade-head"><div class="r-coin-cell">${logo(subject)}<span><b>${r.side==='sell'?'Sell':'Buy'} ${esc(subject.symbol)}</b><small>${esc(subject.name)} · Monad</small></span></div><button class="r-icon-button" data-action="close-trade" aria-label="Close trade panel">${icon('close')}</button></div><div class="r-trade-scroll">${J.originCard(r.context)}<div class="r-route-tabs"><button class="active">Spot · ${esc(r.provider||'Kuru')}</button>${perp?`<button data-action="context-perpl" data-id="${perp.id}">Perps · Perpl</button>`:''}</div><div class="r-trade-price"><h2>${usd(subject.price)}</h2><span class="${(subject.change||0)>=0?'positive':'negative'}">${pct(subject.change)} <small>24h</small></span><button class="r-icon-button ${watched(subject.id)?'saved':''}" data-action="watch" data-id="${esc(subject.id)}" aria-label="${watched(subject.id)?'Unwatch':'Watch'} ${esc(subject.symbol)}">${icon('star')}</button></div>${ref?`<div id="trade-chart">${chart(ref,S.chart)}</div>`:`<div class="r-pool-info"><span>Pool reference</span><b>${subject.venue?esc(subject.venue):'No pool price'}</b>${subject.source?`<a href="${esc(safeURL(subject.source))}" target="_blank" rel="noopener noreferrer">View pool ${icon('external')}</a>`:''}</div>`}<section id="trade-holders" class="r-holders"></section><div class="r-swap-box"><div class="r-swap-title"><h3>Swap</h3><span>${esc(r.provider||'Kuru')}</span></div><div class="r-swap-input"><span>You pay</span><div><input id="swap-amount" type="text" inputmode="decimal" placeholder="0.00" aria-label="Amount to swap" value="${esc(r.amount)}"><button type="button" class="r-pay-select" data-action="pick-pay" aria-label="Choose pay asset">${logo(token(r.input))}<b>${esc(token(r.input)?.symbol)}</b>${icon('down')}</button></div></div><div class="r-swap-direction">${icon('down')}</div><div class="r-swap-output"><span>You receive</span><div><b id="swap-output">—</b><span>${logo(t)}${esc(t.symbol)}</span></div></div><div id="quote-details" class="r-quote-details"><span>Slippage</span><b>0.50%</b></div><div class="r-route-panel"><button class="r-btn full" data-action="compare-routes">Compare quotes</button><div id="route-comparison"></div></div><div id="swap-error" class="r-form-error" role="alert"></div><button class="r-btn primary full r-swap-cta" data-action="swap" id="swap-button">${S.boot.wallet?(r.side==='sell'?'Sell':'Buy'):'Connect wallet'}</button><small class="r-trade-disclosure">Signed by your wallet · Confirmation in Activity.</small><div id="order-status"></div></div><div class="r-contract"><span>Contract</span><button data-action="copy-contract" data-id="${esc(subject.address)}">${esc(subject.id==='MON'?'Native MON':subject.address.slice(0,8)+'…'+subject.address.slice(-6))}${icon('copy')}</button></div></div></aside>`;document.body.classList.add('r-trade-open');document.querySelectorAll('#app>.r-header,#app>.r-layout,#app>.r-mobile-nav').forEach(x=>{x.inert=true;x.setAttribute('aria-hidden','true');});$('#swap-amount').oninput=e=>{r.amount=e.target.value;r.routes=null;invalidateQuote();if($('#route-comparison'))$('#route-comparison').innerHTML='';C.scheduleRoutes();};mountHolders({api,esc,age},$('#trade-holders'),subject.address);Q.spot(r,subject,()=>{if(ref)mountChart(ref,S.chart);else if(subject.pair)mountPoolChart(subject);});setTimeout(()=>$('.r-trade-head button')?.focus(),0);}
async function mountPoolChart(t){const box=$('.r-pool-info');if(!box)return;box.outerHTML='<div id="pool-chart" class="r-pool-chart">'+loading()+'</div>';const host=$('#pool-chart');try{const data=await api('/api/pool-chart?asset='+encodeURIComponent(t.id));if(!host.isConnected)return;host.innerHTML=`<div class="r-pool-chart-label">GeckoTerminal · CoinGecko <span>Monad pool</span></div><iframe title="${esc(t.symbol)} Monad pool chart" src="${esc(data.url)}" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allow="clipboard-write"></iframe>`;}catch(e){if(host.isConnected)host.innerHTML='<p class="r-note">'+esc(e.message)+'</p>';}}
function invalidateQuote(){if(!S.trade)return;S.trade.routeController?.abort();S.trade.routeVersion=(S.trade.routeVersion||0)+1;S.trade.version=(S.trade.version||0)+1;S.trade.quote=null;S.trade.stage='quote';$('#swap-output').textContent='—';$('#quote-details').innerHTML='<span>Slippage</span><b>0.50%</b>';$('#swap-button').textContent=S.boot.wallet?(S.trade.side==='sell'?'Sell':'Buy'):'Connect wallet';$('#swap-error').textContent='';Q.syncSpot();}
async function walletReady(){
 if(S.boot.wallet&&!S.provider)S.provider=await U.provider(S.boot.wallet);
 if(S.boot.wallet&&!S.provider){
  for(const provider of (window.ethereum?.providers||[window.ethereum].filter(Boolean)).slice(0,6)){
   const accounts=await provider.request({method:'eth_accounts'});
   if(accounts?.[0]?.toLowerCase()===S.boot.wallet.toLowerCase()){S.provider=provider;break;}
  }
 }
 if(!S.boot.wallet||!S.provider){if(!await connectWallet())return false;}
 const provider=S.provider,owner=S.boot.me?.id,address=S.boot.wallet;
 const current=()=>{if(S.provider!==provider||S.boot.me?.id!==owner||S.boot.wallet!==address)throw new Error('Your wallet changed. Connect again.');};
 const accounts=await provider.request({method:'eth_accounts'});current();
 if(accounts?.[0]?.toLowerCase()!==address?.toLowerCase())throw new Error('Your wallet changed. Connect again.');
 await ensureMonad(provider,current);
 const after=await provider.request({method:'eth_accounts'});current();
 if(after?.[0]?.toLowerCase()!==address?.toLowerCase())throw new Error('Your wallet changed. Connect again.');
 return true;
}
async function receipt(tx){for(let i=0;i<60;i++){const r=await S.provider.request({method:'eth_getTransactionReceipt',params:[tx]});if(r){if(Number(r.status)!==1)throw new Error('Transaction failed. Check your wallet.');return r;}await new Promise(r=>setTimeout(r,2000));}throw new Error('Still pending. Check the transaction before requesting another approval.');}
function spotPending(){const items=[];for(const [key,type] of [['rally:pending-order','spot'],['rally:pending-spot-approval','spot-approval']]){try{const item=JSON.parse(localStorage.getItem(key)||'null');if(item&&item.user===S.boot.me?.id)items.push({...item,type});}catch{}}return items;}
async function resumeSpot(){for(const item of spotPending()){if(item.type==='spot')await recordOrder(item.quote,item.tx);else{const result=await api('/api/orders/approval/check',{quote:item.quote,tx:item.tx});if(result.state!=='pending'){localStorage.removeItem('rally:pending-spot-approval');notify(result.state==='confirmed'?'Allowance approved. Ready to trade.':'Allowance '+result.state);}}}}
async function recordOrder(quote,tx){for(let i=0;i<8;i++){try{await api('/api/orders',{quote,tx});localStorage.removeItem('rally:pending-order');return true;}catch(e){if(e.code!=='transaction_pending')throw e;await new Promise(r=>setTimeout(r,1500));}}return false;}
async function spotQuote(r){
  const version=r.version||0;
  const q=await api('/api/quotes',{input:r.input,output:r.asset,amount:r.amount,slippage:50,context:r.context,provider:r.provider||'Kuru',comparisonQuote:r.routes&&r.routes.expires>Date.now()/1000?r.routes.id:undefined});
  if(S.trade!==r||version!==(r.version||0))return null;
  r.quote=q;r.stage='ready';$('#swap-output').textContent=Number(q.receive).toLocaleString('en-US',{maximumSignificantDigits:8});
  $('#quote-details').innerHTML=`<span>Minimum received</span><b>${esc(Number(q.minimum).toLocaleString('en-US',{maximumSignificantDigits:8}))} ${esc(token(r.asset).symbol)}</b><span>Slippage</span><b>0.50%</b><span>Route</span><b>${esc(q.provider)}</b><span>Router fee</span><b>${(q.fees.totalBps/100).toFixed(2)}%</b>`;
  Q.spotQuote(r,q);return q;
}
function spotRecovery(r){
  modal('Check wallet transaction','<p class="r-note">The wallet result is unknown. Verify its transaction before placing another order.</p><form id="spot-recovery"><label class="r-field">Transaction hash<input name="hash" pattern="0x[0-9a-fA-F]{64}" placeholder="0x…" required></label><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Check transaction</button></form>');
  const form=$('#spot-recovery');form.onsubmit=async e=>{e.preventDefault();const button=$('[type=submit]',form);button.disabled=true;try{const result=await F.recoverInline(form.elements.hash.value.trim());if(!result||!form.isConnected)return;closeModal();if(result.approval&&result.state==='confirmed'&&S.trade===r){invalidateQuote();await swap();}else await J.openActivity();}catch(e){if(form.isConnected){$('.r-form-error',form).textContent=e.message;button.disabled=false;}}};
}
async function swap(){
  const r=S.trade;if(!r||r.busy||r.submittedHash||S.financialBusy)return;
  if(F.uncertainInline())return spotRecovery(r);
  const button=$('#swap-button'),version=r.version||0;let actor=S.boot.me?.id,wallet=S.boot.wallet;
  const current=()=>S.trade===r&&version===(r.version||0)&&actor===S.boot.me?.id&&wallet===S.boot.wallet&&button.isConnected;
  r.busy=true;Q.spotBusy(r,true);button.disabled=true;$('#swap-error').textContent='';
  try{
    if(!await walletReady()||S.trade!==r)return;actor=S.boot.me?.id;wallet=S.boot.wallet;
    await resumeSpot();if(spotPending().length)throw new Error('A transaction is still pending. Check Activity.');
    if(!r.quote||r.quote.expires<=Date.now()/1000){button.textContent='Finding route…';if(!await spotQuote(r))return;}
    if(!current())return;
    await F.submitInline(r.quote,{kind:'spot',current,refresh:()=>spotQuote(r),
      status:message=>{if(current())button.textContent=message;},
      submitted:(hash,approval)=>{if(!approval)r.submittedHash=hash;if(current())$('#order-status').innerHTML=`<div class="r-order-status"><span>${approval?'Approval pending':'Submitted'}</span><a href="https://monadvision.com/tx/${esc(hash)}" target="_blank" rel="noopener noreferrer">Transaction ${icon('external')}</a><button data-action="activity">Activity</button></div>`;},
      approved:()=>{if(current())$('#order-status').textContent='Opening wallet…';},
      recorded:()=>notify('Submitted. Activity updates after confirmation.'),
      uncertain:()=>{if(current()){button.textContent='Check transaction';button.removeAttribute('data-action');button.onclick=()=>spotRecovery(r);}},
      error:(message,hash)=>{if(current()){$('#swap-error').textContent=message;if(hash)$('#order-status').innerHTML=`<div class="r-order-status"><a href="https://monadvision.com/tx/${esc(hash)}" target="_blank" rel="noopener noreferrer">Transaction</a><button data-action="activity">Activity</button></div>`;}},
      done:()=>{}
    });
  }catch(e){if(S.trade===r)$('#swap-error').textContent=e.code===4001?'Wallet request canceled':e.message;}
  finally{r.busy=false;Q.spotBusy(r,false);if(button.isConnected){if(r.submittedHash){button.disabled=true;button.textContent='Submitted';}else if(F.uncertainInline()){button.disabled=false;button.textContent='Check transaction';button.removeAttribute('data-action');button.onclick=()=>spotRecovery(r);}else{button.disabled=false;Q.syncSpot();}}}
}
async function oauthConsent(){const query=location.search;try{const req=await api('/api/oauth/request'+query);if(!S.boot.me){authModal(false,oauthConsent);return;}modal('Connect '+esc(req.client),`<p class="r-note">This app will publish as an agent profile owned by @${esc(S.boot.me.handle)}.</p><ul class="r-consent-list">${req.scopes.map(scope=>`<li>${esc({'feed:read':'Read your feeds','posts:write':'Publish posts','replies:write':'Reply to posts','media:upload':'Upload photos and videos','markets:read':'Read market data'}[scope])}</li>`).join('')}</ul><p class="r-note">Access lasts one hour. You can revoke it in Agents.</p><div class="r-form-error" role="alert"></div><button class="r-btn primary full" id="oauth-approve">Allow connection</button><button class="r-btn full subtle" id="oauth-cancel">Cancel</button>`);$('#oauth-cancel').onclick=()=>{closeModal();location.href='/';};$('#oauth-approve').onclick=async e=>{e.currentTarget.disabled=true;try{const body=Object.fromEntries(new URLSearchParams(query));body.scope=req.scopes.join(' ');const r=await api('/api/oauth/approve',body);location.assign(r.redirect);}catch(e){$('.r-form-error').textContent=e.message;$('#oauth-approve').disabled=false;}};}catch(e){modal('Connection unavailable',`<p class="r-note">${esc(e.message)}</p><a class="r-btn full" href="/">Back to Rally</a>`);}}
async function handle(action,id,el){
  if(!S.boot)await bootReady;
  if(!S.marketData&&(action==='compose'||action==='compose-reply'||['trade','search-trade','market-detail'].includes(action)&&!token(id)||action==='market-tab'&&id==='rwa'||action==='watch-filter'))await hydrateMarkets();
  if(await SocialLoop.handle(action,id,el))return;
  if(await E.handle(action,id,el))return;
  if(await U.handle(action,id,el))return;
  if(await G.handle(action,id,el))return;
  if(await L.handle(action,id,el))return;
  if(await T.handle(action,id,el))return;
  if(await W.handle(action,id,el))return;
  if(M.handle(action,id,el))return;
  if(action==='market-page'){S.marketOffset=id==='next'?S.catalogPage?.nextOffset||0:Math.max(0,(S.marketOffset||0)-60);marketList();return;}
  if(action==='market-scope'){S.marketAll=id==='all';S.marketOffset=0;marketList();return;}
  if(await C.handle(action,id,el))return;
  if(await N.handle(action,id,el))return;
  if(await J.handle(action,id,el))return;
  if(await F.handle(action,id,el))return;
  if(action==='account'){if(S.boot.me)navigate('account');else authModal();}
  else if(action==='wallet'){if(S.view==='account'&&S.boot.wallet){if(!U.chooseWallet(true))await connectWallet(null,true,true);}else await connectWallet();}
  else if(action==='compose')composer();
  else if(action==='close-modal')closeModal();
  else if(action==='close-trade')closeTrade();
  else if(action==='search')search();
  else if(action==='feed-expand')P.expand(id,el);
  else if(action==='mode'){if(id==='following'&&!S.boot.me)return needAccount(()=>{S.mode=id;render();});S.mode=id;await render();}
  else if(action==='retry'||action==='refresh-feed'){invalidateSocial();await render();}
  else if(action==='theme'){window.RallyTheme?.set(document.documentElement.dataset.theme==='dark'?'light':'dark');refreshThemedCharts();}
  else if(action==='profile'){closeModal();S.profile=id;S.profileTab='posts';navigate('profile');}
  else if(action==='community'){closeModal();S.community=id;S.communityTab='posts';navigate('community');}
  else if(action==='community-filter'){S.communityFilter=id;renderCommunities();rememberUI();}
  else if(action==='community-section'||action==='profile-section'){if(action==='community-section')S.communityTab=id;else S.profileTab=id;document.querySelectorAll(action==='community-section'?'.r-community-tabs button':'.r-profile-tabs button').forEach(b=>{b.classList.toggle('active',b.dataset.id===id);b.setAttribute('aria-pressed',String(b.dataset.id===id));});paintSocialTimeline();rememberUI();}
  else if(action==='follow')needAccount(async()=>{const p=S.boot.people.find(p=>p.id===id)||await api('/api/profile?id='+encodeURIComponent(id));await api('/api/follow',{id,active:!p.following});await boot();render();});
  else if(action==='join')needAccount(async()=>{await api('/api/join',{id,active:!S.boot.communities.find(c=>c.id===id)?.joined});await boot();render();});
  else if(action==='like'||action==='save')needAccount(async()=>{let p=S.posts.find(p=>p.id===id);if(!p){p=await api('/api/post?id='+encodeURIComponent(id));S.posts.push(p);}const r=await api('/api/reaction',{post:id,kind:action==='like'?'like':'save',active:!(action==='like'?p.liked:p.saved)});Object.assign(p,r);if(action==='like'?r.liked:r.saved)C.track(action,id);document.querySelectorAll('[data-post]').forEach(host=>{if(host.dataset.post===id)host.outerHTML=postCard(p);});if(action==='save'&&S.view==='saved')render();});
  else if(action==='reply')await replies(id);
  else if(action==='compose-reply')composer(id);
  else if(action==='share'){await navigator.clipboard.writeText(location.origin+'/?view=post&id='+encodeURIComponent(id));notify('Link copied');}
  else if(action==='delete'){modal('Delete post?','<p class="r-note">This removes the post from Rally.</p><button id="delete-post-confirm" class="r-btn primary full">Delete post</button>');$('#delete-post-confirm').onclick=async()=>{await api('/api/post/delete',{id});closeModal();render();};}
  else if(action==='watch'){const active=!watched(id);if(S.boot.me)await api('/api/watch',{asset:id,active});S.boot.watches=active?[...S.boot.watches,id]:S.boot.watches.filter(x=>x!==id);if(!S.boot.me)localStorage.setItem('rally:guest-watches',JSON.stringify(S.boot.watches));rail();if((S.view==='explore'||S.view==='home'&&S.homeSection==='markets'))marketList();el.classList.toggle('saved',active);el.setAttribute('aria-label',(active?'Unwatch ':'Watch ')+(token(id)?.symbol||''));notify(active?'Added to watchlist':'Removed from watchlist');}
  else if(action==='watch-filter'){S.watchOnly=!S.watchOnly;rememberUI();el.classList.toggle('selected',S.watchOnly);marketList();}
  else if(action==='discover-memes'){S.marketTab='memes';S.nadMode=id==='dex'?'dex':'new';S.filter='';S.watchOnly=false;await navigate('explore');}
  else if(action==='market-tab'){S.marketTab=id;S.filter='';history.replaceState({...history.state},'', '/?view='+S.view+(S.view==='home'?'&section=markets':'')+'&tab='+id+(id==='memes'?(S.nadMode==='dex'?'&phase=dex':S.nadMode==='new'?'&sort=latest':''):''));rememberUI();await renderExplore();}
  else if(action==='refresh-markets'){marketPages.clear();marketList();}
  else if(action==='trade'||action==='search-trade')trade(id,J.origin(el)||(el.closest('.r-modal')?S.perplIntent?.context:null));
  else if(action==='context-perpl'){const context=S.trade?.context;closeTrade();await F.openPerpl(id,context);}
  else if(action==='pick-pay')pickPay();
  else if(action==='pay-asset'){if(!S.trade)return;S.trade.input=id;S.trade.routes=null;const routeBox=$('#route-comparison');if(routeBox)routeBox.innerHTML='';closeModal();$('.r-pay-select').innerHTML=logo(token(id))+'<b>'+esc(token(id).symbol)+'</b>'+icon('down');invalidateQuote();C.scheduleRoutes();}
  else if(action==='swap')await swap();
  else if(action==='copy-contract'){await navigator.clipboard.writeText(id);notify('Contract copied');}
  else if(action==='wallet-send')await WalletUX.send();
  else if(action==='wallet-deposit')await WalletUX.deposit();
  else if(action==='chart-provider'||action==='chart-interval'){const ref=referenceAsset(token(S.trade?.originAsset||S.trade?.asset));if(!ref)return;S.chart[action==='chart-provider'?'chartProvider':'chartInterval']=id;disposeChart();$('#trade-chart').innerHTML=chart(ref,S.chart);mountChart(ref,S.chart);}
  else if(action==='chart-fit')fitChart();
  else if(action==='chart-retry'){const ref=referenceAsset(token(S.trade?.originAsset||S.trade?.asset));if(ref){disposeChart();$('#trade-chart').innerHTML=chart(ref,S.chart);mountChart(ref,S.chart);}}
  else if(action==='connect-agent')connectAgent(id||'');
  else if(action==='agent-guide')agentGuide('',id||'codex');
  else if(action==='copy-agent-setup'){const setup=$('#agent-setup');if(setup){await navigator.clipboard.writeText(setup.textContent);notify('Copied');}}
  else if(action==='copy-mcp'){await navigator.clipboard.writeText(location.origin+'/mcp');notify('MCP address copied');}
  else if(action==='copy-key'){await navigator.clipboard.writeText(S.modal.key);notify('Token copied');}
  else if(action==='revoke'){await api('/api/connections/revoke',{id});await boot();render();notify('Connection revoked');}
  else if(action==='create-feed')createFeed();
  else if(action==='use-feed'){const alreadyFeed=S.view==='home'&&S.homeSection==='feed';S.homeSection='feed';
   if(S.feedSwitchBusy)return;const feed=S.boot.feeds.find(f=>f.id===id);if(!feed)throw new Error('Algorithm unavailable');
   if(!feed.access){S.feed=id;closeModal();await navigate('feed');return;}
   if(S.boot.activeFeed===id&&alreadyFeed&&S.mode==='for-you'){closeModal();return;}
   const owner=S.boot.me?.id,routeKey=history.state?.key;S.feedSwitchBusy=true;el.disabled=true;el.setAttribute('aria-busy','true');
   try{if(owner)await api('/api/feeds/use',{id});if(S.boot.me?.id!==owner)return;S.boot.activeFeed=id;S.mode='for-you';if(!owner){try{localStorage.setItem('rally:guest-feed',id);}catch{}}
    if(history.state?.key!==routeKey){if(S.view==='feeds')J.paintFeeds();else if(S.view==='home'){invalidateSocial();await render();}return;}closeModal();if(S.view==='home'&&alreadyFeed){invalidateSocial();window.scrollTo({top:0,behavior:'instant'});await render();focusMain();}else await navigate('home');
   }finally{S.feedSwitchBusy=false;if(el.isConnected){el.disabled=false;el.removeAttribute('aria-busy');}}
  }
  else if(action==='edit-profile')editProfile();
  else if(action==='logout'){await SocialLoop.detach();const providerLogout=U.logout();await api('/api/auth/logout',{});closeTrade();await boot();S.activity=null;S.feedPreview=null;await navigate('home');await providerLogout;}
  else if(action==='more'){
   el.disabled=true;const seq=renderSequence,host=$('#timeline'),query=new URLSearchParams({mode:S.view==='saved'?'saved':S.view==='home'?S.mode:'for-you',feed:S.boot.activeFeed,cursor:S.cursor});if(!S.boot.me)query.set('watch',S.boot.watches.join(','));if(S.view==='community')query.set('community',S.community);if(S.view==='profile')query.set('author',S.profile);
   try{const d=await api('/api/posts?'+query,undefined,{signal:socialController.signal});if(seq!==renderSequence||!host.isConnected)return;const ids=new Set((S.timelinePosts||[]).map(p=>p.id)),posts=d.posts.filter(p=>!ids.has(p.id));S.posts.push(...posts);S.timelinePosts.push(...posts);for(const p of posts)S.timelineRuns.set(p.id,d.algorithmRun);S.cursor=d.cursor;if(['community','profile'].includes(S.view))paintSocialTimeline();else{el.insertAdjacentHTML('beforebegin',posts.map(postCard).join(''));if(!d.cursor)el.remove();else el.disabled=false;}C.observe(posts,d.algorithmRun);P.sync();}
   catch(error){if(seq===renderSequence&&el.isConnected){el.disabled=false;notify(error.message);}}
  }
}
document.addEventListener('click',e=>{const modified=e.metaKey||e.ctrlKey||e.shiftKey||e.altKey||e.button!==0;const nav=e.target.closest('[data-nav]');if(nav){if(modified&&nav.matches('a[href]'))return;e.preventDefault();$('.r-more-nav')?.removeAttribute('open');closeModal();if(nav.hasAttribute('data-home-primary'))S.homeSection='markets';navigate(nav.dataset.nav).catch(error=>notify(error.message));return;}const el=e.target.closest('[data-action]');if(el){if(modified&&el.matches('a[href]'))return;e.preventDefault();handle(el.dataset.action,el.dataset.id,el).catch(e=>notify(e.message));}});
document.addEventListener('input',e=>{if(e.target.id==='market-filter'){S.filter=e.target.value;S.marketOffset=0;rememberUI();clearTimeout(S.searchTimer);S.searchTimer=setTimeout(marketList,180);}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){const more=$('.r-more-nav');if(more?.open){more.open=false;more.querySelector('summary').focus();}if(S.modal){e.preventDefault();closeModal();}else if(S.trade||S.nadOverlay){e.preventDefault();closeTrade();}}if((e.metaKey||e.ctrlKey)&&e.key==='k'){e.preventDefault();search();}if(e.key==='Tab'&&(S.modal||S.trade||S.nadOverlay)){const root=S.modal?$('.r-modal'):$('.r-trade-panel');const items=[...root.querySelectorAll('button:not([disabled]),a[href],input,textarea,select,[tabindex="0"]')].filter(x=>x.offsetParent!==null);if(items.length){const first=items[0],last=items.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}}});
history.scrollRestoration='manual';
window.addEventListener('popstate',async e=>{
 try{const q=new URLSearchParams(location.search);Object.assign(S,e.state?.ui||{});S.view=q.get('view')||'home';S.homeSection=q.get('section')==='feed'?'feed':'markets';if(S.view==='messages')S.view='home';S.community=q.get('id');S.profile=q.get('id');S.feed=q.get('id');S.post=q.get('id')||q.get('post');S.nadToken=q.get('id')||q.get('token');if(q.has('tab'))S.marketTab=marketTabs.includes(q.get('tab'))?q.get('tab'):'memes';S.swipeTab=['spot','perps','prediction'].includes(q.get('market'))?q.get('market'):S.swipeTab;S.nadMode=q.get('phase')==='dex'?'dex':q.get('sort')==='latest'?'new':'cap';N.dispose();closeModal();closeTrade();await render(routeSnapshots.get(e.state?.key));await restorePosition(e.state);}
 catch(error){if(error.name!=='AbortError')notify(error.message);}
});
async function checkNewPosts(){if(document.hidden||S.modal||S.view==='community'&&S.communityTab&&S.communityTab!=='posts'||S.view==='profile'&&S.profileTab&&S.profileTab!=='posts'||!['home','community','profile'].includes(S.view)||!$('#timeline')||S.mode==='following'&&!S.boot.me)return;const view=S.view;const q=new URLSearchParams({mode:view==='home'?S.mode:'for-you',feed:S.boot.activeFeed,observe:'0'});if(!S.boot.me)q.set('watch',S.boot.watches.join(','));if(view==='community')q.set('community',S.community);if(view==='profile')q.set('author',S.profile);try{const d=await api('/api/posts?'+q);if(S.view!==view||!$('#timeline'))return;const fresh=d.posts.filter(p=>!S.posts.some(x=>x.id===p.id&&Number(x.feedAt||x.created)>=Number(p.feedAt||p.created))).length;let banner=$('#new-posts');if(fresh&&!banner){$('#timeline').insertAdjacentHTML('afterbegin','<button id="new-posts" class="r-new-posts" data-action="refresh-feed"></button>');banner=$('#new-posts');}if(banner){if(fresh)banner.textContent=fresh+(fresh===1?' new post':' new posts')+' · Refresh';else banner.remove();}}catch{}}
function refreshPriceSurfaces(){rail();document.querySelectorAll('.r-post-asset').forEach(el=>{const t=token(el.dataset.id);if(!t)return;$('.r-asset-price>b',el).innerHTML=priceHTML(t.price);const move=$('.r-asset-price>small',el);move.textContent=pct(t.change);move.className=(t.change||0)>=0?'positive':'negative';});if(S.trade){const t=token(S.trade.originAsset||S.trade.asset);const host=$('.r-trade-price');if(t&&host){$('h2',host).textContent=usd(t.price);const move=$('span',host);move.className=(t.change||0)>=0?'positive':'negative';move.innerHTML=pct(t.change)+' <small>24h</small>';}}}
const Q=checkoutUI({S,$,token,trade,closeModal,invalidateQuote,logo,perplAsset:market=>F.perplAsset(market)});
const F=financeUI({S,$,api,esc,icon,usd,age,modal,closeModal,needAccount,walletReady,receipt,notify,boot,navigate,pageHeader,empty,loading,safeURL,token,logo,activity:()=>J.openActivity(),trade,spotPending,resumeSpot,recordSpot:recordOrder,originCard:context=>J.originCard(context),checkout:Q});
const WalletUX=walletUI({S,$,api,esc,icon,usd,pct,age,modal,notify,pageHeader,empty,logo,token,connect:connectWallet,submit:(plan,ui)=>F.submitInline(plan,ui)});
const N=nadfunUI({launchPanel:t=>L.tokenPanel(t),S,$,api,esc,icon,logo,usd,age,modal,needAccount,walletReady,notify,navigate,pageHeader,empty,loading,finance:F,composer,originCard:context=>J.originCard(context),checkout:Q,closeModal,closeTrade,pauseMedia});
const C=communityUI({S,$,api,esc,icon,avatar,age,modal,closeModal,notify,boot,navigate,pageHeader,postCard,loading,empty,needAccount,render,logo,personRow,token});
const M=marketUI({S,$,api,esc,usd,priceHTML,volumeHTML,age,logo,token,modal,trade,finance:F});
const J=journeyUI({S,$,api,esc,icon,avatar,token,postCard,pageHeader,empty,loading,boot,navigate,notify,modal,closeModal,closeTrade,age,finance:F});
const P=feedUI({S,$,esc,icon,safeURL,scope:socialScope});
const W=swipeUI({homeHeader:()=>E.homeHeader(),nad:N,readingAnchor:()=>P.anchor(),S,$,api,esc,icon,logo,avatar,usd,age,mediaCard,safeURL,token,navigate,notify,trade,finance:F,needAccount,walletReady,openPost:replies});
const U=authUI({S,$,api,esc,icon,modal,closeModal,boot,render,notify,connectWallet,afterWallet:async next=>{if(next&&!T.defer(next))await next();},afterLogin:async next=>{if(['/connect-native','/native-wallet'].includes(location.pathname)){if(next)await next();else await nativeLink({S,api,$,esc,notify,trade,finance:F,nad:N,launch:L,needAccount,boot,auth:U});return;}if(location.pathname==='/authorize'){if(next)await next();else await oauthConsent();return;}if(S.view==='launch'){if(next)await next();else await L.create();return;}if(await T.onboard(next))return;if(next)await next();}});
const G=creatorUI({S,$,api,esc,icon,avatar,priceHTML,notify,navigate,render,closeModal,trade,openCommunityToken:()=>T.open(),pageHeader,empty,loading,modal,needAccount,walletReady,afterEarnings:()=>L.earningsPanel()});
const T=communityTokenUI({S,$,api,esc,icon,modal,closeModal,boot,render,notify,walletReady,receipt,navigate,trade,creator:G});
const L=launchpadUI({homeHeader:()=>E.homeHeader(),S,$,api,esc,icon,avatar,usd,age,navigate,needAccount,walletReady,notify,modal,closeModal,boot,finance:F,nad:N,creator:G});
const SocialLoop=socialLoopUI({S,$,api,esc,icon,usd,pct,age,modal,closeModal,notify,needAccount,navigate,render,boot,avatar,token});
const E=experienceUI({S,$,api,esc,icon,avatar,mediaCard,postCard,safeURL,usd,pct,navigate,notify,modal,closeModal,needAccount,empty,loading,motion:Motion});
async function start(){
 clearInterval(refreshTimer);clearInterval(S.feedTimer);clearInterval(S.mediaTimer);shell();$('#page').innerHTML=loading();
 S.community=params.get('id');S.profile=params.get('id');S.feed=params.get('id');S.post=params.get('id')||params.get('post');S.nadToken=params.get('id')||params.get('token');
 try{
  const memeStart=(S.view==='explore'||S.view==='home'&&S.homeSection==='markets')&&S.marketTab==='memes',compact=S.view==='discover'||memeStart;
  if(S.view==='discover')E.prime();else if(memeStart)N.catalog(S.nadMode==='dex'?'dex':'',S.nadMode==='cap'?'cap':'latest').catch(()=>{});
  bootReady=boot(compact);await bootReady;await render();const authResumed=await U.resume();S.mediaTimer=setInterval(refreshMedia,4000);
  // Venue outages cannot delay the social feed or account authorization screen.
  if(location.pathname!=='/authorize'&&S.view!=='swipe'&&(S.view==='home'||matchMedia('(min-width:1191px)').matches)&&!S.nadCatalog)loadLaunchPreview();
  if(['home','explore'].includes(S.view)&&S.marketTab==='perps'&&!S.perps)F.perpData().catch(()=>{});
  if(S.view!=='swipe'&&(!S.marketData||Date.now()/1000-(S.marketData.fetchedAt||0)>45)){
   const hydrate=()=>hydrateMarkets().then(()=>{if((S.view==='explore'||S.view==='home'&&S.homeSection==='markets')&&['spot','rwa'].includes(S.marketTab))($('#market-list [data-spot-market]')?M.patchSpot():marketList());}).catch(()=>{});
   if(compact)setTimeout(()=>{if('requestIdleCallback' in window)requestIdleCallback(hydrate,{timeout:1500});else hydrate();},500);else hydrate();
  }
  if(location.pathname==='/authorize'&&!authResumed)await oauthConsent();
  else if(params.has('post')&&S.view!=='post'){try{const p=await api('/api/post?id='+encodeURIComponent(params.get('post')));if(!S.posts.some(x=>x.id===p.id))S.posts.push(p);await replies(p.id);}catch(e){notify(e.message);}}
  const restore=async()=>{try{const pending=JSON.parse(localStorage.getItem('rally:pending-order')||'null');if(pending&&pending.user===S.boot.me?.id){const recorded=await recordOrder(pending.quote,pending.tx);if(recorded)notify('Submitted order restored. Check Activity.');}await F.resume();}catch(e){notify(e.message);}};
  restore();S.feedTimer=setInterval(()=>{checkNewPosts();C.poll().catch(()=>{});J.poll().catch(()=>{});N.poll().catch(()=>{});L.poll().catch(()=>{});},12000);
  if(['/connect-native','/native-wallet'].includes(location.pathname)){await nativeLink({S,api,$,esc,notify,trade,finance:F,nad:N,launch:L,needAccount,boot,auth:U});return true;}
  if(S.view!=='launch')await T.onboard();
  let refreshing=false;refreshTimer=setInterval(async()=>{if(document.hidden||refreshing||S.view==='swipe')return;refreshing=true;try{const m=await api('/api/markets');S.tokens=[...new Map([...S.tokens,...m.tokens].map(t=>[t.id,t])).values()];S.marketData=m;refreshPriceSurfaces();if((S.view==='explore'||S.view==='home'&&S.homeSection==='markets')&&['spot','rwa'].includes(S.marketTab))($('#market-list [data-spot-market]')?M.patchSpot():marketList());}catch{}finally{refreshing=false;}},20000);
 }catch(e){$('#page').innerHTML=empty('Rally is reconnecting',esc(e.message),'<button class="r-btn" data-action="retry-start">Retry</button>');$('[data-action=retry-start]').onclick=start;}
}
start();
