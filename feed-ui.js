// Reading state only. No account, market or financial requests.
export function feedUI({S,$,esc,icon,safeURL,scope}){
 const expanded=new Map(),visible=new Set();let root,observer,resize,frame=0,width=0,measured=new WeakMap();
 const key=id=>scope()+'|'+id;
 const isExpanded=id=>expanded.get(key(id))===true;
 function source(p){const raw=p.source||p.text.match(/https:\/\/[^\s<>]+/)?.[0];if(!raw)return null;const url=safeURL(raw);if(url==='#')return null;try{return {url,host:new URL(url).hostname.replace(/^www\./,'')};}catch{return null;}}
 function text(p){if(S.view==='post')return p.text;const link=source(p);if(!link)return p.text;const tail=p.text.match(/(?:^|\n)\s*(https:\/\/[^\s<>]+)\s*$/);return tail&&safeURL(tail[1])===link.url?p.text.slice(0,tail.index).trim():p.text;}
 function link(p){const s=source(p);return s?`<a class="r-link-card" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"><span>${icon('link')}<b>${esc(s.host)}</b></span>${icon('external')}</a>`:'';}
 function dispose(){observer?.disconnect();resize?.disconnect();cancelAnimationFrame(frame);frame=0;visible.clear();measured=new WeakMap();root=null;}
 function measure(){frame=0;const updates=[];for(const article of visible){const state=width+'|'+isExpanded(article.dataset.post);if(measured.get(article)===state)continue;const body=$('.r-post-body',article),button=$('.r-post-read',article);if(body&&button){updates.push([button,isExpanded(article.dataset.post)||body.scrollHeight>body.clientHeight+1]);measured.set(article,state);}}for(const [button,show] of updates)button.hidden=!show;}
 function schedule(){if(!frame)frame=requestAnimationFrame(measure);}
 function sync(){
  const timeline=$('#timeline');if(!timeline)return;
  if(root!==timeline){dispose();root=timeline;width=root.clientWidth;observer=new IntersectionObserver(entries=>{for(const e of entries){if(e.isIntersecting)visible.add(e.target);else visible.delete(e.target);}schedule();},{rootMargin:'160px 0px'});resize=new ResizeObserver(entries=>{const next=entries[0].contentRect.width;if(next!==width){width=next;schedule();}});resize.observe(root);}
  for(const article of root.querySelectorAll('.r-post:not([data-reading-bound])')){article.dataset.readingBound='';observer.observe(article);}
 }
 function expand(id,button){
  const article=button.closest('.r-post');if(!article)return;const was=isExpanded(id),before=button.getBoundingClientRect().top;
  expanded.delete(key(id));expanded.set(key(id),!was);while(expanded.size>128)expanded.delete(expanded.keys().next().value);
  article.classList.toggle('is-expanded',!was);button.setAttribute('aria-expanded',String(!was));button.textContent=was?'Read more':'Show less';
  // Keep the collapse control at its reading position when a long post shrinks.
  if(was&&article.getBoundingClientRect().top<0)window.scrollBy({top:button.getBoundingClientRect().top-before,behavior:'instant'});schedule();
 }
 function anchor(){const edge=$('.r-feed-toolbar')?.getBoundingClientRect().bottom||0;return [...visible].filter(el=>el.isConnected).map(el=>{const r=el.getBoundingClientRect();return {id:el.dataset.post,visible:Math.max(0,Math.min(r.bottom,innerHeight)-Math.max(r.top,edge))};}).sort((a,b)=>b.visible-a.visible)[0]?.id;}
 function prepareRestore(id){
  const article=root?.querySelector('[data-post="'+CSS.escape(id)+'"]');if(!article)return;
  // Settle only the reading anchor and its neighbours before restoring its offset.
  for(const el of [article.previousElementSibling,article,article.nextElementSibling])if(el?.matches('.r-post')){el.style.contentVisibility='visible';visible.add(el);measured.delete(el);}
  measure();
 }
 function feedback(post,kind,pending=false){
  const selected=Boolean(kind==='like'?post.liked:post.saved);
  for(const button of document.querySelectorAll(`[data-action="${kind}"][data-id="${CSS.escape(post.id)}"]`)){
   button.classList.toggle(kind==='like'?'liked':'saved',selected);
   button.setAttribute('aria-pressed',String(selected));button.setAttribute('aria-busy',String(pending));button.disabled=pending;
   button.setAttribute('aria-label',(kind==='like'?(selected?'Unlike':'Like'):(selected?'Unsave':'Save'))+' post');
   if(kind==='like'){const count=button.querySelector('span');if(count)count.textContent=post.likes||'';}
  }
 }
 return {sync,dispose,isExpanded,expand,text,link,anchor,prepareRestore,feedback};
}
