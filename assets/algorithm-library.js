import {ALGORITHM_LIBRARY_URL} from './algorithm-library-data.js';

// Reference browsing only. Never register these items as purchasable feeds.
let catalog=null,pending=null;
export async function loadAlgorithmLibrary(){
 if(catalog)return catalog;
 if(pending)return pending;
 pending=(async()=>{
  const r=await fetch(ALGORITHM_LIBRARY_URL,{credentials:'omit',cache:'force-cache',signal:AbortSignal.timeout(10000)});
  if(!r.ok)throw new Error('Library unavailable. Try again.');
  const data=await r.json();
  if(data.version!==1||!Array.isArray(data.items)||data.items.length!==100||data.items.some(a=>a.status!=='reference'||!/^rally-ref-\d{3}$/.test(a.id)))throw new Error('Library unavailable. Try again.');
  catalog=data;return data;
 })().finally(()=>{pending=null;});return pending;
}
export function algorithmLibraryUI({S,esc,icon,modal,notify}){
 let host=null,source='',category='',query='',onlySaved=false,limit=24,saved=new Set();
 try{const ids=JSON.parse(localStorage.getItem('rally:library-saved')||'[]');if(Array.isArray(ids))saved=new Set(ids.filter(x=>/^rally-ref-\d{3}$/.test(x)));}catch{}
 const art=a=>`<img class="al-art ${a.brandIcon?'al-brand-art':''}" src="${esc(a.brandIcon||a.icon)}" width="56" height="56" alt="" loading="lazy" decoding="async">`;
 const row=a=>`<article class="al-row"><button class="al-open" data-action="library-detail" data-id="${a.id}" aria-label="Read ${esc(a.name)}">${art(a)}<span><b>${esc(a.name)}</b><small>${esc(a.category)}</small></span></button><button class="al-save ${saved.has(a.id)?'is-saved':''}" data-action="library-save" data-id="${a.id}" aria-pressed="${saved.has(a.id)}" aria-label="${saved.has(a.id)?'Unsave':'Save'} ${esc(a.name)}">${icon('bookmark')}</button></article>`;
 const tabSources=()=>{const priority=['a16z','aqr','nad','nansen','bridgewater','msci','uniswap','kuru'];return [...catalog.sources].sort((a,b)=>(priority.indexOf(a.id)<0?99:priority.indexOf(a.id))-(priority.indexOf(b.id)<0?99:priority.indexOf(b.id)));};
 function save(id){
  if(!catalog?.items.some(a=>a.id===id))return;
  const next=new Set(saved);next.has(id)?next.delete(id):next.add(id);
  try{localStorage.setItem('rally:library-saved',JSON.stringify([...next]));saved=next;}catch{notify('Could not save on this device.');return;}
  const focus=document.activeElement?.closest('[data-action="library-save"]')?.dataset.id;
  paint();
  document.querySelectorAll('[data-action="library-save"]').forEach(b=>{if(b.dataset.id!==id)return;b.setAttribute('aria-pressed',String(saved.has(id)));b.classList.toggle('is-saved',saved.has(id));b.setAttribute('aria-label',(saved.has(id)?'Unsave ':'Save ')+catalog.items.find(a=>a.id===id).name);if(b.classList.contains('al-detail-save'))b.textContent=saved.has(id)?'Saved':'Save';});
  if(focus&&!S.modal)host?.querySelector(`[data-action="library-save"][data-id="${focus}"]`)?.focus({preventScroll:true});
  notify(saved.has(id)?'Saved on this device':'Removed from saved');
 }
 function paint(){
  if(!host?.isConnected||!catalog)return;
  const words=query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const items=catalog.items.filter(a=>(!source||a.sourceId===source)&&(!category||a.category===category)&&(!onlySaved||saved.has(a.id))&&words.every(w=>[a.name,a.method,a.author,a.kind,a.category,a.sourceName,a.rule].join(' ').toLowerCase().includes(w)));
  host.querySelector('.al-results').textContent=`${items.length} in library`;
  host.querySelector('.al-rows').innerHTML=items.slice(0,limit).map(row).join('')||'<div class="al-empty"><b>No references found</b><button data-action="library-reset">Clear filters</button></div>';
  host.querySelector('.al-more').hidden=items.length<=limit;
  host.querySelector('.al-more').textContent=`Show more · ${Math.max(0,items.length-limit)} left`;
  host.querySelectorAll('[data-action="library-source"]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===source)));
  host.querySelectorAll('[data-action="library-category"]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===category)));
  host.querySelector('[data-action="library-saved"]').setAttribute('aria-pressed',String(onlySaved));
 }
 async function mount(target){
  host=target;target.innerHTML='<div class="al-loading" role="status">Loading library…</div>';
  try{
   await loadAlgorithmLibrary();if(host!==target||!target.isConnected)return;
   const chosen=catalog.items.filter(a=>['rally-ref-099','rally-ref-001','rally-ref-091','rally-ref-080'].includes(a.id)).sort((a,b)=>['rally-ref-099','rally-ref-001','rally-ref-091','rally-ref-080'].indexOf(a.id)-['rally-ref-099','rally-ref-001','rally-ref-091','rally-ref-080'].indexOf(b.id));
   target.innerHTML=`<section class="al-highlights" aria-label="Featured references">${chosen.map(a=>`<button class="al-highlight" data-action="library-detail" data-id="${a.id}">${art(a)}<b>${esc(a.name)}</b></button>`).join('')}</section><div class="al-sources" role="group" aria-label="Reference sources"><button data-action="library-source" data-id="" aria-pressed="${!source}">All sources</button>${tabSources().map(b=>`<button data-action="library-source" data-id="${b.id}" aria-pressed="${source===b.id}"><img src="${esc(b.logo)}" alt="" width="24" height="24" loading="lazy" decoding="async">${esc(b.name)}</button>`).join('')}</div><div class="al-tools"><label class="r-algorithm-search">${icon('search')}<input type="search" id="library-search" placeholder="Search strategies or sources" aria-label="Search library" autocomplete="off" value="${esc(query)}"></label><button class="al-saved-filter" data-action="library-saved" aria-pressed="${onlySaved}">${icon('bookmark')}Saved</button></div><div class="al-categories" role="group" aria-label="Reference categories">${['',...catalog.categories].map(g=>`<button data-action="library-category" data-id="${esc(g)}" aria-pressed="${g===category}">${esc(g||'All methods')}</button>`).join('')}</div><div class="al-caption"><span></span><span class="al-results" role="status" aria-live="polite"></span></div><section class="al-rows" aria-label="Strategy references"></section><button class="al-more" data-action="library-more"></button>`;
   target.querySelector('#library-search').addEventListener('input',e=>{query=e.target.value;limit=24;paint();});paint();
  }catch(e){if(target.isConnected&&host===target)target.innerHTML=`<div class="al-empty"><b>Library unavailable</b><p>${esc(e.message)}</p><button data-action="library-retry">Retry</button></div>`;}
 }
 async function detail(id){
  await loadAlgorithmLibrary();const a=catalog.items.find(a=>a.id===id);if(!a)return;
  const url=new URL(a.sourceURL);if(url.protocol!=='https:')return;
  modal(esc(a.name),`<div class="al-detail-scroll"><div class="al-identity">${art(a)}<span><b>${esc(a.name)}</b><small>${esc(a.category)}</small></span></div><p class="al-method">${esc(a.method)}</p><p class="al-rule">${esc(a.rule)}</p><details class="al-evidence"><summary>How it works ${icon('down')}</summary><h3>Data needed</h3><p>${esc(a.dataNeeded)}</p></details></div><footer class="al-detail-foot"><button class="r-btn primary al-detail-save" data-action="library-save" data-id="${a.id}" aria-pressed="${saved.has(id)}">${saved.has(id)?'Saved':'Save'}</button><small class="al-attribution"><a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">Source: ${esc(a.sourceName||a.author)} ${icon('external')}</a><span>Independent Rally reference · No live results or affiliation</span></small></footer>`,'al-detail-modal');
 }
 async function handle(action,id){
  if(!action.startsWith('library-'))return false;
  if(action==='library-detail')await detail(id);
  else if(action==='library-save')save(id);
  else if(action==='library-retry')await mount(host);
  else if(action==='library-source'){source=source===id?'':id;limit=24;paint();}
  else if(action==='library-category'){category=id;limit=24;paint();}
  else if(action==='library-saved'){onlySaved=!onlySaved;limit=24;paint();}
  else if(action==='library-more'){limit+=24;paint();}
  else if(action==='library-reset'){source='';category='';query='';onlySaved=false;limit=24;host.querySelector('#library-search').value='';paint();}
  else return false;return true;
 }
 return {mount,handle};
}
