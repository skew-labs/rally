import {ALGORITHM_LIBRARY_URL} from './algorithm-library-data.js';

// Research methods share the Algorithms collection, but cannot request payments or orders.
let catalog=null,pending=null;
export function validYear(p){
 if(!p||p.basis!=='published_factor'||p.months!==12||!Number.isFinite(p.returnPct)||p.returnPct<=-100)return false;
 const from=new Date(p.from+'T00:00:00Z'),to=new Date(p.to+'T00:00:00Z');
 return Number.isFinite(+from)&&Number.isFinite(+to)&&from.getUTCDate()===1&&to.getUTCDate()===new Date(Date.UTC(to.getUTCFullYear(),to.getUTCMonth()+1,0)).getUTCDate()&&to.getUTCFullYear()*12+to.getUTCMonth()-from.getUTCFullYear()*12-from.getUTCMonth()===11&&+to<=Date.now()&&/^https:\/\/www\.aqr\.com\//.test(p.sourceURL);
}
export async function loadAlgorithmLibrary(){
 if(catalog)return catalog;if(pending)return pending;
 pending=(async()=>{
  const r=await fetch(ALGORITHM_LIBRARY_URL,{credentials:'omit',cache:'force-cache',signal:AbortSignal.timeout(10000)});
  if(!r.ok)throw Error('Algorithms unavailable. Try again.');
  const data=await r.json();
  if(data.version!==1||!Array.isArray(data.items)||data.items.length!==100||data.items.some(a=>a.status!=='reference'||!/^rally-ref-\d{3}$/.test(a.id)||a.performance1Y&&!validYear(a.performance1Y)))throw Error('Algorithms unavailable. Try again.');
  catalog=data;return data;
 })().finally(()=>pending=null);return pending;
}
export function algorithmLibraryUI({S,esc,icon,modal,notify}){
 let host=null,source='',category='',query='',filter='all',onlySaved=false,limit=24,saved=new Set();
 try{const ids=JSON.parse(localStorage.getItem('rally:library-saved')||'[]');if(Array.isArray(ids))saved=new Set(ids.filter(x=>/^rally-ref-\d{3}$/.test(x)));}catch{}
 const pct=n=>(n>0?'+':'')+n.toLocaleString('en-US',{maximumFractionDigits:1})+'%';
 const art=a=>`<span class="al-art ${a.brandIcon?'al-brand-art':''}"><img class="al-logo-light" src="${esc(a.brandIcon||a.icon)}" width="56" height="56" alt="" loading="lazy" decoding="async">${a.brandIconDark&&a.brandIconDark!==a.brandIcon?`<img class="al-logo-dark" src="${esc(a.brandIconDark)}" width="56" height="56" alt="" loading="lazy" decoding="async">`:''}</span>`;
 const year=a=>{const p=a.performance1Y;return `<span class="al-year"><b class="${p?p.returnPct>=0?'positive':'negative':''}">${p?pct(p.returnPct):'—'}</b><small>${p?'1Y model':'1Y return'}</small></span>`;};
 const row=a=>`<article class="al-row" data-algorithm="${a.id}"><button class="al-open" data-action="library-detail" data-id="${a.id}" aria-label="Open ${esc(a.name)}">${art(a)}<span class="al-row-name"><b>${esc(a.name)}</b><small>${esc(a.category)}</small></span>${year(a)}</button><button class="al-save ${saved.has(a.id)?'is-saved':''}" data-action="library-save" data-id="${a.id}" aria-pressed="${saved.has(a.id)}" aria-label="${saved.has(a.id)?'Unsave':'Save'} ${esc(a.name)}">${icon('bookmark')}</button></article>`;
 function save(id){
  if(!catalog?.items.some(a=>a.id===id))return;const next=new Set(saved);next.has(id)?next.delete(id):next.add(id);
  try{localStorage.setItem('rally:library-saved',JSON.stringify([...next]));saved=next;}catch{notify('Could not save on this device.');return;}
  paint();document.querySelectorAll('[data-action="library-save"]').forEach(b=>{if(b.dataset.id!==id)return;b.setAttribute('aria-pressed',String(saved.has(id)));b.classList.toggle('is-saved',saved.has(id));if(b.classList.contains('al-detail-save'))b.textContent=saved.has(id)?'Saved':'Save';});
 }
 function paint(){
  if(!host?.isConnected||!catalog)return;
  const words=query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const items=catalog.items.filter(a=>!['paid','yours'].includes(filter)&&(!source||a.sourceId===source)&&(!category||a.category===category)&&(!onlySaved||saved.has(a.id))&&words.every(w=>[a.name,a.method,a.author,a.kind,a.category,a.sourceName,a.rule].join(' ').toLowerCase().includes(w)));
  host.querySelector('.al-results').textContent=items.length+' algorithms';
  host.querySelector('.al-rows').innerHTML=items.slice(0,limit).map(row).join('')||'<div class="al-empty">No matching strategies</div>';
  host.querySelector('.al-more').hidden=items.length<=limit;host.querySelector('.al-more').textContent=`Show more · ${Math.max(0,items.length-limit)} left`;
  host.querySelectorAll('[data-action="library-source"]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===source)));
  host.querySelectorAll('[data-action="library-category"]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===category)));
  host.querySelector('[data-action="library-saved"]').setAttribute('aria-pressed',String(onlySaved));
 }
 async function mount(target,options={}){
  if(query!==(options.query||'')||filter!==(options.filter||'all'))limit=24;
  query=options.query||'';filter=options.filter||'all';host=target;
  if(['paid','yours'].includes(filter)){target.hidden=true;return;}target.hidden=false;
  target.innerHTML='<div class="al-loading" role="status">Loading strategies…</div>';
  try{
   await loadAlgorithmLibrary();if(host!==target||!target.isConnected)return;
   const priority=['aqr','a16z','bridgewater','msci','nad','nansen','kuru'];
   const sources=[...catalog.sources].sort((a,b)=>(priority.indexOf(a.id)<0?99:priority.indexOf(a.id))-(priority.indexOf(b.id)<0?99:priority.indexOf(b.id)));
   target.innerHTML=`<header class="am-section-head"><h2>Strategies</h2><button class="al-saved-filter" data-action="library-saved" aria-pressed="${onlySaved}">${icon('bookmark')}Saved</button></header><div class="al-sources" role="group" aria-label="Strategy sources"><button data-action="library-source" data-id="" aria-pressed="${!source}">All</button>${sources.map(b=>`<button data-action="library-source" data-id="${b.id}" aria-pressed="${source===b.id}">${art({brandIcon:b.logo,brandIconDark:b.logoDark})}${esc(b.name)}</button>`).join('')}</div><div class="al-categories" role="group" aria-label="Strategy categories">${['',...catalog.categories].map(g=>`<button data-action="library-category" data-id="${esc(g)}" aria-pressed="${g===category}">${esc(g||'All strategies')}</button>`).join('')}</div><div class="al-caption"><span class="al-results" role="status" aria-live="polite"></span><span>1Y model · published factors</span></div><section class="al-rows" aria-label="Algorithms"></section><button class="al-more" data-action="library-more"></button>`;paint();
  }catch(e){if(target.isConnected&&host===target)target.innerHTML=`<div class="al-empty"><b>Strategies unavailable</b><p>${esc(e.message)}</p><button data-action="library-retry">Retry</button></div>`;}
 }
 async function detail(id){
  await loadAlgorithmLibrary();const a=catalog.items.find(a=>a.id===id);if(!a)return;
  const url=new URL(a.sourceURL);if(url.protocol!=='https:')return;const p=a.performance1Y;
  const performance=`<section class="al-performance">${year(a)}${p?`<p>${esc(p.from)} — ${esc(p.to)}</p><small>${esc(p.universe)} · ${esc(p.series)}</small>`:'<p>No complete 1Y record published.</p>'}</section>`;
  modal(esc(a.name),`<div class="al-detail-scroll"><div class="al-identity">${art(a)}<span><b>${esc(a.name)}</b><small>${esc(a.category)}</small></span></div>${performance}<p class="al-method">${esc(a.method)}</p><p class="al-rule">${esc(a.rule)}</p><details class="al-evidence"><summary>How it works ${icon('down')}</summary><h3>Data needed</h3><p>${esc(a.dataNeeded)}</p>${p?`<h3>1Y methodology</h3><p>Twelve consecutive monthly factor returns, compounded. Hypothetical excess returns; fees excluded. These are research results, not Rally trading returns.</p><a href="${esc(p.sourceURL)}" target="_blank" rel="noopener noreferrer">Performance data ${icon('external')}</a>`:''}</details></div><footer class="al-detail-foot"><button class="r-btn primary al-detail-save" data-action="library-save" data-id="${a.id}" aria-pressed="${saved.has(id)}">${saved.has(id)?'Saved':'Save'}</button><small class="al-attribution"><a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">Source: ${esc(a.sourceName||a.author)} ${icon('external')}</a><span>Independent Rally research · No affiliation</span></small></footer>`,'al-detail-modal');
 }
 async function handle(action,id){
  if(!action.startsWith('library-'))return false;
  if(action==='library-detail')await detail(id);
  else if(action==='library-save')save(id);
  else if(action==='library-retry')await mount(host,{query,filter});
  else if(action==='library-source'){source=source===id?'':id;limit=24;paint();}
  else if(action==='library-category'){category=id;limit=24;paint();}
  else if(action==='library-saved'){onlySaved=!onlySaved;limit=24;paint();}
  else if(action==='library-more'){limit+=24;paint();}
  else return false;return true;
 }
 return {mount,handle};
}
