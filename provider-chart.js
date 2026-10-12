// Provider-rendered charts are isolated from Rally authentication and wallets.
const coins={MON:'monad',BTC:'bitcoin',ETH:'ethereum',SOL:'solana',HYPE:'hyperliquid',PENGU:'pudgy-penguins',LINK:'chainlink',ONDO:'ondo-finance',AAVE:'aave',PEPE:'pepe',UNI:'uniswap',USDC:'usd-coin',ZEC:'zcash',LIT:'lighter',VVV:'venice-token',PUMP:'pump-fun',NEAR:'near',NVDAon:'nvidia-ondo-tokenized-stock',TSLAon:'tesla-ondo-tokenized-stock',AAPLon:'apple-ondo-tokenized-stock',SPYon:'spdr-s-p-500-etf-ondo-tokenized-etf',PAXG:'pax-gold'};
export function providerTarget(asset,kind='spot'){
  if(kind!=='spot')return null;
  const id=String(asset?.address||asset?.id||'').toLowerCase();
  if(kind==='spot'&&/^0x[0-9a-f]{40}$/.test(id)&&id!=='0x'+'0'.repeat(40)){
    if(asset.nadfun&&!asset.graduated)return null;
    if(asset.chainId!=null&&Number(asset.chainId)!==143)return null;
    return {kind:'pool',token:id}; // Token route avoids quoting the opposite side of a pool.
  }
  const coin=coins[kind==='spot'?asset?.id:asset?.symbol];
  return coin?{kind:'coin',coin}:null;
}
export function providerURL(target,dark=false,interval='1'){
  if(target?.kind!=='pool'||!/^0x[0-9a-f]{40}$/.test(target.token))return null;
  const query=new URLSearchParams({embed:'1',info:'0',swaps:'0',light_chart:dark?'0':'1',chart_type:'price',resolution:({'1':'1m','15':'15m','60':'1h','240':'4h'})[interval]||'1m',bg_color:dark?'17181c':'ffffff'});
  return 'https://www.geckoterminal.com/monad/tokens/'+target.token+'?'+query;
}
export function preconnectProvider(){
  for(const origin of ['https://www.geckoterminal.com','https://widgets.coingecko.com'])if(!document.head.querySelector(`link[rel=preconnect][href="${origin}"]`)){
    const link=document.createElement('link');link.rel='preconnect';link.href=origin;link.crossOrigin='anonymous';document.head.append(link);
  }
}
export function mountProviderChart(host,target,{dark=false,interval='1',onFailure=()=>{}}={}){
  if(!host||!target)return ()=>{};
  preconnectProvider();let disposed=false,timer;
  const frame=document.createElement('iframe'),channel=crypto.randomUUID();
  frame.title=target.kind==='pool'?'CoinGecko · Monad token chart':'CoinGecko · Spot reference chart';
  frame.className='r-provider-frame';frame.referrerPolicy='strict-origin-when-cross-origin';frame.loading='eager';
  frame.style.cssText='display:block;width:100%;height:100%;border:0;min-width:0';
  frame.setAttribute('sandbox',target.kind==='pool'?'allow-scripts allow-same-origin':'allow-scripts');
  frame.setAttribute('allow','fullscreen');
  const fail=()=>{if(!disposed)onFailure();};
  const message=e=>{if(e.source!==frame.contentWindow||e.data?.channel!==channel)return;if(e.data.state==='failed')fail();};
  window.addEventListener('message',message);frame.onerror=fail;
  if(target.kind==='pool')frame.src=providerURL(target,dark,interval);
  else if(target.kind==='coin'&&/^[a-z0-9-]{1,80}$/.test(target.coin)){
    frame.srcdoc=`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0;background:${dark?'#17181c':'#fff'};height:100%;overflow:hidden}gecko-coin-price-chart-widget{display:block;width:100%}</style><script>Object.defineProperty(window,'sessionStorage',{value:{getItem:()=>null,setItem:()=>{},removeItem:()=>{}}});<\/script></head><body><gecko-coin-price-chart-widget coin-id="${target.coin}" locale="en" initial-currency="usd" height="200" width="0" dark-mode="${dark}" transparent-background="true" outlined="false"></gecko-coin-price-chart-widget><script src="https://widgets.coingecko.com/gecko-coin-price-chart-widget.js" onerror="parent.postMessage({channel:'${channel}',state:'failed'},'*')"><\/script></body></html>`;
  }else {window.removeEventListener('message',message);fail();return ()=>{};}
  host.replaceChildren(frame);host.dataset.provider='coingecko';host.setAttribute('aria-busy','true');
  frame.onload=()=>{if(!disposed&&host.isConnected){host.setAttribute('aria-busy','false');host.dataset.frameLoaded='true';}};
  timer=setTimeout(()=>{if(!disposed&&host.isConnected&&host.dataset.frameLoaded!=='true')fail();},12000);
  return ()=>{disposed=true;clearTimeout(timer);window.removeEventListener('message',message);frame.remove();delete host.dataset.provider;delete host.dataset.frameLoaded;};
}
