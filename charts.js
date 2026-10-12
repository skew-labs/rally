import {closingPrices,priceLineOptions,fitPriceLine} from './price-line.js';
import {providerTarget,mountProviderChart} from './provider-chart.js';
export const money = (n, digits) => '$' + n.toLocaleString('en-US',{minimumFractionDigits:digits ?? (n < .0001 ? 9 : n < 1 ? 5 : 2),maximumFractionDigits:digits ?? (n < .0001 ? 9 : n < 1 ? 5 : 2)});
export const compact = n => '$' + (n >= 1e12 ? (n/1e12).toFixed(2)+'T' : n >= 1e9 ? (n/1e9).toFixed(2)+'B' : n >= 1e6 ? (n/1e6).toFixed(1)+'M' : (n/1e3).toFixed(1)+'K');
export const changeText = n => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
export const changeClass = n => n >= 0 ? 'positive' : 'negative';

// Exact token identities; tokenized equities never use the underlying stock feed.
const sources = {
  MON: ['monad',38927],
  BTC: ['bitcoin',1],
  ETH: ['ethereum',279],
  SOL: ['solana',4128],
  HYPE: ['hyperliquid',50882],
  PENGU: ['pudgy-penguins',52622],
  LINK: ['chainlink',877],
  ONDO: ['ondo-finance',26580],
  AAVE: ['aave',12645],
  PEPE: ['pepe',29850],
  UNI: ['uniswap',12504],
  USDC: ['usd-coin',6319],
  NVDAon: ['nvidia-ondo-tokenized-stock',68623],
  TSLAon: ['tesla-ondo-tokenized-stock',68628],
  AAPLon: ['apple-ondo-tokenized-stock',68616],
  SPYon: ['spdr-s-p-500-etf-ondo-tokenized-etf',68655],
  PAXG: ['pax-gold',9519]
};
const coinPage = id => `https://www.coingecko.com/en/coins/${sources[id][0] === 'ondo-finance' ? 'ondo' : sources[id][0]}`;
const tradingViewAssets = new Set('MON BTC ETH SOL HYPE PENGU LINK ONDO AAVE PEPE UNI USDC'.split(' '));
const hasTradingView = a => tradingViewAssets.has(a.id);
const provider = (a,state) => hasTradingView(a) && state.chartProvider === 'tradingview' ? 'tradingview' : 'coingecko';
export const chartKey = (a,state) => `${a.id}:${provider(a,state)}:${state.chartInterval}:${state.theme}`;
export function spark(a) {
  const source=sources[a.id];
  if(!source)return '<span class="muted">—</span>';
  return `<span class="spark-wrap"><img class="spark" src="https://data.coingecko.com/coins/${source[1]}/sparkline.svg" width="120" height="34" alt="${a.id} 7-day chart by CoinGecko" loading="lazy" decoding="async"><span class="spark-unavailable" hidden>—</span></span>`;
}
export function chart(a,state) {
  const tv=provider(a,state)==='tradingview';
  return `<section class="provider-chart" data-chart-key="${chartKey(a,state)}" aria-label="${a.id} price chart"><div class="provider-toolbar"><div class="provider-tabs">${hasTradingView(a)?`<button data-action="chart-provider" data-id="tradingview" class="${tv?'selected':''}" aria-pressed="${tv}">TradingView</button>`:''}<button data-action="chart-provider" data-id="coingecko" class="${!tv?'selected':''}" aria-pressed="${!tv}">CoinGecko</button></div><span>${a.id} / ${tv?'USDT':'USD'}</span></div>${tv?`<div class="native-chart-tools"><div class="chart-intervals" aria-label="Price interval">${[['15','15m'],['60','1h'],['240','4h'],['D','1D']].map(([id,label])=>`<button data-action="chart-interval" data-id="${id}" class="${state.chartInterval===id?'selected':''}" aria-pressed="${state.chartInterval===id}">${label}</button>`).join('')}</div><span class="grow"></span><button data-action="chart-fit" aria-label="Reset chart zoom">Reset</button></div><div class="chart-quote"><strong id="chart-price">—</strong><span id="chart-change"></span><small>Bybit · Spot reference</small></div><div class="chart-ohlc" id="chart-ohlc" aria-live="off"></div>`:''}<div id="market-chart" class="chart-embed ${tv?'tradingview-native':'coingecko'}" role="group" aria-label="${a.id} price line chart"></div><div class="chart-foot">${tv?'<a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a><span id="chart-status" role="status">Loading</span>':`<span>Token price · CoinGecko</span><a href="${coinPage(a.id)}" target="_blank" rel="noopener noreferrer">Open chart ↗</a>`}</div></section>`;
}
// TradingView Lightweight Charts™ Copyright (c) 2025 TradingView, Inc.
// https://www.tradingview.com/ — official library, not a custom chart renderer.
let chartLibrary;
const loadTradingView = () => chartLibrary ||= import(location.origin+'/assets/lightweight-charts-5.2.1.mjs').catch(error=>{chartLibrary=null;throw error;});
let activeChart;
export function disposeChart() {
  if(!activeChart)return;
  activeChart.controller.abort();
  activeChart.providerCleanup?.();
  clearTimeout(activeChart.timer);
  activeChart.api?.remove();
  activeChart=null;
}
export function fitChart(){if(activeChart?.api&&activeChart.points)fitPriceLine(activeChart.api,activeChart.points);}
function failed(host) {
  if (!host.isConnected) return;
  host.replaceChildren();
  const message=document.createElement('div');
  message.className='chart-error';
  message.innerHTML='<span>Chart unavailable</span><button class="btn small" data-action="chart-retry">Retry</button>';
  host.append(message);
}
export async function mountChart(a,state) {
  const host=document.querySelector('#market-chart');
  if(!host||host.dataset.mounted)return;
  disposeChart();
  host.dataset.mounted='true';
  const source=sources[a.id],dark=state.theme==='dark';
  host.innerHTML='<div class="chart-loading">Loading chart…</div>';
  if(provider(a,state)==='tradingview')return mountTradingView(host,a,state.chartInterval,dark);
  try {
    activeChart={controller:new AbortController(),providerCleanup:mountProviderChart(host,{kind:'coin',coin:source[0]},{dark,onFailure:()=>failed(host)})};
  }catch{failed(host);}
}
const historyCache=new Map();
export function mountPoolPriceChart(a,state){
  const parent=document.querySelector('#pool-chart');if(!parent)return;
  parent.innerHTML='<section class="provider-chart"><div class="chart-quote"><strong id="chart-price">—</strong><span id="chart-change"></span><small>Monad pool reference</small></div><div class="chart-ohlc" id="chart-ohlc" aria-live="off"></div><div id="market-chart" class="chart-embed tradingview-native" aria-label="Pool price line chart"></div><div class="chart-foot"><a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a><span id="chart-status" role="status">Loading</span></div></section>';
  disposeChart();
  const target=providerTarget(a);
  if(target&&state.chartProvider!=='tradingview'){const host=parent.querySelector('#market-chart');host.style.height='360px';activeChart={controller:new AbortController(),providerCleanup:mountProviderChart(host,target,{dark:state.theme==='dark',onFailure:()=>failed(host)})};parent.querySelector('.chart-foot').innerHTML='<span>CoinGecko · Monad token</span>';return;}
  return mountTradingView(parent.querySelector('#market-chart'),a,'D',state.theme==='dark',`/api/market-chart?asset=${encodeURIComponent(a.id)}&kind=spot&period=1D`);
}
async function mountTradingView(host,a,interval,dark,requestURL=`/api/chart?asset=${encodeURIComponent(a.id)}&interval=${interval}`){
  const session={controller:new AbortController(),api:null,timer:null};
  activeChart=session;
  const section=host.closest('.provider-chart');
  const status=section.querySelector('#chart-status');
  const historyKey=requestURL+'|'+(a.pair||'');
  const getData=async(force=false)=>{
    const cached=historyCache.get(historyKey);if(!force&&cached&&!cached.stale&&Date.now()/1000-cached.fetchedAt<120)return cached;
    const response=await fetch(requestURL,{signal:session.controller.signal});
    if(!response.ok)throw new Error('Chart data unavailable');
    const data=await response.json();
    if(data.asset!==a.id||data.interval&&data.interval!==interval)throw new Error('Invalid chart identity');
    if(data.pool&&a.pair&&data.pool.toLowerCase()!==a.pair.toLowerCase())throw new Error('Chart pool changed');
    const points=data.points||closingPrices(data.candles||[]);if(!points.length)throw new Error('No chart observations');
    const normalized={...data,points};historyCache.delete(historyKey);historyCache.set(historyKey,normalized);while(historyCache.size>16)historyCache.delete(historyCache.keys().next().value);return normalized;
  };
  try{
    const [lib,data]=await Promise.all([loadTradingView(),getData()]);
    if(!host.isConnected||activeChart!==session)return;
    host.replaceChildren();
    const api=session.api=lib.createChart(host,{
      autoSize:true,
      layout:{background:{type:lib.ColorType.Solid,color:dark?'#111214':'#ffffff'},textColor:dark?'#969aa5':'#687080',fontFamily:'Inter, sans-serif',fontSize:11,attributionLogo:true},
      grid:{vertLines:{visible:false},horzLines:{color:dark?'#1f2228':'#edf0f4'}},
      rightPriceScale:{borderVisible:false,scaleMargins:{top:.12,bottom:.12}},
      timeScale:{borderVisible:false,timeVisible:interval!=='D',secondsVisible:false,rightOffset:4},
      crosshair:{mode:lib.CrosshairMode.Normal},
      handleScroll:{vertTouchDrag:false},localization:{locale:'en-US'}
    });
    const last=data.points.at(-1),precision=last.value<.0001?9:last.value<1?5:2;
    const price=api.addSeries(lib.LineSeries,priceLineOptions(precision));
    let previousTime=0,latestPoint=last;
    const ohlc=section.querySelector('#chart-ohlc');
    const showPoint=p=>{ohlc.textContent=money(p.value,precision)+' · '+new Date(Number(p.time)*1000).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});};
    const paint=(next,initial=false)=>{
      const points=next.points;
      price.applyOptions({pointMarkersVisible:points.length===1,pointMarkersRadius:3});
      session.points=points;
      if(initial){price.setData(points);fitPriceLine(api,points);}
      else for(const p of points.filter(p=>p.time>=previousTime))price.update(p);
      latestPoint=points.at(-1);previousTime=latestPoint.time;
      section.querySelector('#chart-price').textContent=money(latestPoint.value,precision);
      const move=points[0].value>0?(latestPoint.value/points[0].value-1)*100:0;
      const change=section.querySelector('#chart-change');change.textContent=changeText(move);change.className=changeClass(move);change.title='Chart range change';
      showPoint(latestPoint);
      status.textContent=`Updated ${new Date(next.fetchedAt*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`;
      host.dataset.points=String(points.length);host.dataset.series='line';
    };
    paint(data,true);
    api.subscribeCrosshairMove(p=>{const point=p.seriesData.get(price);showPoint(point?{time:p.time,value:point.value}:latestPoint);});
    const refresh=async()=>{
      if(!host.isConnected||activeChart!==session)return;
      if(!document.hidden){try{paint(await getData(true));}catch(error){if(error.name!=='AbortError')status.textContent='Update paused · Retry shortly';}}
      if(activeChart===session)session.timer=setTimeout(refresh,30000);
    };
    session.timer=setTimeout(refresh,30000);
  }catch(error){
    if(error.name==='AbortError'||activeChart!==session)return;
    disposeChart();status.textContent='Data unavailable';failed(host);
  }
}
// Provider errors never fall back to generated prices or invented history.
document.addEventListener('error',event=>{
  if (event.target.matches?.('img.spark')) {
    event.target.hidden=true;
    event.target.parentElement.querySelector('.spark-unavailable').hidden=false;
  }
},true);
