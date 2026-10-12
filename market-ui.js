import {mountHolders,warmHolders} from './holder-ui.js';
import {priceLineOptions,fitPriceLine} from './price-line.js';
import {providerTarget,mountProviderChart,preconnectProvider} from './provider-chart.js';
import {streamPrices} from './live-price.js';
let renderer;
const library=()=>renderer ||= import(location.origin+'/assets/lightweight-charts-5.2.1.mjs').catch(e=>{renderer=null;throw e;});

export function marketUI(c){
  const {S,$,api,esc,usd,priceHTML,volumeHTML,age,logo,token,modal,trade,finance}=c;
  let reading,refreshing=false;
  const intent=e=>{const el=e.target.closest('[data-action="market-detail"],[data-action="perp-detail"],[data-action="prediction-detail"]');if(!el)return;const a=el.dataset.action==='market-detail'&&token(el.dataset.id);if(!a||!providerTarget(a))library().catch(()=>{});if(a)warmHolders({api},a.address||a.id).catch(()=>{});};
  document.addEventListener('pointerover',intent,{passive:true});document.addEventListener('touchstart',intent,{passive:true});
  function details(id,kind='spot'){
    const pool=kind==='prediction'?S.predictions?.pools.find(p=>String(p.id)===String(id)):null;
    const perp=kind==='perps'?S.perps?.markets.find(m=>String(m.id)===String(id)):null;
    const asset=pool?.assetInfo||(perp?finance.perplAsset(perp):token(id));
    if(!asset)return;
    const reference=pool&&S.perps?.markets.find(m=>m.venue==='Perpl'&&String(m.id)===String(pool.assetInfo?.chartMarket));
    const referenceFresh=reference&&!reference.stale&&reference.mark>0&&Date.now()/1000-reference.observationAt<=60;
    const poolPrice=pool?.state==='settled'?pool.settlementPrice:referenceFresh?reference.mark:null;
    modal(esc(asset.symbol),`<div class="r-asset-body"><div class="r-asset-summary">${logo(asset)}<div><b>${esc(asset.name||asset.symbol)}</b><small>${pool?'Castora · Price prediction':kind==='perps'?esc(perp.venue)+' · Perpetual':'Monad · Spot'}</small></div></div><div class="r-asset-price"><strong>${usd(pool?poolPrice:perp?.mark??asset.price)}</strong><span>${pool?(pool.state==='settled'?'Resolved pool price':'Perpl mark · Reference price'):kind==='perps'?esc((perp.stale?'Last known · ':'')+(perp.priceSource||'Venue price')):asset.stale?'Stale pool price':'Pool price'}</span></div><div class="r-mini-periods" role="group" aria-label="Chart period">${['1D','7D','1M'].map(p=>`<button data-mini-period="${p}" aria-pressed="${p==='1D'}">${p}</button>`).join('')}</div><div class="r-mini-chart" aria-label="${esc(asset.symbol)} price chart"><div class="r-chart-loading" role="status">Loading chart…</div></div><div class="r-mini-caption" role="status"></div>${kind==='spot'?'<section id="market-holders" class="r-holders"></section>':''}<div class="r-asset-facts"><span>${pool?'Entry stake':kind==='perps'?'Last trade':'24h volume'}</span><b>${pool?esc(pool.stake+' '+pool.stakeAsset):kind==='perps'?usd(perp.last):asset.volume==null?'—':usd(asset.volume)}</b>${asset.liquidity!=null?`<span>Pool liquidity</span><b>${usd(asset.liquidity)}</b>`:''}<span>Updated</span><b>${age(pool?(pool.state==='settled'?pool.completedAt:reference?.observationAt||0):kind==='perps'?perp.observationAt:asset.fetchedAt||S.marketData?.fetchedAt||0)}</b></div></div><div class="r-asset-actions">${perp&&perp.execution!=='wallet_transactions'?`<span class="r-note">${perp.executionBlocker||'Order adapter under verification.'}</span>${perp.orderAdapter?`<button class="r-btn subtle" data-action="venue-order" data-id="${esc(perp.id)}">Order details</button>`:""}<a class="r-btn subtle" href="${esc(perp.sourceURL)}" target="_blank" rel="noopener noreferrer">Open ${esc(perp.venue)}</a>`:pool?`<button class="r-btn primary" style="grid-column:1/-1" data-mini-trade="buy" ${pool.state==='open'?'':'disabled'}>${pool.state==='open'?'Predict price':pool.state==='settled'?'Settled':'Awaiting settlement'}</button>`:`<button class="r-btn primary" data-mini-trade="buy" ${perp&&!perp.open?'disabled':''}>${kind==='perps'?'Buy / Long':'Buy'}</button><button class="r-btn" data-mini-trade="sell" ${perp&&!perp.open?'disabled':''}>${kind==='perps'?'Sell / Short':'Sell'}</button>`}</div>`, 'r-asset-modal');
    if(kind==='spot')mountHolders({api,esc,age},$('#market-holders'),asset.address||asset.id);
    const instance=S.modal,host=$('.r-mini-chart'),caption=$('.r-mini-caption'),target=providerTarget(asset,kind==='prediction'?'perps':kind);let providerCleanup,useLine=false,live,chartMode='history',hourlyTimer;
    const state=reading={instance,host,chart:null,controller:null,sequence:0,resize:null,theme:null,line:null,data:null,period:null};
    instance.cleanup=()=>{state.sequence++;clearTimeout(hourlyTimer);document.removeEventListener('visibilitychange',resumeHourly);live?.dispose();providerCleanup?.();state.controller?.abort();state.resize?.disconnect();state.theme?.disconnect();state.chart?.remove();if(reading===state)reading=null;};
    let selectedPeriod='1D',selectedInterval='1';
    const controls=$('.r-mini-periods');
    function periods(){
      controls.hidden=false;const embedded=target?.kind==='pool'&&!useLine;controls.setAttribute('aria-label','Chart view');
      const modes=`<div class="r-mini-mode-tabs"><button data-mini-candles aria-label="1 hour candles" aria-pressed="${chartMode==='candles'}">1h</button><button data-mini-live="line" aria-pressed="${chartMode==='line'}">Live</button><button data-mini-live="ticks" aria-pressed="${chartMode==='ticks'}">Ticks</button><button data-mini-history aria-pressed="${chartMode==='history'}">History</button></div>`;
      const ranges=chartMode==='candles'?['1D','7D','1M'].map(p=>`<button data-mini-range="${p}" aria-pressed="${selectedPeriod===p}">${p}</button>`).join(''):chartMode==='history'&&!(target?.kind==='coin'&&!useLine)?(embedded?['1m','15m','1h','4h']:['1D','7D','1M']).map((p,i)=>`<button ${embedded?'data-mini-interval='+['1','15','60','240'][i]:'data-mini-period='+p} aria-pressed="${embedded?selectedInterval===['1','15','60','240'][i]:selectedPeriod===p}">${p}</button>`).join(''):'';
      controls.innerHTML=modes+(ranges?'<div class="r-mini-range-tabs">'+ranges+'</div>':'');
    }
    const theme=()=>{const dark=document.documentElement.dataset.theme==='dark';return {background:{type:'solid',color:dark?'#19191f':'#ffffff'},textColor:dark?'#a3a3b0':'#797980'};};
    function resumeHourly(){if(chartMode!=='candles')return;if(document.hidden){clearTimeout(hourlyTimer);state.controller?.abort();}else if(chartMode==='candles'&&S.modal===instance)load(selectedPeriod,true,true);}
    document.addEventListener('visibilitychange',resumeHourly);
    async function load(period,candles=false,refresh=false){
      clearTimeout(hourlyTimer);live?.dispose();live=null;chartMode=candles?'candles':'history';selectedPeriod=period;periods();
      const sequence=++state.sequence;state.controller?.abort();state.controller=new AbortController();
      document.querySelectorAll('[data-mini-period]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.miniPeriod===period)));
      providerCleanup?.();providerCleanup=null;
      if(target&&!useLine&&!candles){
        state.resize?.disconnect();state.theme?.disconnect();state.chart?.remove();state.chart=null;state.line=null;
        host.style.height=target.kind==='coin'?'360px':'320px';caption.innerHTML='<span>CoinGecko · '+(target.kind==='pool'?'Monad token':'Spot reference')+'</span><button class="r-text-button" data-mini-line>Price line</button>';
        providerCleanup=mountProviderChart(host,target,{dark:document.documentElement.dataset.theme==='dark',interval:selectedInterval,onFailure:()=>{if(sequence===state.sequence&&host.isConnected){useLine=true;load(period);}}});return;
      }
      if(!refresh)caption.textContent='Loading '+(candles?'1h candles':period)+'…';host.setAttribute('aria-busy','true');
      document.querySelectorAll('[data-mini-period]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.miniPeriod===period)));
      try{
        const query=new URLSearchParams({asset:pool?String(asset.chartMarket):id,kind:pool?'perps':kind,period});
        if(candles)query.set('interval','1h');
        const [data,L]=await Promise.all([api('/api/market-chart?'+query+'&fresh=1',undefined,{signal:state.controller.signal}),library()]);
        if(sequence!==state.sequence||S.modal!==instance||!host.isConnected)return;
        const values=candles?data.candles:data.points;
        if(!Array.isArray(values)||!values.length||String(data.asset)!==String(query.get('asset'))||data.period&&data.period!==period||candles&&data.interval!=='1h')throw Error('Invalid chart identity');
        host.style.height=candles?'260px':'200px';
        if(!state.chart){
          host.replaceChildren();
          const chart=state.chart=L.createChart(host,{width:host.clientWidth,height:host.clientHeight,layout:{...theme(),fontFamily:'-apple-system,BlinkMacSystemFont,Inter,sans-serif',attributionLogo:true},grid:{vertLines:{visible:false},horzLines:{visible:false}},rightPriceScale:{visible:false},timeScale:{borderVisible:false,timeVisible:period==='1D',secondsVisible:false},localization:{locale:'en-US'},crosshair:{mode:L.CrosshairMode.Normal,vertLine:{color:'#aaa',labelVisible:false},horzLine:{visible:false}},handleScroll:{mouseWheel:false,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},handleScale:{mouseWheel:false,pinch:true,axisPressedMouseMove:false}});
          chart.subscribeCrosshairMove(p=>{const node=caption.querySelector('[data-chart-observation]'),v=p.seriesData.get(state.line);if(node)node.textContent=v&&p.time?(v.open!=null?`O ${usd(v.open)}  H ${usd(v.high)}  L ${usd(v.low)}  C ${usd(v.close)}`:usd(v.value))+' · '+observation(Number(p.time)):label();});
          state.resize=new ResizeObserver(()=>{if(host.isConnected)chart.applyOptions({width:host.clientWidth,height:host.clientHeight});});state.resize.observe(host);
          state.theme=new MutationObserver(()=>chart.applyOptions({layout:theme()}));state.theme.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
        }
        const type=candles?'candles':'line';
        if(!state.line||state.seriesType!==type){
          if(state.line)state.chart.removeSeries(state.line);
          state.line=state.chart.addSeries(candles?L.CandlestickSeries:L.LineSeries,candles?{upColor:'#3478f6',downColor:'#e35d73',wickUpColor:'#3478f6',wickDownColor:'#e35d73',borderVisible:false,priceLineVisible:false,priceFormat:priceLineOptions(values.at(-1).close<.0001?9:values.at(-1).close<1?6:2).priceFormat}:{...priceLineOptions(),pointMarkersRadius:3,lastValueVisible:false});
          state.seriesType=type;state.values=null;
        }
        const previous=state.values,incremental=refresh&&candles&&previous?.length&&values[0].time===previous[0].time&&values.length>=previous.length&&previous.every((p,i)=>p.time===values[i].time);
        if(incremental){for(let i=0;i<values.length;i++){const a=previous[i],b=values[i];if(!a||a.time!==b.time||a.open!==b.open||a.high!==b.high||a.low!==b.low||a.close!==b.close)state.line.update(b,i<previous.length-1);}}
        else state.line.setData(values);
        state.data=data;state.values=values;
        if(!candles)state.line.applyOptions({pointMarkersVisible:values.length===1});
        state.chart.applyOptions({width:host.clientWidth,height:host.clientHeight,rightPriceScale:{visible:candles,borderVisible:false},timeScale:{timeVisible:period==='1D'||candles}});
        if(!refresh){if(candles)state.chart.timeScale().setVisibleLogicalRange({from:Math.max(-1,values.length-48),to:values.length+1});else fitPriceLine(state.chart,values);}
        state.period=period;host.dataset.series=type;host.dataset.points=String(values.length);
        function observation(t){return new Date(t*1000).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});}
        function label(){return state.data?`${state.data.interval==='1h'?'1h · ':''}${state.data.stale?'Last known · ':''}${observation(state.data.lastObservation)}`:'';}
        caption.innerHTML=`<span>${esc(data.reference)}</span><span data-chart-observation>${esc(label())}</span><a href="${esc(data.sourceURL)}" target="_blank" rel="noopener noreferrer">${esc(data.source)}</a>`;
      }catch(e){if(sequence!==state.sequence||e.name==='AbortError'||!host.isConnected)return;if(!refresh){state.resize?.disconnect();state.theme?.disconnect();state.chart?.remove();state.chart=null;state.line=null;host.innerHTML='<div class="r-chart-loading">Chart temporarily unavailable</div>';}caption.innerHTML=(refresh?'<span>Update delayed · Last known candles</span>':'')+'<button class="r-text-button" data-mini-retry>Retry chart</button>';}
      finally{if(sequence===state.sequence&&host.isConnected){host.removeAttribute('aria-busy');if(candles&&!document.hidden)hourlyTimer=setTimeout(()=>load(period,true,true),30000);}}
    }
    function showLive(mode){
      clearTimeout(hourlyTimer);
      if(live){chartMode=mode;live.setMode(mode);periods();return;}
      chartMode=mode;periods();state.sequence++;state.controller?.abort();providerCleanup?.();providerCleanup=null;state.resize?.disconnect();state.theme?.disconnect();state.chart?.remove();state.chart=null;state.line=null;
      host.style.height='200px';host.removeAttribute('aria-busy');caption.textContent='Waiting for price updates…';
      let latest;
      live=streamPrices({host,api,asset:pool?String(asset.chartMarket):id,kind:pool?'perps':kind,mode,onStatus:({data,point,error})=>{
        if(!host.isConnected)return;if(data)latest=data;
        if(point&&!pool){const price=host.closest('.r-asset-modal').querySelector('.r-asset-price');price.querySelector('strong').textContent=usd(point.value);price.querySelector('span').textContent=(latest?.stale?'Last known · ':'')+(latest?.source||'Price update');}
        const stamp=point?new Date(point.time*1000).toLocaleTimeString('en-US',{hour12:false}):'';
        caption.textContent=error?'Price updates delayed':`${latest?.source||'Price updates'}${latest?.stale?' · Last known':''}${point?' · '+usd(point.value)+' · '+stamp:' · Waiting for data'}`;
      }});
    }
    $('.r-asset-modal').onclick=e=>{
      const b=e.target.closest('[data-mini-candles],[data-mini-range],[data-mini-history],[data-mini-live],[data-mini-interval],[data-mini-period],[data-mini-trade],[data-mini-retry],[data-mini-line]');if(!b)return;
      if(b.hasAttribute('data-mini-candles'))load(selectedPeriod,true);
      else if(b.hasAttribute('data-mini-range'))load(b.dataset.miniRange,true);
      else if(b.hasAttribute('data-mini-history'))load(selectedPeriod);
      else if(b.hasAttribute('data-mini-live'))showLive(b.dataset.miniLive);
      else if(b.hasAttribute('data-mini-line')){useLine=true;load(selectedPeriod);}
      else if(b.hasAttribute('data-mini-interval')){if(b.dataset.miniInterval!==selectedInterval){selectedInterval=b.dataset.miniInterval;load(selectedPeriod);}}
      else if(b.hasAttribute('data-mini-period'))load(b.dataset.miniPeriod);
      else if(b.hasAttribute('data-mini-retry'))load(selectedPeriod,chartMode==='candles');
      else if(pool)finance.handle('predict',id);
      else if(kind==='perps')finance.handle(b.dataset.miniTrade==='sell'?'perpl-short':'perpl-order',id);
      else trade(id,null,b.dataset.miniTrade);
    };
    load('1D',kind==='perps');
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
      }else if(S.marketTab==='prediction')await finance.refreshPredictions();
    }catch{patchSpot();const u=$('[data-perpl-updated]');if(u)u.textContent='Price update delayed · Last '+age(S.perps?.priceUpdatedAt||0);}finally{refreshing=false;}
  }
  setInterval(poll,15000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
  return {details,patchSpot,handle(action,id){if(action==='prediction-detail'){details(id,'prediction');return true;}if(action==='market-detail'){details(id);return true;}if(action==='perp-detail'){details(id,'perps');return true;}return false;}};
}
