// Social asset discovery and nad.fun's native MON routes use Rally's direct wallet flow.
export function nadfunUI(c){
  const {S,$,api,esc,icon,usd,age,modal,needAccount,walletReady,notify,navigate,pageHeader,empty,loading}=c;
  const short=x=>x?x.slice(0,6)+'…'+x.slice(-4):'—';
  const quantity=x=>x==null?'—':Number(x).toLocaleString('en-US',{maximumSignificantDigits:7});
  const img=(t,eager=false)=>c.logo(t,eager);
  const capFormat=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',notation:'compact',maximumSignificantDigits:3});
  const priceFormats=['standard','compact'].map(notation=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',notation,minimumFractionDigits:0,maximumSignificantDigits:4}));
  const cap=t=>t.marketCap==null||!Number.isFinite(Number(t.marketCap))?'—':capFormat.format(Number(t.marketCap));
  const price=n=>n==null||!Number.isFinite(Number(n))||Number(n)<0?'—':Number(n)>0&&Number(n)<.000001?'$'+Number(n).toExponential(3):priceFormats[Number(n)>=10000?1:0].format(Number(n));
  const metrics=(t,compact=false)=>`<b data-meme-cap title="Total-supply valuation (FDV)">${cap(t)}</b><small data-meme-price aria-label="Price ${esc(price(t.price))}" title="${t.price==null?'Price unavailable':esc('$'+t.price)}">${compact?'':'Price '}${price(t.price)}${t.stale&&t.price?' · Last '+esc(age(t.referenceAt)):''}</small>`;
  const phase=t=>t.locked?'Migrating':t.graduated?'DEX':'Bonding curve';
  let chartApi,chartSeries,chartSequence=0,pollAt=0,chartAt=0;
  const catalogRequests=new Map(),catalogCache=new Map();
  let listSequence=0,listState,listObserver;
  function fresh(data){return {...data,tokens:data.tokens.map(t=>{const elapsed=Date.now()/1000-(t.referenceAt||0),expired=elapsed>900||elapsed<0;return {...t,stale:elapsed>180||elapsed<0,priceAgeSeconds:Math.max(0,elapsed),...(expired?{price:null,marketCap:null,lastKnown:false}:{} )};})};}
  const remember=t=>{const i=S.tokens.findIndex(x=>x.id===t.id);if(i<0)S.tokens.push(t);else S.tokens[i]={...S.tokens[i],...t};};
  function dispose(){listSequence++;listObserver?.disconnect();c.checkout.disposeNad();chartSequence++;chartApi?.remove();chartApi=null;chartSeries=null;}
  async function catalog(phase='',sort='latest',force=false){
    const key=phase+':'+sort,query=new URLSearchParams({sort});if(phase)query.set('phase',phase);
    const cached=catalogCache.get(key);let data;
    if(!force&&cached&&Date.now()-cached.at<20000)data=fresh(cached.data);
    else{
      if(!catalogRequests.has(key))catalogRequests.set(key,api('/api/nadfun/tokens?'+query).then(data=>{catalogCache.set(key,{data,at:Date.now()});return data;}).finally(()=>{catalogRequests.delete(key);}));
      data=fresh(await catalogRequests.get(key));
    }
    data.tokens.forEach(remember);S[phase==='dex'?'nadGraduatedCatalog':'nadCatalog']=data;return data;
  }
  function row(t,index){return `<tr><td><button class="r-coin-cell" data-action="nad-token" data-id="${esc(t.id)}">${img(t,index<10)}<span class="r-market-identity"><b title="${esc(t.symbol)}">${esc(t.symbol)}</b><small title="${esc(t.name)}">${esc(t.name)}</small></span></button></td><td class="r-number nad-list-metrics" data-meme-token="${esc(t.id)}">${metrics(t,true)}</td><td><button class="nad-progress-cell" data-action="nad-token" data-id="${esc(t.id)}"><span>${phase(t)}${t.graduated?icon('arrow'): `<b>${(t.progressBps/100).toFixed(1)}%</b>`}</span><span class="nad-progress-track"><i style="width:${Math.min(100,t.progressBps/100)}%"></i></span></button></td><td class="r-number"><small>${age(t.created)}</small></td></tr>`;}
  function appendRows(){
    const state=listState;if(!state||!state.host.isConnected||S.marketTab!=='memes'||state.mode!==(S.nadMode||'cap'))return;
    const start=state.shown;state.shown=Math.min(state.tokens.length,start+24);
    state.host.querySelector('tbody').insertAdjacentHTML('beforeend',state.tokens.slice(start,state.shown).map((t,i)=>row(t,start+i)).join(''));
    const more=state.host.querySelector('.nad-load-more');more.innerHTML=`<span>${state.shown} of ${state.tokens.length} tokens</span>${state.shown<state.tokens.length?'<button class="r-text-button" data-action="nad-more">Load more</button>':''}`;
    if(state.shown>=state.tokens.length)listObserver?.disconnect();
  }
  function observeList(){
    listObserver?.disconnect();if(!listState?.host.isConnected||listState.shown>=listState.tokens.length)return;
    listObserver=new IntersectionObserver(entries=>{if(!S.nadOverlay&&!document.hidden&&entries.some(e=>e.isIntersecting))appendRows();},{rootMargin:'300px'});
    listObserver.observe(listState.host.querySelector('.nad-load-more'));
  }
  async function list(host,q='',force=false){
    const mode=S.nadMode||'cap',seq=++listSequence;listObserver?.disconnect();
    const data=await catalog(mode==='dex'?'dex':'',mode==='cap'?'cap':'latest',force);if(seq!==listSequence||!host.isConnected||S.marketTab!=='memes'||mode!==(S.nadMode||'cap'))return;
    const tokens=data.tokens.filter(t=>(t.name+' '+t.symbol+' '+t.address).toLowerCase().includes(q)&&(!S.watchOnly||S.boot.watches.includes(t.id))&&(mode!=='dex'||t.graduated));
    if(mode==='cap')tokens.sort((a,b)=>(b.marketCap==null?-1:Number(b.marketCap))-(a.marketCap==null?-1:Number(a.marketCap)));
    host.innerHTML=`<div class="nad-list-head"><div class="nad-filters">${[['cap','Mcap'],['new','Latest'],['dex','Graduated']].map(([id,label])=>`<button class="${mode===id?'selected':''}" data-action="nad-filter" data-id="${id}">${label}</button>`).join('')}</div><button class="r-btn primary small" data-action="nad-launch" aria-label="Launch token" title="Launch token">${icon('plus')}Launch token</button></div>${tokens.length?`<div class="r-table-wrap"><table class="r-market-table nad-table"><thead><tr><th>Token</th><th>Mcap / price</th><th>Progress</th><th>Age</th></tr></thead><tbody></tbody></table></div><div class="nad-load-more" aria-live="polite"></div>`:empty(data.error?'Launches unavailable':mode==='dex'?'No graduated tokens in this list':'No tokens found',data.error?'The last successful collection is kept. Try again shortly.':'Try a contract address or switch to Latest.',`<button class="r-btn" data-action="${/^0x[0-9a-f]{40}$/.test(q)?'nad-token':'nad-refresh'}" data-id="${esc(q)}">${/^0x[0-9a-f]{40}$/.test(q)?'Open token':'Refresh'}</button>`)}<div class="r-data-foot"><span>nad.fun · Total-supply cap (FDV)</span><span>${data.fetchedAt?'Updated '+age(data.fetchedAt):'Collecting new launches'}</span></div>${data.error&&tokens.length?'<p class="r-note">Collection is delayed. Quotes use the current contract state.</p>':''}`;
    listState=tokens.length?{host,tokens,mode,shown:0}:null;if(listState){appendRows();observeList();}
  }
  async function open(id,context=null,side='buy'){
    if(S.view!=='token'){
      c.closeTrade();c.closeModal();c.pauseMedia();
      const panel={id,context,side:side==='sell'?'sell':'buy',returnFocus:document.activeElement};S.nadOverlay=panel;
      $('#trade-root').innerHTML=`<div class="r-trade-scrim" data-action="nad-close"></div><aside class="r-trade-panel r-nad-panel" role="dialog" aria-modal="true" aria-label="Token trade"><div class="r-trade-head"><b>Token</b><button class="r-icon-button" data-action="nad-close" aria-label="Close token trade">${icon('close')}</button></div><div class="r-nad-content">${loading()}</div></aside>`;
      document.body.classList.add('r-trade-open');document.querySelectorAll('#app>.r-header,#app>.r-layout,#app>.r-mobile-nav').forEach(x=>{x.inert=true;x.setAttribute('aria-hidden','true');});
      $('.r-trade-head button')?.focus({preventScroll:true});
      await detail($('.r-nad-content'),panel);return;
    }
    if(S.view!=='token')S.nadReturn={view:S.view,scrollY:window.scrollY,post:S.post,feed:S.feed,profile:S.profile,community:S.community};
    S.nadToken=id;S.nadOrigin=context;S.nadIntentSide=side==='sell'?'sell':'buy';await navigate('token');
  }
  function closeOverlay(){
    const panel=S.nadOverlay;if(!panel)return;
    dispose();S.nadOverlay=null;S.nadQuote=null;S.nadDetail=null;
    $('#trade-root').replaceChildren();document.body.classList.remove('r-trade-open');
    document.querySelectorAll('#app>.r-header,#app>.r-layout,#app>.r-mobile-nav').forEach(x=>{x.inert=false;x.removeAttribute('aria-hidden');});
    if(panel.returnFocus?.isConnected)panel.returnFocus.focus({preventScroll:true});
    observeList();
  }
  async function detail(host=$('#page'),panel=null){
    dispose();const seq=chartSequence,id=panel?.id||S.nadToken;
    const current=()=>host.isConnected&&seq===chartSequence&&(panel?S.nadOverlay===panel:S.view==='token');
    host.innerHTML=(panel?'':pageHeader('Token'))+loading();
    try{
      const t=await api('/api/nadfun/token?token='+encodeURIComponent(id));if(!current())return;
      remember(t);S.nadDetail=t;S.nadQuote=null;S.nadOrderVersion=0;S.nadSide=panel?.side||S.nadIntentSide||'buy';S.nadIntentSide=null;if(panel)S.nadOrigin=panel.context;
      host.innerHTML=`<div class="r-page-head"><button class="nad-back r-text-button" data-action="nad-back">${icon('chevron')}${S.nadReturn?'Back':'Memes'}</button><div class="nad-token-actions"><button class="r-icon-button ${S.boot.watches.includes(t.id)?'saved':''}" data-action="watch" data-id="${esc(t.id)}" aria-label="Watch ${esc(t.symbol)}">${icon('star')}</button><button class="r-icon-button" data-action="nad-share" data-id="${esc(t.id)}" aria-label="Copy token link">${icon('share')}</button></div></div><section class="nad-identity"><div class="nad-token-title">${img(t)}<div><h1>${esc(t.name)}</h1><span>${esc(t.symbol)} <button class="r-text-button" data-action="nad-copy" data-id="${esc(t.id)}">${short(t.address)} ${icon('link')}</button></span></div></div><div class="nad-price"><span class="nad-cap-label">Market cap / FDV</span>${metrics(t)}</div></section>${c.originCard(S.nadOrigin)}<section class="nad-lifecycle"><span id="nad-phase" class="r-pill ${t.graduated?'good':''}">${phase(t)}</span><div class="nad-progress-track"><i id="nad-progress" style="width:${Math.min(100,t.progressBps/100)}%"></i></div><b id="nad-progress-label">${t.graduated?'100':(t.progressBps/100).toFixed(1)}%</b></section><section class="nad-chart-section"><div class="nad-chart-toolbar"><div class="nad-filters">${[['1','1m'],['15','15m'],['60','1h'],['240','4h']].map(([id,label])=>`<button data-action="nad-interval" data-id="${id}" class="${(S.nadInterval||'60')===id?'selected':''}">${label}</button>`).join('')}</div><span>USD</span></div><div id="nad-chart" aria-label="${esc(t.symbol)} candlestick chart">${loading()}</div><div class="r-data-foot"><a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a><span>nad.fun data</span></div></section><div class="nad-token-bottom"><section class="nad-order"><div class="r-order-directions"><button data-action="nad-side" data-id="buy" aria-pressed="${S.nadSide==='buy'}" class="${S.nadSide==='buy'?'selected':''}">Buy</button><button data-action="nad-side" data-id="sell" aria-pressed="${S.nadSide==='sell'}" class="${S.nadSide==='sell'?'selected':''}">Sell</button></div><form id="nad-order-form"><label class="nad-amount"><span>Amount <b id="nad-input-unit">${esc(S.nadSide==='sell'?t.symbol:t.quoteSymbol||'MON')}</b></span><input name="amount" type="text" inputmode="decimal" placeholder="0.00" autocomplete="off" required aria-label="Trade amount"></label><div class="nad-slippage"><label for="nad-slippage">Slippage</label><select id="nad-slippage" name="slippage"><option value="50">0.5%</option><option value="100" selected>1%</option><option value="300">3%</option><option value="500">5%</option></select></div><small id="nad-penalty" class="r-note" ${t.snipingPenaltyBps>0?'':'hidden'}>${t.snipingPenaltyBps>0?'Early-trade penalty: '+t.snipingPenaltyBps/100+'%':''}</small><div id="nad-quote"></div><div class="r-form-error" role="alert"></div><button type="submit" class="r-btn primary full" ${t.locked||t.tradeSupported===false?'disabled':''}>${t.locked?'Migrating':t.tradeSupported===false?'Quote asset unavailable':(S.nadSide==='sell'?'Sell':'Buy')}</button></form></section><section class="nad-facts"><h2>Token</h2><div class="r-summary"><span>Network</span><b>Monad</b><span>Market</span><b id="nad-market">${phase(t)}</b><span>Creator</span><a href="https://monadvision.com/address/${esc(t.creator)}" target="_blank" rel="noopener noreferrer">${short(t.creator)} ${icon('external')}</a><span>Contract</span><a href="https://monadvision.com/token/${esc(t.address)}" target="_blank" rel="noopener noreferrer">${short(t.address)} ${icon('external')}</a>${t.holders!=null?`<span>Holders</span><b>${quantity(t.holders)}</b>`:''}${t.creatorFeeBps!=null?`<span>Creator fee</span><b>${t.creatorFeeBps/100}%</b>`:''}</div><button class="r-btn subtle full" data-action="nad-post" data-id="${esc(t.id)}">${icon('plus')}Post about ${esc(t.symbol)}</button><a class="nad-source-link" href="https://nad.fun/tokens/${esc(t.id)}" target="_blank" rel="noopener noreferrer">nad.fun ${icon('external')}</a></section></div>`;
      host.insertAdjacentHTML('beforeend','<div id="nad-launch-social"></div>');c.launchPanel?.(t);
      if(panel){host.querySelector('.r-page-head').remove();$('.r-nad-panel').setAttribute('aria-label','Trade '+t.symbol);$('.r-trade-head>b').textContent=t.symbol;}
      const form=$('#nad-order-form');
      form.oninput=()=>{if(form.dataset.pending==='true')return;if(form.dataset.orderState!=='unknown')delete form.dataset.orderState;S.nadOrderVersion++;S.nadQuote=null;$('#nad-quote').innerHTML='';$('.r-form-error',form).textContent='';c.checkout.valid(form);};
      form.onsubmit=async e=>{
        e.preventDefault();if(form.dataset.pending==='true'||S.financialBusy)return;c.checkout.formBusy(form,true);const button=$('[type=submit]',form),error=$('.r-form-error',form);button.disabled=true;error.textContent='';
        const args={venue:'nadfun',kind:S.nadSide,token:t.id,amount:form.elements.amount.value,slippage:Number(form.elements.slippage.value),context:S.nadOrigin};
        try{await needAccount(async()=>{if(!await walletReady()||!form.isConnected)return;button.textContent='Opening wallet…';const plan=await api('/api/execution/plan',args);if(form.isConnected)await c.finance.review(plan);});}
        catch(e){if(error.isConnected)error.textContent=e.message;}
        finally{c.checkout.formBusy(form,false);c.checkout.valid(form);}
      };
      c.checkout.nad(t);
      mount(t,seq).catch(e=>{if($('#nad-chart')&&seq===chartSequence)$('#nad-chart').innerHTML=`<div class="nad-chart-empty">${esc(e.message)}<button class="r-btn small" data-action="nad-chart-retry">Retry chart</button></div>`;});
    }catch(e){if(current())host.innerHTML=(panel?'':pageHeader('Token'))+empty('Token unavailable',esc(e.message),`<button class="r-btn" data-action="${panel?'nad-close':'nad-back'}">${panel?'Close':S.nadReturn?'Back':'Back to Memes'}</button>`);}
  }
  async function mount(t,seq=chartSequence){
    const [lib,data]=await Promise.all([import('https://cdn.jsdelivr.net/npm/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.mjs'),api('/api/nadfun/chart?token='+encodeURIComponent(t.id)+'&interval='+(S.nadInterval||'60'))]);
    const host=$('#nad-chart');if(!host?.isConnected||seq!==chartSequence)return;
    if(!data.candles.length){host.innerHTML='<div class="nad-chart-empty">No trades in this interval</div>';return;}
    chartApi?.remove();host.replaceChildren();const css=getComputedStyle(document.documentElement);chartApi=lib.createChart(host,{autoSize:true,layout:{background:{type:lib.ColorType.Solid,color:css.getPropertyValue('--paper').trim()||'#101114'},textColor:css.getPropertyValue('--muted').trim()||'#979eac',fontFamily:'Inter, sans-serif',fontSize:11,attributionLogo:true},grid:{vertLines:{color:css.getPropertyValue('--line').trim()},horzLines:{color:css.getPropertyValue('--line').trim()}},rightPriceScale:{borderVisible:false},timeScale:{borderVisible:false,timeVisible:true},localization:{locale:'en-US'},handleScroll:{vertTouchDrag:false}});
    const close=data.candles.at(-1).close,precision=close<.0001?9:close<1?6:2;
    chartSeries=chartApi.addSeries(lib.CandlestickSeries,{upColor:'#63d6a0',downColor:'#ed7c89',borderVisible:false,wickUpColor:'#63d6a0',wickDownColor:'#ed7c89',priceFormat:{type:'price',precision,minMove:10**-precision}});chartSeries.setData(data.candles);chartAt=Date.now();
    if(data.candles.length<30)chartApi.timeScale().setVisibleLogicalRange({from:-30,to:data.candles.length+5});else chartApi.timeScale().fitContent();
  }
  async function launch(){
    const config=await api('/api/nadfun/config');
    modal('Launch token',`<form id="nad-launch-form"><div class="ct-create-scroll"><div class="ct-network"><span><img src="/assets/MON.png" alt="" width="18" height="18">Monad</span><span>nad.fun</span></div><label class="nad-image-upload"><span id="nad-image-preview">${icon('image')}<b>Token image</b><small>JPG, PNG or WebP · 5 MB max</small></span><input name="image" type="file" accept="image/png,image/jpeg,image/webp" required aria-label="Token image"></label><div class="nad-form-pair"><label class="r-field">Name<input name="name" maxlength="32" placeholder="Token name" required></label><label class="r-field">Symbol<input name="symbol" maxlength="10" pattern="[A-Za-z0-9]{1,10}" placeholder="TICKER" required></label></div><label class="r-field">Description <small>Optional</small><textarea name="description" maxlength="500" rows="2" placeholder="About your token"></textarea></label><details class="nad-launch-links"><summary>Links</summary><label class="r-field">Website<input name="website" type="url" placeholder="https://"></label><label class="r-field">X<input name="twitter" type="url" placeholder="https://x.com/"></label><label class="r-field">Telegram<input name="telegram" type="url" placeholder="https://t.me/"></label></details><div class="r-summary"><span>Launch fee</span><b>${esc(config.creationFeeMON)} MON + network fee</b><span>Creator fee</span><b>1%</b><span>Initial purchase</span><b>None</b></div></div><div class="ct-create-footer"><small class="ct-create-terms">Published on nad.fun · Creator fees go to its vault</small><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Launch token</button></div></form>`,'nad-launch-modal');
    const form=$('#nad-launch-form'),pending=S.nadLaunchInput?.actor===S.boot.me?.id?S.nadLaunchInput:null;let key=pending?.key||crypto.randomUUID(),objectURL,media=pending?.actor===S.boot.me?.id?pending.media:null,selectedFile=pending?.file;
    if(pending){for(const [name,value] of Object.entries(pending.fields))if(form.elements[name])form.elements[name].value=value;}
    if(selectedFile){form.elements.image.required=false;objectURL=URL.createObjectURL(selectedFile);$('#nad-image-preview').innerHTML=`<img src="${objectURL}" alt="Token image preview"><small>Change image</small>`;}
    const owner=S.boot.me?.id;
    const retain=()=>{if(owner===S.boot.me?.id){const fields=Object.fromEntries([...form.elements].filter(e=>e.name&&e.name!=='image').map(e=>[e.name,e.value]));S.nadLaunchInput={fields,file:selectedFile,key,media,actor:owner};}};
    S.modal.cleanup=()=>{retain();if(objectURL)URL.revokeObjectURL(objectURL);};
    form.addEventListener('input',()=>{key=crypto.randomUUID();form.elements.symbol.value=form.elements.symbol.value.toUpperCase();retain();});
    form.elements.image.onchange=e=>{const file=e.target.files[0];if(!file)return;if(!['image/png','image/jpeg','image/webp'].includes(file.type)||!file.size||file.size>5*1024*1024){notify('Choose a PNG, JPG or WebP under 5 MB');e.target.value='';return;}key=crypto.randomUUID();media=null;if(objectURL)URL.revokeObjectURL(objectURL);selectedFile=file;form.elements.image.required=false;objectURL=URL.createObjectURL(file);$('#nad-image-preview').innerHTML=`<img src="${objectURL}" alt="Token image preview"><small>Change image</small>`;};
    form.onsubmit=async e=>{
      e.preventDefault();if(form.dataset.pending==='true'||S.financialBusy||['unknown','submitted'].includes(form.dataset.orderState))return;if(!selectedFile){$('.r-form-error',form).textContent='Add a token image';return;}const fields=Object.fromEntries(new FormData(form));delete fields.image;form.dataset.pending='true';const button=$('[type=submit]',form),error=$('.r-form-error',form),controls=[...form.elements].filter(e=>e!==button),disabled=controls.map(e=>e.disabled);controls.forEach(e=>e.disabled=true);button.disabled=true;error.textContent='';
      try{
        S.nadLaunchInput={fields,file:selectedFile,key,media,actor:owner};
        if(!S.boot.me){await needAccount(launch);return;}
        if(!await walletReady())return;
        if(owner!==S.boot.me?.id)throw Error('Account changed. Open your draft again.');
        if(!form.isConnected){await launch();return;}
        if(!media){button.textContent='Uploading image…';media=(await api('/api/media',undefined,{method:'PUT',body:selectedFile,headers:{'Content-Type':selectedFile.type}})).id;S.nadLaunchInput.media=media;S.nadLaunchInput.actor=S.boot.me.id;}
        if(!form.isConnected||owner!==S.boot.me?.id)return;
        button.textContent='Preparing metadata…';const d=await api('/api/nadfun/draft',{...fields,media},{key});
        if(!form.isConnected||owner!==S.boot.me?.id)return;button.textContent='Preparing transaction…';
        const plan=await api('/api/execution/plan',{venue:'nadfun',kind:'create',draft:d.id});
        if(form.isConnected&&owner===S.boot.me?.id){await c.finance.review(plan);if(form.dataset.orderState==='submitted'&&owner===S.boot.me?.id)S.nadLaunchInput=null;}
      }catch(e){if(error.isConnected)error.textContent=e.message;}
      finally{form.dataset.pending='false';if(button.isConnected){controls.forEach((e,i)=>e.disabled=disabled[i]);const blocked=['unknown','submitted'].includes(form.dataset.orderState);button.disabled=blocked;button.textContent=form.dataset.orderState==='submitted'?'Submitted':'Launch token';}}
    };
    if(S.boot.wallet){api('/api/nadfun/drafts').then(d=>{if(form.isConnected&&d.drafts.length)form.querySelector('.ct-create-scroll').insertAdjacentHTML('beforeend',`<section class="nad-saved-drafts"><h3>Your drafts</h3>${d.drafts.map(x=>`<button type="button" class="r-person-row" data-action="nad-review-draft" data-id="${esc(x.id)}"><img class="r-token" src="${esc(x.imageURI)}" alt="${esc(x.symbol)}"><span><b>${esc(x.name)}</b><small>${esc(x.symbol)} · Prepared ${age(x.created)}</small></span>${icon('chevron')}</button>`).join('')}</section>`);}).catch(()=>{});}
  }
  async function poll(){
    if(document.hidden||S.modal||S.financialBusy||Date.now()-pollAt<20000)return;pollAt=Date.now();
    if(!S.nadOverlay&&(S.view==='explore'||S.view==='home'&&S.homeSection==='markets')&&S.marketTab==='memes'){
      const graduated=S.nadMode==='dex';
      try{const old=new Set((S[graduated?'nadGraduatedCatalog':'nadCatalog']?.tokens||[]).map(t=>t.id));const d=await catalog(graduated?'dex':'',(S.nadMode||'cap')==='cap'?'cap':'latest',true);for(const token of d.tokens){const cell=document.querySelector('[data-meme-token="'+token.id+'"]');if(cell)cell.innerHTML=metrics(token,true);}if(listState?.host.isConnected){const latest=new Map(d.tokens.map(t=>[t.id,t]));listState.tokens=listState.tokens.map(t=>latest.get(t.id)||t);}const count=d.tokens.filter(t=>!old.has(t.id)).length;if(count&&!$('#nad-new-launches'))$('.nad-list-head')?.insertAdjacentHTML('afterend',`<button class="r-new-posts" id="nad-new-launches" data-action="nad-refresh">${count} new ${graduated?'graduation'+(count===1?'':'s'):'launch'+(count===1?'':'es')} · Refresh</button>`);}catch{}return;
    }
    if(!S.nadDetail||!S.nadOverlay&&S.view!=='token')return;
    const panel=S.nadOverlay,id=panel?.id||S.nadToken;try{const t=await api('/api/nadfun/token?token='+encodeURIComponent(id));if(panel?S.nadOverlay!==panel:S.view!=='token'||S.nadToken!==id)return;
      const changed=S.nadDetail.phase!==t.phase||S.nadDetail.locked!==t.locked;remember(t);S.nadDetail=t;
      $('[data-meme-cap]',$('.nad-price')).textContent=cap(t);$('[data-meme-price]',$('.nad-price')).textContent='Price '+usd(t.price);
      $('#nad-phase').textContent=phase(t);$('#nad-phase').classList.toggle('good',t.graduated);$('#nad-market').textContent=phase(t);$('#nad-progress').style.width=Math.min(100,t.progressBps/100)+'%';$('#nad-progress-label').textContent=(t.progressBps/100).toFixed(1)+'%';
      if(changed){S.nadQuote=null;$('#nad-quote').innerHTML='';const b=$('#nad-order-form [type=submit]');b.disabled=t.locked||t.tradeSupported===false;b.textContent=t.locked?'Migrating':S.nadSide==='sell'?'Sell':'Buy';notify(t.graduated?'Graduated. DEX trading is ready.':'Token state changed. Get a fresh quote.');}
      if(chartSeries&&Date.now()-chartAt>90000){const seq=chartSequence;chartAt=Date.now();const d=await api('/api/nadfun/chart?token='+encodeURIComponent(id)+'&interval='+(S.nadInterval||'60'));if(seq===chartSequence&&chartSeries&&d.candles.length)chartSeries.setData(d.candles);}
    }catch{}}
  async function handle(action,id){
    if(!action.startsWith('nad-'))return false;
    if(action==='nad-token')await open(id);
    else if(action==='nad-close')closeOverlay();
    else if(action==='nad-back'){
      const back=S.nadReturn;S.nadReturn=null;
      if(back)history.back();
      else {S.marketTab='memes';await navigate('explore');}
    }
    else if(action==='nad-filter'){S.nadMode=id;const url=new URL(location.href);if(id==='dex')url.searchParams.set('phase','dex');else url.searchParams.delete('phase');if(id==='new')url.searchParams.set('sort','latest');else url.searchParams.delete('sort');history.replaceState({...history.state,ui:{...history.state?.ui,nadMode:id}},'',url);await list($('#market-list'),S.filter.toLowerCase());}
    else if(action==='nad-refresh')await list($('#market-list'),S.filter.toLowerCase(),true);
    else if(action==='nad-more')appendRows();
    else if(action==='nad-launch')await launch();
    else if(action==='nad-review-draft')await c.finance.review(await api('/api/execution/plan',{venue:'nadfun',kind:'create',draft:id}));
    else if(action==='nad-resume')await c.finance.review(await api('/api/execution/plan',S.financialPlan.args));
    else if(action==='nad-receive')modal('Receive MON',`<div class="r-summary"><span>Network</span><b>Monad</b><span>Your wallet</span><b>${esc(S.boot.wallet)}</b></div><button class="r-btn full" data-action="nad-copy" data-id="${esc(S.boot.wallet)}">Copy address</button><button class="r-btn primary full" data-action="nad-resume">Back to token</button>`);
    else if(action==='nad-side'){
      if(S.financialBusy||$('#nad-order-form')?.dataset.pending==='true')return true;
      if($('#nad-order-form')?.dataset.orderState==='unknown')return true;delete $('#nad-order-form').dataset.orderState;S.nadOrderVersion++;S.nadSide=id;S.nadQuote=null;$('#nad-input-unit').textContent=id==='buy'?(S.nadDetail.quoteSymbol||'MON'):S.nadDetail.symbol;$('#nad-order-form input[name=amount]').value='';$('#nad-quote').innerHTML='';$('#nad-order-form [type=submit]').textContent=(S.nadSide==='sell'?'Sell':'Buy');document.querySelectorAll('.nad-order [data-action=nad-side]').forEach(x=>{x.classList.toggle('selected',x.dataset.id===id);x.setAttribute('aria-pressed',String(x.dataset.id===id));});c.checkout.nadSide();
    }else if(action==='nad-copy'){await navigator.clipboard.writeText(id);notify('Contract address copied');}
    else if(action==='nad-share'){await navigator.clipboard.writeText(location.origin+'/?view=token&id='+encodeURIComponent(id));notify('Token link copied');}
    else if(action==='nad-post'){closeOverlay();S.composeAsset=id;c.composer();}
    else if(action==='nad-interval'||action==='nad-chart-retry'){
      if(action==='nad-interval')S.nadInterval=id;dispose();document.querySelectorAll('[data-action=nad-interval]').forEach(b=>b.classList.toggle('selected',b.dataset.id===(S.nadInterval||'60')));$('#nad-chart').innerHTML=loading();
      try{await mount(S.nadDetail);}catch(e){if($('#nad-chart'))$('#nad-chart').innerHTML=`<div class="nad-chart-empty">${esc(e.message)}</div>`;}
    }
    return true;
  }
  return {catalog,list,open,detail,launch,handle,dispose,closeOverlay,poll,metrics};
}
