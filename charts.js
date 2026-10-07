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
const provider = (a,state) => hasTradingView(a) && state.chartProvider !== 'coingecko' ? 'tradingview' : 'coingecko';
export const chartKey = (a,state) => `${a.id}:${provider(a,state)}:${state.chartInterval}:${state.theme}`;
export function spark(a) {
  const source=sources[a.id];
  if(!source)return '<span class="muted">—</span>';
  return `<span class="spark-wrap"><img class="spark" src="https://data.coingecko.com/coins/${source[1]}/sparkline.svg" width="120" height="34" alt="${a.id} 7-day chart by CoinGecko" loading="lazy" decoding="async"><span class="spark-unavailable" hidden>—</span></span>`;
}
export function chart(a,state) {
  const tv=provider(a,state)==='tradingview';
  return `<section class="provider-chart" data-chart-key="${chartKey(a,state)}" aria-label="${a.id} price chart"><div class="provider-toolbar"><div class="provider-tabs">${hasTradingView(a)?`<button data-action="chart-provider" data-id="tradingview" class="${tv?'selected':''}" aria-pressed="${tv}">TradingView</button>`:''}<button data-action="chart-provider" data-id="coingecko" class="${!tv?'selected':''}" aria-pressed="${!tv}">CoinGecko</button></div><span>${a.id} / ${tv?'USDT':'USD'}</span></div>${tv?`<div class="native-chart-tools"><div class="chart-intervals" aria-label="Candle interval">${[['15','15m'],['60','1h'],['240','4h'],['D','1D']].map(([id,label])=>`<button data-action="chart-interval" data-id="${id}" class="${state.chartInterval===id?'selected':''}" aria-pressed="${state.chartInterval===id}">${label}</button>`).join('')}</div><span class="grow"></span><button data-action="chart-fit" aria-label="Reset chart zoom">Reset</button></div><div class="chart-quote"><strong id="chart-price">—</strong><span id="chart-change"></span><small>Bybit · Spot reference</small></div><div class="chart-ohlc" id="chart-ohlc" aria-live="off"></div>`:''}<div id="market-chart" class="chart-embed ${tv?'tradingview-native':'coingecko'}" role="group" aria-label="${a.id} ${tv?'candlestick':'price'} chart"></div><div class="chart-foot">${tv?'<a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a><span id="chart-status" role="status">Loading</span>':`<span>Token price · CoinGecko</span><a href="${coinPage(a.id)}" target="_blank" rel="noopener noreferrer">Open chart ↗</a>`}</div></section>`;
}
// TradingView Lightweight Charts™ Copyright (c) 2025 TradingView, Inc.
// https://www.tradingview.com/ — official library, not a custom chart renderer.
let chartLibrary;
const loadTradingView = () => chartLibrary ||= import('https://cdn.jsdelivr.net/npm/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.mjs').catch(error=>{chartLibrary=null;throw error;});
let activeChart;
export function disposeChart() {
  if(!activeChart)return;
  activeChart.controller.abort();
  clearTimeout(activeChart.timer);
  activeChart.api?.remove();
  activeChart=null;
}
export function fitChart(){activeChart?.api?.timeScale().fitContent();}
let geckoScript;
function loadGecko() {
  if (!geckoScript) geckoScript = new Promise((resolve,reject) => {
    const script = document.createElement('script');
    script.src = 'https://widgets.coingecko.com/gecko-coin-price-chart-widget.js';
    script.async = true;
    script.onload = resolve;
    script.onerror = () => {script.remove();geckoScript=null;reject(new Error('CoinGecko unavailable'));};
    document.head.append(script);
  });
  return geckoScript;
}
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
    await loadGecko();
    if(!host.isConnected)return;
    const widget=document.createElement('gecko-coin-price-chart-widget');
    Object.entries({'coin-id':source[0],locale:'en','initial-currency':'usd',height:'360',width:'0','dark-mode':String(dark),'transparent-background':'true',outlined:'false'}).forEach(([key,value])=>widget.setAttribute(key,value));
    host.replaceChildren(widget);
  }catch{failed(host);}
}
async function mountTradingView(host,a,interval,dark){
  const session={controller:new AbortController(),api:null,timer:null};
  activeChart=session;
  const section=host.closest('.provider-chart');
  const status=section.querySelector('#chart-status');
  const getData=async()=>{
    const response=await fetch(`/api/chart?asset=${encodeURIComponent(a.id)}&interval=${interval}`,{signal:session.controller.signal});
    if(!response.ok)throw new Error('Chart data unavailable');
    const data=await response.json();
    if(data.asset!==a.id||data.interval!==interval||!data.candles?.length)throw new Error('Invalid chart data');
    return data;
  };
  try{
    const [lib,data]=await Promise.all([loadTradingView(),getData()]);
    if(!host.isConnected||activeChart!==session)return;
    host.replaceChildren();
    const api=session.api=lib.createChart(host,{
      autoSize:true,
      layout:{background:{type:lib.ColorType.Solid,color:dark?'#111214':'#ffffff'},textColor:dark?'#969aa5':'#687080',fontFamily:'Inter, sans-serif',fontSize:11,attributionLogo:true},
      grid:{vertLines:{color:dark?'#1b1e24':'#f1f3f6'},horzLines:{color:dark?'#1f2228':'#edf0f4'}},
      rightPriceScale:{borderVisible:false,scaleMargins:{top:.08,bottom:.23}},
      timeScale:{borderVisible:false,timeVisible:interval!=='D',secondsVisible:false,rightOffset:4},
      crosshair:{mode:lib.CrosshairMode.Normal},
      handleScroll:{vertTouchDrag:false},localization:{locale:'en-US'}
    });
    const last=data.candles.at(-1),precision=last.close<.0001?9:last.close<1?5:2;
    const price=api.addSeries(lib.CandlestickSeries,{upColor:'#55c7a0',downColor:'#e6828e',borderVisible:false,wickUpColor:'#55c7a0',wickDownColor:'#e6828e',priceFormat:{type:'price',precision,minMove:10**-precision}});
    const volume=api.addSeries(lib.HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'volume',lastValueVisible:false,priceLineVisible:false});
    api.priceScale('volume').applyOptions({scaleMargins:{top:.83,bottom:0},visible:false});
    let previousTime=0,latestCandle=last;
    const ohlc=section.querySelector('#chart-ohlc');
    const showCandle=c=>{ohlc.textContent=`O ${c.open.toFixed(precision)}   H ${c.high.toFixed(precision)}   L ${c.low.toFixed(precision)}   C ${c.close.toFixed(precision)}`;};
    const paint=(next,initial=false)=>{
      const candles=next.candles;
      const volumePoint=c=>({time:c.time,value:c.volume,color:c.close>=c.open?'rgba(85,199,160,.24)':'rgba(230,130,142,.24)'});
      if(initial){price.setData(candles);volume.setData(candles.map(volumePoint));api.timeScale().fitContent();}
      else for(const c of candles.filter(c=>c.time>=previousTime)){price.update(c);volume.update(volumePoint(c));}
      latestCandle=candles.at(-1);previousTime=latestCandle.time;
      section.querySelector('#chart-price').textContent=money(latestCandle.close,precision);
      const move=(latestCandle.close/latestCandle.open-1)*100;
      const change=section.querySelector('#chart-change');change.textContent=changeText(move);change.className=changeClass(move);change.title='Current candle change';
      showCandle(latestCandle);
      status.textContent=`Updated ${new Date(next.fetchedAt*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`;
      host.dataset.candles=String(candles.length);
    };
    paint(data,true);
    api.subscribeCrosshairMove(p=>showCandle(p.seriesData.get(price)||latestCandle));
    const refresh=async()=>{
      if(!host.isConnected||activeChart!==session)return;
      if(!document.hidden){try{paint(await getData());}catch(error){if(error.name!=='AbortError')status.textContent='Update paused · Retry shortly';}}
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
