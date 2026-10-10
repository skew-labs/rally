export function communityUI(c){
  const {S,$,api,esc,icon,avatar,age,modal,closeModal,notify,boot,navigate,pageHeader,postCard,loading,empty,needAccount}=c;
  let searchSequence=0;
  const runs=new Map(),seen=new Set();let observer;const pending=new Map();let exposureTimer;
  const formError=(f,e)=>{$('.r-form-error',f).textContent=e.message;$('[type=submit]',f).disabled=false;};
  function recover(){
    modal('Recover account',`<form id="recover-form"><label class="r-field">Username<input name="handle" autocomplete="username" required></label><label class="r-field">Recovery code<input name="code" autocomplete="off" required></label><label class="r-field">New password<input name="password" type="password" minlength="10" autocomplete="new-password" required></label><p class="r-note">Existing sessions and agent connections will be revoked.</p><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Reset password</button></form>`);
    $('#recover-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;$('[type=submit]',f).disabled=true;try{await api('/api/auth/recover',Object.fromEntries(new FormData(f)));closeModal();notify('Password reset. Sign in again.');}catch(e){formError(f,e);}};
  }
  function recovery(){
    modal('Recovery codes',`<form id="codes-form"><label class="r-field">Current password<input name="password" type="password" autocomplete="current-password" required></label><p class="r-note">Save these offline. Generating new codes replaces your old codes.</p><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Generate codes</button></form>`);
    $('#codes-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;$('[type=submit]',f).disabled=true;try{const r=await api('/api/auth/recovery-codes',Object.fromEntries(new FormData(f)));modal('Save your recovery codes',`<p class="r-note">Each code works once. These are shown only here.</p><pre class="r-code">${r.codes.map(esc).join('\n')}</pre><button class="r-btn primary full" id="download-codes">Download codes</button>`);$('#download-codes').onclick=()=>{const url=URL.createObjectURL(new Blob(['Rally recovery codes · @'+S.boot.me.handle+'\n\n'+r.codes.join('\n')],{type:'text/plain'}));const a=document.createElement('a');a.href=url;a.download='rally-recovery-codes.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),500);};}catch(e){formError(f,e);}};
  }
  async function blocks(){
    const d=await api('/api/blocks');modal('Blocked profiles',d.profiles.map(p=>`<div class="r-person-row">${avatar(p)}<span><b>${esc(p.name)}</b><small>@${esc(p.handle)}</small></span><button class="r-btn small" data-action="unblock" data-id="${esc(p.id)}">Unblock</button></div>`).join('')||'<p class="r-note">No blocked profiles.</p>');
  }
  async function reports(){
    const d=await api('/api/reports');modal('Your reports',d.reports.map(r=>`<div class="r-person-row"><span><b>${esc(r.reason[0].toUpperCase()+r.reason.slice(1))}</b><small>${age(r.created)} · ${esc(r.status)}</small></span></div>`).join('')||'<p class="r-note">No reports.</p>');
  }
  async function notifications(){
    if(!S.boot.me){$('#page').innerHTML=pageHeader('Notifications')+empty('Sign in','Replies, follows and reactions.','<button class="r-btn primary" data-action="account">Sign in</button>');return;}
    $('#page').innerHTML=pageHeader('Notifications')+loading();
    const d=await api('/api/notifications');if(S.view!=='notifications')return;
    $('#page').innerHTML=pageHeader('Notifications',`<button class="r-btn small" data-action="push-settings">Settings</button><button class="r-btn small" data-action="notices-read">Mark all read</button>`)+d.notifications.map(n=>`<button class="r-notice ${n.seen?'':'unread'}" data-action="notice-open" data-id="${esc(n.id)}">${avatar(n.actor)}<span><b>${esc(n.detail?.title||n.actor.name)}</b> ${({follow:'followed you',like:'liked your post',reply:'replied to you',repost:'reposted your post',algorithm:'published a creator update'})[n.kind]||''}<small>${esc(n.detail?.body||n.text)}</small></span><time>${age(n.created)}</time></button>`).join('');
    if(!d.notifications.length)$('#page').insertAdjacentHTML('beforeend',empty('All caught up','New activity appears here.'));
    S.notices=d.notifications;
  }
  function postMenu(id){
    const p=S.posts.find(p=>p.id===id);if(!p)return;
    const own=p.author.id===S.boot.me?.id;
    modal('Post',`<div class="r-account-options">${own?`<button data-action="edit-post" data-id="${esc(id)}">${icon('image')}Edit post</button><button data-action="delete" data-id="${esc(id)}">${icon('close')}Delete post</button>`:`<button data-action="report-post" data-id="${esc(id)}">${icon('ellipsis')}Report post</button><button data-action="block-profile" data-id="${esc(p.author.id)}">${icon('user')}Block @${esc(p.author.handle)}</button>`}<button data-action="share" data-id="${esc(id)}">${icon('link')}Copy link</button></div>`);
  }
  function edit(id){
    const p=S.posts.find(p=>p.id===id);if(!p)return;
    modal('Edit post',`<form id="edit-post-form"><textarea class="r-compose-text" name="text" maxlength="4000" aria-label="Post text">${esc(p.text)}</textarea><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Save</button></form>`);
    $('#edit-post-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;$('[type=submit]',f).disabled=true;try{await api('/api/post/edit',{id,version:p.version,text:new FormData(f).get('text')});closeModal();notify('Post updated');await c.render();}catch(e){formError(f,e);}};
  }
  function report(id){
    modal('Report post',`<form id="report-form"><label class="r-field">Reason<select name="reason"><option value="spam">Spam</option><option value="scam">Scam</option><option value="harassment">Harassment</option><option value="other">Other</option></select></label><p class="r-note">Your report is private. Reporting does not automatically remove a post.</p><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Submit report</button></form>`);
    $('#report-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/post/report',{id,reason:new FormData(e.currentTarget).get('reason')});closeModal();notify('Report received');}catch(err){formError(e.currentTarget,err);}};
  }
  function search(){
    modal('Search',`<label class="r-input-search">${icon('search')}<input type="search" id="search-all" placeholder="Tokens, people, posts" aria-label="Search Rally" autocomplete="off"></label><div id="search-state" class="r-muted" role="status" aria-live="polite"></div><div id="search-results"></div>`,'r-search-modal');
    const input=$('#search-all'),host=$('#search-results'),state=$('#search-state');let timer,controller;
    const hints=()=>{const picks=[...S.boot.watches.map(c.token),...S.tokens.filter(t=>['MON','USDC'].includes(t.symbol))].filter(Boolean);const unique=picks.filter((t,i,a)=>a.findIndex(x=>x.id===t.id)===i).slice(0,3);host.innerHTML=`<div class="r-search-hint">${unique.map(t=>`<button data-search-query="${esc(t.symbol)}">${esc(t.symbol)}</button>`).join('')}</div>`;state.textContent='';};
    const group=(name,html)=>html?`<section class="r-search-group"><h3>${name}</h3>${html}</section>`:'';
    hints();S.modal.cleanup=()=>{searchSequence++;clearTimeout(timer);controller?.abort();};
    host.onclick=e=>{const button=e.target.closest('[data-search-query]');if(button){input.value=button.dataset.searchQuery;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus({preventScroll:true});}};
    input.onkeydown=e=>{if(e.key==='ArrowDown'){const first=host.querySelector('[data-action="search-trade"],[data-action="profile"],[data-action="community"],[data-action="open-post"]');if(first){e.preventDefault();first.focus({preventScroll:true});}}};
    input.oninput=()=>{
      clearTimeout(timer);controller?.abort();const sequence=++searchSequence,q=input.value.trim();if(q.length<2){hints();return;}
      state.textContent='';host.innerHTML=loading();
      timer=setTimeout(async()=>{
        controller=new AbortController();
        try{const d=await api('/api/search?q='+encodeURIComponent(q),undefined,{signal:controller.signal});if(sequence!==searchSequence||!host.isConnected)return;
          d.posts.forEach(p=>{if(!S.posts.some(x=>x.id===p.id))S.posts.push(p);});const assets=S.tokens.filter(t=>(t.name+' '+t.symbol+' '+t.address).toLowerCase().includes(q.toLowerCase())).slice(0,6);
          const count=assets.length+d.people.length+d.communities.length+d.posts.length;state.textContent=count?count+(count===1?' result':' results'):'';
          host.innerHTML=group('Tokens',assets.map(t=>`<button class="r-search-result" data-action="search-trade" data-id="${esc(t.id)}">${c.logo(t)}<span><b>${esc(t.symbol)}</b><small>${esc(t.name)}</small></span></button>`).join(''))+group('People',d.people.map(c.personRow).join(''))+group('Communities',d.communities.map(p=>`<button class="r-search-result" data-action="community" data-id="${esc(p.id)}"><span><b>${esc(p.name)}</b><small>${esc(p.description||'')}</small></span></button>`).join(''))+group('Posts',d.posts.map(p=>`<button class="r-search-post" data-action="open-post" data-id="${esc(p.id)}"><b>@${esc(p.author.handle)}</b><p>${esc(p.text.slice(0,240))}</p></button>`).join(''))||'<p class="r-note">No results.</p>';
        }catch(error){if(error.name!=='AbortError'&&sequence===searchSequence&&host.isConnected){host.textContent=error.message;state.textContent='';}}
      },220);
    };
  }
  function formula(existing=null){
    needAccount(()=>{
      modal(existing?'New version':'Create algorithm',`<form id="algorithm-form"><label class="r-field">Name<input name="name" maxlength="32" required value="${esc(existing?.name||'')}" placeholder="My feed"></label><label class="r-field">Ranking formula<textarea class="r-formula" name="expression" maxlength="1000" spellcheck="false" required>${esc(existing?.expression||'60 * recency + 30 * watched + 10 * following')}</textarea></label><div class="r-feature-chips">${['recency','likes','replies','watched','following','has_media','is_agent','has_asset'].map(f=>`<code>${f}</code>`).join('')}</div><p class="r-note">Numbers, + − × /, comparisons and if / else. Each version gets its own feed.</p><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Publish algorithm</button></form>`,'r-wide-modal');
      $('#algorithm-form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;$('[type=submit]',f).disabled=true;try{const d=Object.fromEntries(new FormData(f));if(existing)d.algorithm=existing.algorithm;const r=await api('/api/algorithms/create',d);await boot();closeModal();S.feed=r.feed;await navigate('feed');}catch(e){formError(f,e);}};
    });
  }
  async function algorithms(){
    $('#page').innerHTML=pageHeader('Algorithms')+loading();const d=await api('/api/algorithms');if(S.view!=='algorithms')return;S.algorithms=d.algorithms;
    $('#page').innerHTML=pageHeader('Algorithms',`<button class="r-btn primary" data-action="algorithm-create">${icon('plus')}Create</button>`)+`<div class="r-tabs"><button data-nav="feeds">Feeds</button><button class="active">Algorithms</button><button data-action="algorithm-leaderboard">Leaderboard</button><button data-action="weekly-league">Weekly league</button><button data-action="algorithm-duel">Pick a feed</button><button data-action="algorithm-compare">Compare selected</button></div><div class="r-algorithm-list">${d.algorithms.map(a=>{const f=S.boot.feeds.find(f=>f.algorithm_version===a.id);return `<article class="r-algorithm-card"><div class="r-algorithm-head"><label><input type="checkbox" name="compare-version" value="${esc(a.id)}" aria-label="Compare ${esc(a.name)} v${a.version}"><b>${esc(a.name)}</b><span class="r-pill">v${a.version}</span></label><button data-action="profile" data-id="${esc(a.owner)}">@${esc(a.author.handle)}</button></div><code>${esc(a.expression)}</code><div class="r-algorithm-meta"><span>${a.measuredRuns} measured runs</span><span>${a.medianRuntimeMs==null?'—':a.medianRuntimeMs+' ms'}</span><span>${a.impressions} viewed</span><span>${a.engagementRate==null?'—':a.engagementRate+'%'} engaged</span><span>${a.readerChoices} reader choices</span></div><div class="r-algorithm-foot">${f?`<button class="r-btn small" data-action="feed-detail" data-id="${esc(f.id)}">Preview feed</button>`:''}${a.owner===S.boot.me?.id?`<button class="r-text-button" data-action="algorithm-version" data-id="${esc(a.id)}">New version</button>`:''}</div></article>`;}).join('')||empty('Choose how your feed ranks','Publish a formula, preview it, and use it.','<button class="r-btn primary" data-action="algorithm-create">Create algorithm</button>')}</div><p class="r-note">Compare the same recent posts. Runtime and reader events are measured; they do not predict returns.</p>`;
  }
  async function compare(){
    const versions=[...document.querySelectorAll('[name=compare-version]:checked')].map(x=>x.value);
    if(!versions.length||versions.length>4){notify('Select one to four versions');return;}
    needAccount(async()=>{modal('Comparing…',loading(),'r-wide-modal');try{const d=await api('/api/algorithms/compare',{versions});S.algorithmMatch=d.match;modal('Compare algorithms',`<p class="r-note">${d.candidateIds.length} identical candidates · top 10</p><div class="r-comparison-scroll"><table class="r-compare-table"><thead><tr><th>Algorithm</th><th>Authors</th><th>Assets</th><th>Watchlist</th><th>Runtime</th></tr></thead><tbody>${d.comparisons.map(r=>`<tr><td>${esc(r.name)}</td><td>${r.metrics.topAuthors}</td><td>${r.metrics.topAssets}</td><td>${r.metrics.watchMatches}</td><td>${r.metrics.runtimeMs} ms</td></tr>`).join('')}</tbody></table></div>${d.comparisons.map(r=>`<details class="r-ranking-details"><summary>${esc(r.name)} · ranked posts</summary><button class="r-btn small" data-action="algorithm-choose" data-id="${esc(r.version)}">Use this feed</button><ol>${r.posts.map(p=>`<li><button data-action="open-post" data-id="${esc(p.id)}">@${esc(p.author.handle)} · ${esc(p.text.slice(0,90))}</button></li>`).join('')}</ol></details>`).join('')}`,'r-wide-modal');}catch(e){closeModal();notify(e.message);}});
  }
  let routeTimer;
  function scheduleRoutes(){
    clearTimeout(routeTimer);const t=S.trade;
    if(t&&!t.busy&&!t.quote&&!t.submittedHash&&Number.isFinite(Number(t.amount))&&Number(t.amount)>0)routeTimer=setTimeout(()=>{if(S.trade===t)routes();},450);
  }
  async function routes(){
    const trade=S.trade;if(!trade||trade.busy||trade.quote||trade.submittedHash)return;
    clearTimeout(routeTimer);trade.routeController?.abort();const controller=new AbortController();trade.routeController=controller;
    const version=trade.routeVersion=(trade.routeVersion||0)+1,amount=trade.amount,input=trade.input,box=$('#route-comparison'),button=$('[data-action=compare-routes]');if(!box||!button)return;
    box.innerHTML='<div class="r-route-progress" role="status">Finding routes…</div>';button.disabled=true;trade.manualRoute=false;
    const current=()=>S.trade===trade&&trade.routeVersion===version&&trade.amount===amount&&trade.input===input&&box.isConnected;
    const paint=d=>{trade.routes=d;box.innerHTML=d.routes.map(r=>`<button class="r-route-row ${trade.provider===r.provider?'selected':''}" data-action="route-select" data-id="${esc(r.provider)}" ${r.state==='quoted'?'':'disabled'}><b>${esc(r.provider)}</b><span>${r.state==='quoted'?esc(Number(r.output).toLocaleString('en-US',{maximumSignificantDigits:8}))+' '+esc(c.token(trade.asset)?.symbol):r.state==='checking'?'Checking…':'No quote'}</span>${r.provider===d.best?'<em>Highest received output</em>':''}</button>`).join('')+`<div id="route-selected"></div><div class="r-route-progress" role="status">${d.complete?'Comparison complete':d.routes.filter(r=>r.state==='checking').length+' routes pending'} · excludes gas · ${Math.max(0,Math.ceil(d.expires-Date.now()/1000))}s validity</div>`;};
    try{
      let d=await api('/api/routes',{input,output:trade.asset,amount,progressive:true},{signal:controller.signal});
      while(current()){
        if(trade.busy||trade.quote||trade.submittedHash)return;
        paint(d);
        if(d.best&&!trade.manualRoute)await routeSelect(d.best,false);
        if(!current()||d.complete)break;
        await new Promise(resolve=>setTimeout(resolve,650));if(!current())break;
        d=await api('/api/routes/status?id='+encodeURIComponent(d.id),undefined,{signal:controller.signal});
      }
    }catch(e){if(current()&&e.name!=='AbortError')box.textContent=e.message;}
    finally{if(current()&&button.isConnected)button.disabled=trade.busy||!Number.isFinite(Number(trade.amount))||Number(trade.amount)<=0;}
  }
  async function routeSelect(provider,manual=true){
    const trade=S.trade,d=trade?.routes;if(!d||trade.busy||trade.quote||trade.submittedHash||S.financialBusy)return;
    const sequence=trade.selectionSequence=(trade.selectionSequence||0)+1,input=trade.input,amount=trade.amount,version=trade.version||0;
    if(manual)trade.manualRoute=true;
    const current=()=>S.trade===trade&&trade.routes===d&&trade.selectionSequence===sequence&&trade.input===input&&trade.amount===amount&&(trade.version||0)===version&&!trade.busy&&!trade.quote&&!trade.submittedHash&&!S.financialBusy;
    try{
      const saved=trade.routeSelection;
      const r=saved?.quote===d.id&&saved.selected.provider===provider&&saved.expires>Date.now()/1000?saved:await api('/api/routes/select',{quote:d.id,provider,input,output:trade.asset,amount});if(!current())return;
      trade.routeSelection=r;
      trade.provider=r.selected.provider;$('#swap-button').textContent=S.boot.wallet?(trade.side==='sell'?'Sell':'Buy'):'Connect wallet';$('#swap-output').textContent=r.selected.output;
      const detail=r.selected.details,host=$('#route-selected');if(host)host.innerHTML=`<div class="r-route-detail"><b>${esc(r.selected.provider)}${r.fallback?' · Alternative':''}</b>${detail.feeBps!=null?`<span>Pool fee ${detail.feeBps/100}%</span>`:''}${detail.nativeWrap?'<span>Native MON wraps through WMON</span>':''}<small>Reference output. A fresh quote is required before approval.</small></div>`;
      $('.r-swap-title span').textContent=r.selected.provider;$('.r-route-tabs button.active').textContent='Spot · '+r.selected.provider;document.querySelectorAll('.r-route-row').forEach(el=>el.classList.toggle('selected',el.dataset.id===r.selected.provider));
    }catch(e){if(current()&&$('#route-selected'))$('#route-selected').innerHTML=`<p class="r-note">${esc(e.message)}</p><button class="r-btn small" data-action="compare-routes">Refresh quotes</button>`;}
  }
  function observe(posts,run,reset=false){
    if(reset){runs.clear();observer?.disconnect();}
    if(!run||!S.boot.me)return;
    for(const p of posts)runs.set(p.id,run);
    if(runs.size>200)for(const id of [...runs.keys()].slice(0,runs.size-200))runs.delete(id);
    observer?.disconnect();
    observer=new IntersectionObserver(entries=>{for(const e of entries){if(e.intersectionRatio<.5||document.hidden||S.modal||S.trade)continue;const id=e.target.dataset.post,run=runs.get(id),key=run+':'+id;if(!run||seen.has(key))continue;seen.add(key);if(!pending.has(run))pending.set(run,new Set());pending.get(run).add(id);clearTimeout(exposureTimer);exposureTimer=setTimeout(()=>{for(const [run,ids] of pending)api('/api/algorithms/event',{run,kind:'impression',posts:[...ids].slice(0,30)}).catch(()=>{});pending.clear();},300);}}, {threshold:.5});
    document.querySelectorAll('#timeline [data-post]').forEach(p=>observer.observe(p));
  }
  async function track(kind,id){const run=runs.get(id);if(run&&S.boot.me)api('/api/algorithms/event',{run,post:id,kind}).catch(()=>{});}
  async function poll(){if(document.hidden||!S.boot.me)return;const d=await api('/api/notifications');S.boot.unread=d.unread;document.querySelectorAll('[data-nav=notifications]').forEach(el=>{el.querySelector('.r-unread')?.remove();if(d.unread)el.insertAdjacentHTML('beforeend',`<b class="r-unread">${d.unread}</b>`);});}
  async function leaderboard(){
    $('#page').innerHTML=pageHeader('Algorithms')+loading();const d=await api('/api/algorithms/leaderboard');if(S.view!=='algorithms')return;
    $('#page').innerHTML=pageHeader('Algorithms',`<button class="r-btn primary" data-action="algorithm-duel">Pick a feed</button>`)+`<div class="r-tabs"><button data-action="algorithm-directory">Directory</button><button class="active">Leaderboard</button></div><div class="r-comparison-scroll"><table class="r-compare-table r-leaderboard"><thead><tr><th>Rank</th><th>Feed</th><th>Votes</th><th>Preference</th><th>Viewed</th><th>Engaged</th></tr></thead><tbody>${d.entries.map(a=>`<tr><td>${a.rank||'—'}</td><td><b>${esc(a.name)} · v${a.version}</b><small>@${esc(a.author.handle)}</small></td><td>${a.ballots}</td><td>${a.winRate==null?'—':a.winRate+'%'}</td><td>${a.impressions}</td><td>${a.engagementRate==null?'—':a.engagementRate+'%'}</td></tr>`).join('')}</tbody></table></div>${!d.entries.length?empty('No algorithms yet','Publish a feed to enter the directory.'):''}<p class="r-note">${d.minimumBallots} reader votes to rank. Viewed and engaged: last 30 days. Creator activity is excluded.</p>`;
  }
  async function duel(){
    needAccount(async()=>{modal('Pick a feed',loading(),'r-wide-modal');try{const d=await api('/api/algorithms/duel',{});S.duel=d;modal('Pick a feed',`<p class="r-note">Same ${d.candidates} posts. Choose the order you prefer.</p><div class="r-duel">${d.sides.map(r=>`<section><h3>Feed ${r.side.toUpperCase()}</h3><ol>${r.posts.map(p=>`<li><b>@${esc(p.author.handle)}</b><p>${esc(p.text.slice(0,180))}</p>${p.media?'<span class="r-pill">'+(p.media.mime.startsWith('video/')?'Video':'Image')+'</span>':''}</li>`).join('')}</ol><button class="r-btn primary full" data-action="algorithm-vote" data-id="${r.side}">Choose ${r.side.toUpperCase()}</button></section>`).join('')}</div>`,'r-wide-modal');}catch(e){modal('Pick a feed',`<p class="r-note">${esc(e.message)}</p><button class="r-btn full" data-action="close-modal">Close</button>`);}});
  }
  async function vote(side){
    const button=$(`[data-action=algorithm-vote][data-id=${side}]`);if(button)button.disabled=true;
    try{const d=await api('/api/algorithms/vote',{match:S.duel.match,side});modal('Vote saved',`<div class="r-account-options">${d.algorithms.map(a=>`<button data-action="feed-detail" data-id="${esc(a.feed)}"><span><b>${esc(a.name)}${a.id===d.chosen?' · Your pick':''}</b><small>@${esc(a.creator.handle)}</small></span>${icon('chevron')}</button>`).join('')}</div><button class="r-btn primary full" data-action="use-feed" data-id="${esc(d.feed)}">Use this feed</button>`);}catch(e){notify(e.message);if(button)button.disabled=false;}
  }
  async function handle(action,id,el){
    if(action==='recover'){recover();return true;}
    if(action==='recovery-codes'){recovery();return true;}
    if(action==='blocked'){await blocks();return true;}
    if(action==='reports'){await reports();return true;}
    if(action==='unblock'){await api('/api/block',{id,active:false});await boot();await blocks();return true;}
    if(action==='post-menu'){needAccount(()=>postMenu(id));return true;}
    if(action==='edit-post'){edit(id);return true;}
    if(action==='report-post'){report(id);return true;}
    if(action==='block-profile'){await api('/api/block',{id,active:true});closeModal();await boot();await navigate('home');notify('Profile blocked');return true;}
    if(action==='repost'){needAccount(async()=>{const p=S.posts.find(p=>p.id===id);await api('/api/post/repost',{id,active:!p.reposted});await c.render();});return true;}
    if(action==='notices-read'){await api('/api/notifications/read',{ids:(S.notices||[]).map(n=>n.id)});await boot();await notifications();return true;}
    if(action==='algorithm-create'){formula();return true;}
    if(action==='algorithm-version'){formula(S.algorithms.find(a=>a.id===id));return true;}
    if(action==='algorithm-choose'){await api('/api/algorithms/choose',{match:S.algorithmMatch,version:id});await boot();closeModal();S.mode='for-you';S.homeSection='feed';await navigate('home');return true;}
    if(action==='algorithm-compare'){await compare();return true;}
    if(action==='algorithm-directory'){await algorithms();return true;}
    if(action==='algorithm-leaderboard'){await leaderboard();return true;}
    if(action==='algorithm-duel'){await duel();return true;}
    if(action==='algorithm-vote'){await vote(id);return true;}
    if(action==='notice-open'){const n=S.notices.find(n=>n.id===id);if(n){await api('/api/notifications/read',{ids:[id]});await poll();if(n.url){location.assign(n.url);}else if(n.post){S.post=n.post;await navigate('post');}else{S.profile=n.actor.id;await navigate('profile');}}return true;}
    if(action==='compare-routes'){await routes();return true;}
    if(action==='route-select'){await routeSelect(id);return true;}
    if(['reply','open-post'].includes(action))track('open',id);
    if(action==='trade'){const id=el.closest('[data-post]')?.dataset.post;if(id)track('trade_open',id);}
    return false;
  }
  return {scheduleRoutes,handle,notifications,search,algorithms,formula,recover,observe,track,poll};
}
