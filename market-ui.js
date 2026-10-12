import {mountHolders,warmHolders} from './holder-ui.js';
import {priceLineOptions,fitPriceLine} from './price-line.js';
import {providerTarget,mountProviderChart,preconnectProvider} from './provider-chart.js';
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
    const instance=S.modal,host=$('.r-mini-chart'),caption=$('.r-mini-caption'),target=providerTarget(asset,kind==='prediction'?'perps':kind);let providerCleanup,useLine=false;
    const state=reading={instance,host,chart:null,controller:null,sequence:0,resize:null,theme:null,line:null,data:null,period:null};
    instance.cleanup=()=>{state.sequence++;providerCleanup?.();state.controller?.abort();state.resize?.disconnect();state.theme?.disconnect();state.chart?.remove();if(reading===state)reading=null;};
    let selectedPeriod='1D',selectedInterval='1';
    const controls=$('.r-mini-periods');
    function periods(){controls.hidden=target?.kind==='coin'&&!useLine;const embedded=target?.kind==='pool'&&!useLine;controls.setAttribute('aria-label',embedded?'Candle interval':'Chart period');controls.innerHTML=(embedded?['1m','15m','1h','4h']:['1D','7D','1M']).map((p,i)=>`<button ${embedded?'data-mini-interval='+['1','15','60','240'][i]:'data-mini-period='+p} aria-pressed="${embedded?selectedInterval===['1','15','60','240'][i]:selectedPeriod===p}">${p}</button>`).join('');}
    const theme=()=>{const dark=document.documentElement.dataset.theme==='dark';return {background:{type:'solid',color:dark?'#19191f':'#ffffff'},textColor:dark?'#a3a3b0':'#797980'};};
    async function load(period){
      selectedPeriod=period;periods();
      const sequence=++state.sequence;state.controller?.abort();state.controller=new AbortController();
      document.querySelectorAll('[data-mini-period]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.miniPeriod===period)));
      providerCleanup?.();providerCleanup=null;
      if(target&&!useLine){
        host.style.height=target.kind==='coin'?'360px':'320px';caption.innerHTML='<span>CoinGecko · '+(target.kind==='pool'?'Monad token':'Spot reference')+'</span><button class="r-text-button" data-mini-line>Price line</button>';
        providerCleanup=mountProviderChart(host,target,{dark:document.documentElement.dataset.theme==='dark',interval:selectedInterval,onFailure:()=>{if(sequence===state.sequence&&host.isConnected){useLine=true;load(period);}}});return;
      }
      caption.textContent='Loading '+period+'…';host.setAttribute('aria-busy','true');
      document.querySelectorAll('[data-mini-period]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.miniPeriod===period)));
      try{
        const query=new URLSearchParams({asset:pool?String(asset.chartMarket):id,kind:pool?'perps':kind,period});
        const [data,L]=await Promise.all([api('/api/market-chart?'+query+'&fresh=1',undefined,{signal:state.controller.signal}),library()]);
        if(sequence!==state.sequence||S.modal!==instance||!host.isConnected)return;
        if(!Array.isArray(data.points)||!data.points.length||String(data.asset)!==String(query.get('asset'))||data.period&&data.period!==period)throw Error('Invalid chart identity');
        host.style.height='200px';
        if(!state.chart){
          host.replaceChildren();
          const chart=state.chart=L.createChart(host,{width:host.clientWidth,height:host.clientHeight,layout:{...theme(),fontFamily:'-apple-system,BlinkMacSystemFont,Inter,sans-serif',attributionLogo:true},grid:{vertLines:{visible:false},horzLines:{visible:false}},rightPriceScale:{visible:false},timeScale:{borderVisible:false,timeVisible:period==='1D',secondsVisible:false},localization:{locale:'en-US'},crosshair:{mode:L.CrosshairMode.Normal,vertLine:{color:'#aaa',labelVisible:false},horzLine:{visible:false}},handleScroll:{mouseWheel:false,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},handleScale:{mouseWheel:false,pinch:true,axisPressedMouseMove:false}});
          state.line=chart.addSeries(L.LineSeries,{...priceLineOptions(),pointMarkersRadius:3,lastValueVisible:false});
          chart.subscribeCrosshairMove(p=>{const node=caption.querySelector('[data-chart-observation]'),v=p.seriesData.get(state.line);if(node)node.textContent=v&&p.time?usd(v.value)+' · '+observation(Number(p.time)):label();});
          state.resize=new ResizeObserver(()=>{if(host.isConnected)chart.applyOptions({width:host.clientWidth,height:host.clientHeight});});state.resize.observe(host);
          state.theme=new MutationObserver(()=>chart.applyOptions({layout:theme()}));state.theme.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
        }
        state.data=data;state.line.applyOptions({pointMarkersVisible:data.points.length===1});state.line.setData(data.points);
        state.chart.applyOptions({timeScale:{timeVisible:period==='1D'}});fitPriceLine(state.chart,data.points);state.period=period;
        host.dataset.series='line';host.dataset.points=String(data.points.length);
        function observation(t){return new Date(t*1000).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});}
        function label(){return `${state.data.stale?'Stale · ':''}${observation(state.data.lastObservation)}`;}
        caption.innerHTML=`<span>${esc(data.reference)}</span><span data-chart-observation>${esc(label())}</span><a href="${esc(data.sourceURL)}" target="_blank" rel="noopener noreferrer">${esc(data.source)}</a>`;
      }catch(e){if(sequence!==state.sequence||e.name==='AbortError'||!host.isConnected)return;state.resize?.disconnect();state.theme?.disconnect();state.chart?.remove();state.chart=null;state.line=null;host.innerHTML='<div class="r-chart-loading">Chart temporarily unavailable</div>';caption.innerHTML='<button class="r-text-button" data-mini-retry>Retry chart</button>';}
      finally{if(sequence===state.sequence&&host.isConnected)host.removeAttribute('aria-busy');}
    }
    $('.r-asset-modal').onclick=e=>{
      const b=e.target.closest('[data-mini-interval],[data-mini-period],[data-mini-trade],[data-mini-retry],[data-mini-line]');if(!b)return;
      if(b.hasAttribute('data-mini-line')){useLine=true;load(selectedPeriod);}
      else if(b.hasAttribute('data-mini-interval')){if(b.dataset.miniInterval!==selectedInterval){selectedInterval=b.dataset.miniInterval;load(selectedPeriod);}}
      else if(b.hasAttribute('data-mini-period'))load(b.dataset.miniPeriod);
      else if(b.hasAttribute('data-mini-retry'))load(selectedPeriod);
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
      }else if(S.marketTab==='prediction')await finance.refreshPredictions();
    }catch{patchSpot();const u=$('[data-perpl-updated]');if(u)u.textContent='Price update delayed · Last '+age(S.perps?.priceUpdatedAt||0);}finally{refreshing=false;}
  }
  setInterval(poll,15000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
  return {details,patchSpot,handle(action,id){if(action==='prediction-detail'){details(id,'prediction');return true;}if(action==='market-detail'){details(id);return true;}if(action==='perp-detail'){details(id,'perps');return true;}return false;}};
}
