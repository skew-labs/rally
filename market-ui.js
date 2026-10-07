let renderer;
const library=()=>renderer ||= import('https://cdn.jsdelivr.net/npm/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.mjs').catch(e=>{renderer=null;throw e;});

export function marketUI(c){
  const {S,$,api,esc,usd,priceHTML,volumeHTML,age,logo,token,modal,trade,finance}=c;
  let reading,refreshing=false;
  const charts=new Map();
  async function readChart(query,signal){
    const key=query.toString()+'|'+(query.get('kind')==='spot'?token(query.get('asset'))?.pair||'':''),hit=charts.get(key);
    if(hit&&Date.now()/1000-hit.fetchedAt<120&&!hit.stale)return hit;
    const data=await api('/api/market-chart?'+query,undefined,{signal});
    if(!signal.aborted&&!data.stale){charts.delete(key);charts.set(key,data);while(charts.size>12)charts.delete(charts.keys().next().value);}
    return data;
  }
  document.addEventListener('pointerover',e=>{if(e.target.closest('[data-action="market-detail"],[data-action="perp-detail"],[data-action="prediction-detail"]'))library().catch(()=>{});},{passive:true});
  function details(id,kind='spot'){
    const pool=kind==='prediction'?S.predictions?.pools.find(p=>String(p.id)===String(id)):null;
    const perp=kind==='perps'?S.perps?.markets.find(m=>String(m.id)===String(id)):null;
    const asset=pool?.assetInfo||(perp?finance.perplAsset(perp):token(id));
    if(!asset)return;
    modal(esc(asset.symbol),`<div class="r-asset-body"><div class="r-asset-summary">${logo(asset)}<div><b>${esc(asset.name||asset.symbol)}</b><small>${pool?'Castora · Price prediction':kind==='perps'?esc(perp.venue)+' · Perpetual':'Monad · Spot'}</small></div></div><div class="r-asset-price"><strong>${pool&&pool.state!=='settled'?esc(pool.stake+' '+pool.stakeAsset):usd(pool?.settlementPrice??perp?.mark??asset.price)}</strong><span>${pool?(pool.state==='settled'?'Settled pool price':'Entry stake'):kind==='perps'?esc((perp.stale?'Last known · ':'')+(perp.priceSource||'Venue price')):asset.stale?'Stale pool price':'Pool price'}</span></div><div class="r-mini-periods" role="group" aria-label="Chart period">${['1D','7D','1M'].map(p=>`<button data-mini-period="${p}" aria-pressed="${p==='1D'}">${p}</button>`).join('')}</div><div class="r-mini-chart" aria-label="${esc(asset.symbol)} price chart"><div class="r-chart-loading" role="status">Loading chart…</div></div><div class="r-mini-caption" role="status"></div><div class="r-asset-facts"><span>${pool?'Entry stake':kind==='perps'?'Last trade':'24h volume'}</span><b>${pool?esc(pool.stake+' '+pool.stakeAsset):kind==='perps'?usd(perp.last):asset.volume==null?'—':usd(asset.volume)}</b>${asset.liquidity!=null?`<span>Pool liquidity</span><b>${usd(asset.liquidity)}</b>`:''}<span>Updated</span><b>${age(pool?S.predictions.fetchedAt:kind==='perps'?perp.observationAt:asset.fetchedAt||S.marketData?.fetchedAt||0)}</b></div></div><div class="r-asset-actions">${perp&&perp.execution!=='wallet_transactions'?`<span class="r-note">${perp.executionBlocker||'Order adapter under verification.'}</span>${perp.orderAdapter?`<button class="r-btn subtle" data-action="venue-order" data-id="${esc(perp.id)}">Order details</button>`:""}<a class="r-btn subtle" href="${esc(perp.sourceURL)}" target="_blank" rel="noopener noreferrer">Open ${esc(perp.venue)}</a>`:pool?`<button class="r-btn primary" style="grid-column:1/-1" data-mini-trade="buy" ${pool.state==='open'?'':'disabled'}>${pool.state==='open'?'Predict price':pool.state==='settled'?'Settled':'Awaiting settlement'}</button>`:`<button class="r-btn primary" data-mini-trade="buy" ${perp&&!perp.open?'disabled':''}>${kind==='perps'?'Buy / Long':'Buy'}</button><button class="r-btn" data-mini-trade="sell" ${perp&&!perp.open?'disabled':''}>${kind==='perps'?'Sell / Short':'Sell'}</button>`}</div>`, 'r-asset-modal');
    const instance=S.modal,host=$('.r-mini-chart'),caption=$('.r-mini-caption');
    const state=reading={instance,host,chart:null,controller:null,sequence:0,resize:null,theme:null};
    instance.cleanup=()=>{state.sequence++;state.controller?.abort();state.resize?.disconnect();state.theme?.disconnect();state.chart?.remove();if(reading===state)reading=null;};
    const theme=()=>{const dark=document.documentElement.dataset.theme==='dark';return {background:{type:'solid',color:dark?'#19191f':'#ffffff'},textColor:dark?'#a3a3b0':'#797980'};};
    async function load(period){
      const sequence=++state.sequence;state.controller?.abort();state.controller=new AbortController();
      caption.textContent='Loading '+period+'…';host.setAttribute('aria-busy','true');
      document.querySelectorAll('[data-mini-period]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.miniPeriod===period)));
      try{
        const [data,L]=await Promise.all([readChart(new URLSearchParams({asset:pool?String(asset.chartMarket):id,kind:pool?'perps':kind,period}),state.controller.signal),library()]);
        if(sequence!==state.sequence||S.modal!==instance||!host.isConnected)return;
        state.resize?.disconnect();state.theme?.disconnect();state.chart?.remove();host.replaceChildren();
        const chart=state.chart=L.createChart(host,{width:host.clientWidth,height:host.clientHeight,layout:{...theme(),fontFamily:'-apple-system,BlinkMacSystemFont,Inter,sans-serif',attributionLogo:true},grid:{vertLines:{visible:false},horzLines:{visible:false}},rightPriceScale:{visible:false},timeScale:{borderVisible:false,timeVisible:period==='1D',secondsVisible:false},crosshair:{mode:L.CrosshairMode.Normal,vertLine:{color:'#aaa',labelVisible:false},horzLine:{visible:false}},handleScroll:{mouseWheel:false,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},handleScale:{mouseWheel:false,pinch:true,axisPressedMouseMove:false}});
        const line=chart.addSeries(L.AreaSeries,{lineColor:'#9178ff',topColor:'rgba(145,120,255,.18)',bottomColor:'rgba(145,120,255,0)',lineWidth:2,priceLineVisible:false,lastValueVisible:false});line.setData(data.points);chart.timeScale().fitContent();
        const label=()=>`${data.stale?'Stale · ':''}${new Date(data.lastObservation*1000).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}`;
        caption.innerHTML=`<span>${esc(data.reference)}</span><span data-chart-observation>${esc(label())}</span><a href="${esc(data.sourceURL)}" target="_blank" rel="noopener noreferrer">${esc(data.source)}</a>`;
        chart.subscribeCrosshairMove(p=>{const v=p.seriesData.get(line);if(v&&p.time)caption.querySelector('[data-chart-observation]').textContent=usd(v.value)+' · '+new Date(Number(p.time)*1000).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});else caption.querySelector('[data-chart-observation]').textContent=label();});
        state.resize=new ResizeObserver(()=>{if(host.isConnected)chart.applyOptions({width:host.clientWidth,height:host.clientHeight});});state.resize.observe(host);
        state.theme=new MutationObserver(()=>chart.applyOptions({layout:theme()}));state.theme.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
      }catch(e){if(sequence!==state.sequence||e.name==='AbortError'||!host.isConnected)return;state.resize?.disconnect();state.theme?.disconnect();state.chart?.remove();state.chart=null;host.innerHTML='<div class="r-chart-loading">'+esc(e.message)+'</div>';caption.innerHTML='<button class="r-text-button" data-mini-retry>Retry chart</button>';}
      finally{if(sequence===state.sequence&&host.isConnected)host.removeAttribute('aria-busy');}
    }
    $('.r-asset-modal').onclick=e=>{
      const b=e.target.closest('[data-mini-period],[data-mini-trade],[data-mini-retry]');if(!b)return;
      if(b.hasAttribute('data-mini-period'))load(b.dataset.miniPeriod);
      else if(b.hasAttribute('data-mini-retry'))load($('.r-mini-periods [aria-pressed=true]').dataset.miniPeriod);
      else if(pool)finance.handle('predict',id);
      else if(kind==='perps')finance.handle(b.dataset.miniTrade==='sell'?'perpl-short':'perpl-order',id);
      else trade(id,null,b.dataset.miniTrade);
    };
    load('1D');
  }
  function patchSpot(){
    const rows=document.querySelectorAll('[data-spot-market]');
    for(const row of rows){const asset=token(row.dataset.spotMarket);if(!asset)continue;const cells=row.querySelectorAll('td'),elapsed=Date.now()/1000-(asset.fetchedAt||0),price=elapsed<=900?asset.price:null,stale=asset.stale||elapsed>120;cells[2].innerHTML=priceHTML(price)+(stale&&price?'<small>Last '+esc(age(asset.fetchedAt))+'</small>':'');cells[3].textContent=asset.change==null?'—':(asset.change>=0?'+':'')+Number(asset.change).toFixed(2)+'%';cells[3].classList.toggle('positive',(asset.change||0)>=0);cells[3].classList.toggle('negative',asset.change<0);cells[4].innerHTML=volumeHTML(asset.volume);}
    const updated=$('[data-market-updated]');if(updated)updated.textContent=(S.marketData?.error?'Prices delayed · ':'')+'Updated '+age(S.marketData?.fetchedAt||0);
  }
  async function poll(){
    if(document.hidden||refreshing||!(S.view==='explore'||S.view==='home'&&S.homeSection==='markets'))return;
    refreshing=true;
    try{
      if(S.marketTab==='perps')await finance.refreshPerps();
      else if(['spot','rwa'].includes(S.marketTab)){
        const rows=[...document.querySelectorAll('[data-spot-market]')].slice(0,60),ids=rows.map(r=>r.dataset.spotMarket),tab=S.marketTab;
        if(ids.length){const data=await api('/api/market-prices?'+new URLSearchParams({assets:ids.join(',')}));if(!(S.view==='explore'||S.view==='home'&&S.homeSection==='markets')||S.marketTab!==tab||rows.some(r=>!r.isConnected))return;const merged=new Map(S.tokens.map(t=>[t.id,t]));data.tokens.forEach(t=>{const old=merged.get(t.id);if((t.fetchedAt||0)>=(old?.fetchedAt||0))merged.set(t.id,{...old,...t});});S.tokens=[...merged.values()];patchSpot();}
      }else if(S.marketTab==='prediction'&&(!S.predictions||Date.now()/1000-S.predictions.fetchedAt>=120))await finance.predictions($('#market-list'),S.filter.toLowerCase());
    }catch{patchSpot();const u=$('[data-perpl-updated]');if(u)u.textContent='Price update delayed · Last '+age(S.perps?.priceUpdatedAt||0);}finally{refreshing=false;}
  }
  setInterval(poll,15000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
  return {details,patchSpot,handle(action,id){if(action==='prediction-detail'){details(id,'prediction');return true;}if(action==='market-detail'){details(id);return true;}if(action==='perp-detail'){details(id,'perps');return true;}return false;}};
}
