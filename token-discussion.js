// Compact conversation rows share identities and moderation with the main feed.
export function mentionText(c,p){
 const mentions=new Map((p.mentions||[]).map(m=>[m.handle.toLowerCase(),m]));
 return p.text.split(/(@[a-zA-Z0-9_]{3,24}\b)/g).map(part=>{const m=part[0]==='@'&&mentions.get(part.slice(1).toLowerCase());return m?`<button class="rd-mention" data-action="profile" data-id="${c.esc(m.id)}">${c.esc(part)}</button>`:c.esc(part).replace(/\n/g,'<br>');}).join('');
}
export function commentCard(c,p,{inside=false}={}){
 const {esc,avatar,logo,age}=c,t=c.token?.(p.asset)||p.assetInfo,paired=p.author.communityToken;
 const compact=!inside&&(p.text.length>180||p.text.split('\n').length>4);
 const symbol=t?.symbol||(p.asset?.startsWith('0x')?p.asset.slice(0,6)+'…'+p.asset.slice(-4):p.asset);
 return `<article class="rd-comment" data-post="${esc(p.id)}"><button class="rd-avatar" data-action="profile" data-id="${esc(p.author.id)}" aria-label="${esc(p.author.name)} profile">${avatar(p.author)}</button><div class="rd-comment-main"><header><button class="rd-author" data-action="profile" data-id="${esc(p.author.id)}"><b>${esc(p.author.name)}</b><span>@${esc(p.author.handle)}</span></button>${p.author.kind==='agent'?'<small class="rd-agent">Agent</small>':''}<time>${age(p.created)}</time><button class="rd-menu" data-action="post-menu" data-id="${esc(p.id)}" aria-label="Comment options">${c.icon('ellipsis')}</button></header>${p.replyTo?`<button class="rd-reply-to" data-action="reply" data-id="${esc(p.replyTo.id)}">↳ @${esc(p.replyTo.author.handle)}</button>`:''}<div class="rd-text${compact?' rd-preview':''}">${mentionText(c,p)}</div>${compact?'<button class="rd-expand" data-action="expand-comment" aria-expanded="false">Show more</button>':''}${p.media&&c.mediaCard?c.mediaCard(p.media,p.author.name):''}${!inside&&t?`<button class="rd-token" data-action="${t.nadfun?'nad-token':'market-detail'}" data-id="${esc(p.asset)}">${logo({...t,id:p.asset})}<b>${esc(symbol)}</b>${c.icon('chevron')}</button>`:''}<footer><button data-action="like" data-id="${esc(p.id)}" class="${p.liked?'liked':''}" aria-label="${p.liked?'Unlike':'Like'} comment">${c.icon('heart')}<span>${p.likes||''}</span></button><button ${inside?'data-discussion-reply':'data-action="reply"'} data-id="${esc(p.id)}" aria-label="Reply to ${esc(p.author.name)}">${c.icon('chat')}<span>${p.replies||'Reply'}</span></button>${paired?`<button class="rd-creator-token" data-action="creator-token" data-id="${esc(paired.address)}">${logo({...paired,id:paired.address})}${esc(paired.symbol)}</button>`:''}</footer></div></article>`;
}
export function mountDiscussion(c,host,asset){
 const {S,esc,api}=c;let cursor=null,reply=null,busy=false,loaded=false,generation=0,requestKey=crypto.randomUUID();const posts=new Map();
 host.classList.add('rd-discussion');
 host.innerHTML=`<form class="rd-compose"><div class="rd-compose-identity">${c.avatar(S.boot.me)}<span>${esc(S.boot.me?.name||'Join the conversation')}</span></div><div class="rd-reply-draft" hidden></div><div class="rd-compose-input"><textarea rows="1" maxlength="4000" aria-label="Comment on ${esc(asset.symbol)}" placeholder="Say something about $${esc(asset.symbol)}…"></textarea><button type="submit" aria-label="Post comment">${c.icon('arrow')}</button></div><div class="rd-error" role="alert"></div></form><div class="rd-comments" aria-live="polite"></div><button class="rd-more" hidden>Load more</button>`;
 const list=host.querySelector('.rd-comments'),form=host.querySelector('form'),input=form.querySelector('textarea'),error=form.querySelector('.rd-error'),more=host.querySelector('.rd-more');
 const remember=rows=>rows.forEach(p=>{posts.set(p.id,p);const i=S.posts.findIndex(x=>x.id===p.id);if(i<0)S.posts.push(p);else S.posts[i]=p;});
 async function load(append=false){if(busy||!host.isConnected)return;busy=true;const seq=++generation;more.disabled=true;
  if(!loaded)list.innerHTML='<p class="rd-empty" role="status">Loading conversation…</p>';
  try{const query=new URLSearchParams({discussion:'1',asset:asset.id,feed:'latest',mode:'for-you',...(append&&cursor?{cursor}:{})});const data=await api('/api/posts?'+query);if(!host.isConnected||seq!==generation)return;remember(data.posts);const html=data.posts.map(p=>commentCard(c,p,{inside:true})).join('');if(append)list.insertAdjacentHTML('beforeend',html);else list.innerHTML=html||'<p class="rd-empty">Be the first to comment.</p>';cursor=data.cursor;loaded=true;more.hidden=!cursor;error.textContent='';}
  catch(e){if(host.isConnected){if(!loaded)list.innerHTML='<button class="rd-retry">Retry conversation</button>';error.textContent=e.message;}}
  finally{busy=false;more.disabled=false;}
 }
 input.oninput=()=>{requestKey=crypto.randomUUID();input.style.height='auto';input.style.height=Math.min(120,input.scrollHeight)+'px';};
 function setReply(p){reply=p;const draft=form.querySelector('.rd-reply-draft');draft.hidden=!p;draft.innerHTML=p?`Replying to @${esc(p.author.handle)} <button type="button" class="rd-cancel-reply" aria-label="Cancel reply">×</button>`:'';input.placeholder=p?'Add a reply…':`Say something about $${asset.symbol}…`;if(p)input.focus({preventScroll:false});}
 form.onsubmit=event=>{event.preventDefault();if(!S.boot.me){c.needAccount(()=>input.focus());return;}if(busy||!input.value.trim())return;const owner=S.boot.me.id,text=input.value.trim(),parent=reply?.id;busy=true;form.querySelector('[type=submit]').disabled=true;error.textContent='';
  api('/api/posts',{text,asset:asset.id,...(parent?{parent}:{})},{key:requestKey}).then(p=>{if(!host.isConnected||owner!==S.boot.me?.id)return;remember([p]);list.querySelector('.rd-empty')?.remove();list.insertAdjacentHTML('afterbegin',commentCard(c,p,{inside:true}));input.value='';input.style.height='auto';requestKey=crypto.randomUUID();setReply(null);c.notify?.('Comment posted');}).catch(e=>{if(host.isConnected)error.textContent=e.message;}).finally(()=>{busy=false;form.querySelector('[type=submit]').disabled=false;});
 };
 host.addEventListener('click',e=>{const b=e.target.closest('[data-discussion-reply]');if(b){e.stopPropagation();setReply(posts.get(b.dataset.id));}if(e.target.closest('.rd-cancel-reply'))setReply(null);if(e.target.closest('.rd-retry'))load();});
 more.onclick=()=>load(true);
 return ()=>{if(!loaded)load();};
}
