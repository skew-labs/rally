import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';
import {observeChartRenderer} from './chart-observer.mjs';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33223';
const evidence=process.env.RALLY_EVIDENCE||'/tmp/rally-hourly';await fs.mkdir(evidence,{recursive:true});
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{cwd:root,env:{...process.env,RALLY_PREVIEW_PORT:'33223'},stdio:'ignore'});
const sleep=ms=>new Promise(r=>setTimeout(r,ms)),hour=Math.floor(Date.now()/3600000)*3600,id='0x'+'a'.repeat(40);
const candles=Array.from({length:25},(_,i)=>({time:hour-(24-i)*3600,open:100+i,high:104+i,low:98+i,close:102+i}));
const modules=new Map(await Promise.all(['market-ui.js','chart-settings.js','price-line.js','holder-ui.js','provider-chart.js','live-price.js'].map(async p=>['/'+p,await fs.readFile(root+'/'+p,'utf8')])));
const html='<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/live.css"><link rel="stylesheet" href="/market.css"><style>body{margin:0}.r-asset-modal{display:block;margin:8px auto;width:min(640px,calc(100% - 16px));max-height:none}button{font:inherit}</style></head><body><main id="root"></main></body></html>';
const results=[];let browser;
try {
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await sleep(100);}
 browser=await chromium.launch({headless:true});
 for(const width of [320,390,768,1440])for(const theme of ['light','dark'])for(const kind of ['spot','perps']) {
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[];let reads=0,updates=false;
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',async r=>{
   const u=new URL(r.request().url());assert.equal(r.request().method(),'GET');if(u.hostname==='www.geckoterminal.com')return r.fulfill({contentType:'text/html',body:'Provider history fixture'});if(u.origin!==origin)return r.abort();
   if(await observeChartRenderer(r))return;
   if(modules.has(u.pathname))return r.fulfill({contentType:'text/javascript',body:modules.get(u.pathname)});
   if(u.pathname==='/hourly-fixture')return r.fulfill({contentType:'text/html',body:html});
   if(u.pathname==='/api/market-chart'){
    reads++;await sleep(35);const hourly=u.searchParams.get('interval')==='1h',bars=structuredClone(candles);if(updates)bars.at(-1).close+=.5;
    return r.fulfill({json:{asset:u.searchParams.get('asset'),kind,interval:hourly?'1h':undefined,period:u.searchParams.get('period'),candles:bars,points:bars.map(b=>({time:b.time,value:b.close})),source:'Read-only fixture',reference:'Fixture OHLC',sourceURL:'https://example.com',freshRead:true,cached:false,fetchedAt:hour,lastObservation:hour}});
   }
   if(u.pathname==='/api/token-holders')return r.fulfill({json:{asset:id,holders:[],indexed:true,total:0}});
   if(u.pathname==='/api/market-ticks')return r.fulfill({json:{asset:u.searchParams.get('asset'),kind,epoch:'fixture',cursor:1,points:Array.from({length:160},(_,i)=>({id:i+1,time:hour-160+i,value:126+i/100})),source:'Fixture ticks',observationType:'price_update'}});
   return r.continue();
  });
  await page.goto(origin+'/hourly-fixture');
  await page.evaluate(async({theme,kind,id})=>{
   document.documentElement.dataset.theme=theme;const {marketUI}=await import('/market-ui.js');
   const asset={id,address:id,chainId:143,symbol:'TEST',name:'Test token',price:126},S={perps:{markets:[{id:'1',venue:'Perpl',symbol:'BTC',mark:126,last:126,open:true,execution:'wallet_transactions'}]}};
   const api=async(path,_,options)=>{const r=await fetch(path,options);if(!r.ok)throw Error('Unavailable');return r.json();};
   const ui=marketUI({S,$:s=>document.querySelector(s),api,esc:s=>String(s??'').replaceAll('<','&lt;'),usd:v=>'$'+v,priceHTML:String,volumeHTML:String,age:()=>'',logo:()=>'',token:()=>asset,
    modal:(title,body,cls)=>{S.modal?.cleanup?.();document.querySelector('#root').innerHTML='<div class="'+cls+'">'+body+'</div>';S.modal={};},trade:()=>{throw Error('No trading');},finance:{perplAsset:()=>({symbol:'BTC',name:'Bitcoin'}),handle:()=>{throw Error('No trading');}}});
   window.openFixture=()=>ui.details(kind==='spot'?id:'1',kind);window.closeFixture=()=>{S.modal.cleanup();S.modal=null;document.querySelector('#root').replaceChildren();};ui.details(kind==='spot'?id:'1',kind);
  },{theme,kind,id});
  await page.waitForFunction(()=>document.querySelector('.r-mini-chart')?.dataset.series==='line');
  assert.equal(await page.locator('[data-mini-history]').getAttribute('aria-pressed'),'true');
  await page.locator('[data-mini-candles]').click();
  await page.waitForFunction(()=>document.querySelector('.r-mini-chart')?.dataset.series==='candles');
  assert.deepEqual(await page.evaluate(()=>window.chartSeriesObserved.at(-1).points),candles);
  const created=await page.evaluate(()=>window.chartCreateCount);
  await page.locator('[data-mini-range="7D"]').click();await page.waitForFunction(()=>window.chartSeriesObserved.at(-1).sets===2);
  assert.equal(await page.evaluate(()=>window.chartCreateCount),created);
  // Resume refresh: only the changed current hour goes through series.update.
  updates=true;await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
  await page.waitForFunction(()=>window.chartSeriesObserved.at(-1).updates===1);
  assert.equal(await page.evaluate(()=>window.chartSeriesObserved.at(-1).sets),2);
  const metrics=await page.evaluate(()=>({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth+1,chartWidth:document.querySelector('.r-mini-chart').getBoundingClientRect().width,setMs:window.chartSeriesObserved.at(-1).setMs,creates:window.chartCreateCount}));
  assert(!metrics.overflow);assert(metrics.chartWidth<=width);
  await page.screenshot({path:`${evidence}/${kind}-${width}-${theme}.png`});
  await page.locator('[data-mini-history]').click();

  await page.waitForFunction(()=>document.querySelector('.r-mini-chart')?.dataset.series==='line');
  await page.locator('[data-mini-candles]').click();await page.waitForFunction(()=>document.querySelector('.r-mini-chart')?.dataset.series==='candles');
  await page.locator('[data-mini-live="ticks"]').click();
  await page.waitForFunction(()=>document.querySelector('.r-mini-chart')?.dataset.series==='ticks');
  await page.locator('[data-mini-window="120"]').click();
  assert.equal(await page.locator('.r-mini-chart').getAttribute('data-visible-points'),'120');
  await page.locator('[data-mini-window="30"]').click();
  assert.equal(await page.locator('.r-mini-chart').getAttribute('data-visible-points'),'30');
  await page.evaluate(()=>{window.closeFixture();window.openFixture();});
  await page.waitForFunction(()=>document.querySelector('.r-mini-chart')?.dataset.series==='ticks');
  assert.equal(await page.locator('[data-mini-window="30"]').getAttribute('aria-pressed'),'true');
  await page.locator('[data-mini-history]').click();
  await page.waitForFunction(()=>document.querySelector('.r-mini-chart')?.dataset.series==='line');
  await page.locator('[data-mini-live="line"]').click();
  await page.waitForFunction(()=>document.querySelector('.r-mini-chart')?.dataset.series==='live-line');
  assert.equal(await page.locator('[data-mini-history]').getAttribute('aria-pressed'),'true');
  await page.locator('[data-mini-period="1D"]').click();
  await page.waitForFunction(()=>document.querySelector('.r-mini-chart')?.dataset.series==='line');
  assert.equal(await page.locator('[data-mini-live="line"]').getAttribute('aria-pressed'),'false');

  await page.evaluate(()=>window.closeFixture());const before=reads;await sleep(150);assert.equal(reads,before);
  assert.deepEqual(errors,[]);results.push({width,theme,kind,...metrics,reads,incrementalUpdate:true,writes:0});await context.close();
 }
 await fs.writeFile(evidence+'/browser.json',JSON.stringify({results,financialTransactions:0},null,2));console.log(JSON.stringify({cases:results.length,maxSetMs:Math.max(...results.map(r=>r.setMs))}));
}finally{await browser?.close();server.kill();}
