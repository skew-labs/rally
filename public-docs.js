const themeButton=document.querySelector('.p-theme');
function updateTheme(){
 const dark=document.documentElement.dataset.theme==='dark';
 themeButton?.setAttribute('aria-label',dark?'Switch to light mode':'Switch to dark mode');
 if(themeButton)themeButton.innerHTML=dark?'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5"/></svg>':'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M20.6 14A8.7 8.7 0 0 1 10 3.4 8.7 8.7 0 1 0 20.6 14Z"/></svg>';
 document.querySelector('meta[name="theme-color"]')?.setAttribute('content',dark?'#18181c':'#ffffff');
}
 themeButton?.addEventListener('click',()=>{window.RallyTheme?.set(document.documentElement.dataset.theme==='dark'?'light':'dark');updateTheme();});
 window.addEventListener('rally-theme-change',updateTheme);updateTheme();
const searchDialog=document.querySelector('#p-search');
const searchInput=document.querySelector('#p-search-input');
const results=document.querySelector('#p-search-results');
const searchCount=document.querySelector('.p-search-count');
const drawer=document.querySelector('#p-navigation');
let indexPromise,selected=-1,searchGeneration=0;
const origins=new WeakMap();
function openDialog(dialog,trigger){
 if(dialog.open)return;
 document.querySelectorAll('dialog[open]').forEach(other=>other.close());
 origins.set(dialog,trigger||document.activeElement);dialog.showModal();
 document.body.style.overflow='hidden';
 if(dialog===searchDialog){searchInput.focus();searchInput.select();renderSearch();}
}
document.querySelector('.p-menu')?.addEventListener('click',event=>openDialog(drawer,event.currentTarget));
document.querySelector('.p-search-trigger')?.addEventListener('click',event=>openDialog(searchDialog,event.currentTarget));
document.querySelectorAll('dialog').forEach(dialog=>{
 dialog.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();dialog.close();}});
 dialog.querySelector('[data-close-dialog]')?.addEventListener('click',()=>dialog.close());
 dialog.addEventListener('click',event=>{
  if(event.target!==dialog)return;
  const box=dialog.getBoundingClientRect();
  if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)dialog.close();
 });
 dialog.addEventListener('close',()=>{
  if(!document.querySelector('dialog[open]'))document.body.style.overflow='';
  origins.get(dialog)?.focus();
 });
});
drawer?.querySelectorAll('a').forEach(link=>link.addEventListener('click',()=>drawer.close()));
function loadIndex(){
 if(!indexPromise)indexPromise=fetch('/docs-search.json',{credentials:'omit'}).then(response=>{
  if(!response.ok)throw new Error('Search is unavailable');return response.json();
 }).then(pages=>{
  if(!Array.isArray(pages))throw new Error('Search is unavailable');
  return pages.filter(page=>typeof page.url==='string'&&(/^\/docs(?:\/[a-z-]+)?$/.test(page.url)||['/terms','/privacy'].includes(page.url))&&typeof page.title==='string'&&typeof page.text==='string');
 }).catch(error=>{indexPromise=undefined;throw error;});
 return indexPromise;
}
function excerpt(page,words){
 if(!words.length)return page.description;
 const text=page.text.replace(/\s+/g,' '),lower=text.toLowerCase();
 const found=words.map(word=>lower.indexOf(word)).filter(position=>position>=0);
 const start=Math.max(0,(found.length?Math.min(...found):0)-48);
 return (start?'…':'')+text.slice(start,start+160)+(text.length>start+160?'…':'');
}
function setSelected(position,moveFocus=false){
 const links=[...results.querySelectorAll('a')];if(!links.length)return;
 selected=Math.max(0,Math.min(position,links.length-1));
 links.forEach((link,i)=>{link.toggleAttribute('data-selected',i===selected);link.removeAttribute('aria-current');});
 links[selected].setAttribute('aria-current','true');
 if(moveFocus){links[selected].focus();links[selected].scrollIntoView({block:'nearest'});}
}
async function renderSearch(){
 const generation=++searchGeneration,query=searchInput.value.trim().toLowerCase().slice(0,120);
 searchCount.textContent='Loading documentation…';
 try{
  const pages=await loadIndex();if(generation!==searchGeneration||!searchDialog.open)return;
  const words=query.split(/\s+/).filter(Boolean);
  const ranked=pages.map(page=>{
   const title=page.title.toLowerCase(),description=(page.description||'').toLowerCase(),text=page.text.toLowerCase();
   const matches=words.every(word=>title.includes(word)||description.includes(word)||text.includes(word));
   return {page,score:matches?words.reduce((score,word)=>score+(title.includes(word)?12:0)+(description.includes(word)?4:0)+(text.includes(word)?1:0),0):-1};
  }).filter(item=>item.score>=0&&(words.length||['/docs/getting-started','/docs/wallets','/docs/spot','/docs/algorithms','/docs/community-tokens','/docs/agents'].includes(item.page.url))).sort((a,b)=>b.score-a.score).slice(0,12);
  results.replaceChildren();selected=-1;
  for(const {page} of ranked){
   const link=document.createElement('a');link.href=page.url;
   for(const [className,text] of [['p-result-group',page.group],['p-result-title',page.title],['p-result-excerpt',excerpt(page,words)]]){
    const span=document.createElement('span');span.className=className;span.textContent=text;link.append(span);
   }
   link.addEventListener('pointermove',()=>setSelected([...results.children].indexOf(link)));
   results.append(link);
  }
  searchCount.textContent=words.length?(ranked.length?`${ranked.length} result${ranked.length===1?'':'s'}`:'No matching guides. Try “wallet”, “fees” or “buyback”.'):'Popular guides';
  if(ranked.length)setSelected(0);
 }catch{
  if(generation!==searchGeneration||!searchDialog.open)return;
  results.replaceChildren();searchCount.textContent='Search is temporarily unavailable. Browse the documentation menu or try again.';
 }
}
searchInput?.addEventListener('input',renderSearch);
searchDialog?.addEventListener('keydown',event=>{
 if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();setSelected(selected+(event.key==='ArrowDown'?1:-1),true);}
 if(event.key==='Enter'&&event.target===searchInput){event.preventDefault();results.querySelector('[data-selected]')?.click();}
});
document.addEventListener('keydown',event=>{
 if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){event.preventDefault();openDialog(searchDialog,document.activeElement);}
});
let toastTimer;
function toast(message){
 const element=document.querySelector('.p-toast');element.textContent=message;element.setAttribute('data-visible','');
 clearTimeout(toastTimer);toastTimer=setTimeout(()=>element.removeAttribute('data-visible'),2400);
}
async function copy(text){
 try{await navigator.clipboard.writeText(text);toast('Copied to clipboard');return true;}
 catch{toast('Copy unavailable. Select the text or copy from the address bar.');return false;}
}
document.querySelector('[data-copy-link]')?.addEventListener('click',()=>copy(location.href));
document.querySelectorAll('[data-copy-code]').forEach(button=>button.addEventListener('click',async()=>{
 if(await copy(button.closest('.p-code').querySelector('code').textContent)){button.textContent='Copied';setTimeout(()=>button.textContent='Copy',1600);}
}));
const tocLinks=[...document.querySelectorAll('.p-toc a')];
const headings=tocLinks.map(link=>document.getElementById(link.hash.slice(1))).filter(Boolean);
let scrolling=false;
function markSection(){
 const offset=parseInt(getComputedStyle(document.documentElement).getPropertyValue('--top'))+64;
 const heading=[...headings].reverse().find(item=>item.getBoundingClientRect().top<=offset)||headings[0];
 for(const link of tocLinks){if(link.hash==='#'+heading?.id)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');}
 scrolling=false;
}
addEventListener('scroll',()=>{if(!scrolling){scrolling=true;requestAnimationFrame(markSection);}},{passive:true});
addEventListener('resize',markSection);markSection();
document.querySelectorAll('.p-mobile-toc a').forEach(link=>link.addEventListener('click',()=>link.closest('details').open=false));
