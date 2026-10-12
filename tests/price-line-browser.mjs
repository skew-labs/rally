import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';
import {observeChartRenderer} from './chart-observer.mjs';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33219';
const evidence=process.env.RALLY_EVIDENCE||'/tmp/rally-line-evidence';await fs.mkdir(evidence,{recursive:true});
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{cwd:root,env:{...process.env,RALLY_PREVIEW_PORT:'33219'},stdio:'ignore'});
const sleep=ms=>new Promise(r=>setTimeout(r,ms)),now=Math.floor(Date.now()/1000),asset='0x'+'d'.repeat(40);
const points=[{time:now-86400,value:1.23},{time:now-3600,value:1.26},{time:now,value:1.24}];
const candles=points.map(p=>({time:p.time,open:p.value-.01,high:p.value+.02,low:p.value-.02,close:p.value,volume:1}));
const html=`<!doctype html><html><head><style>body{margin:16px;font:14px Arial}.chart-embed,.r-mini-chart{height:280px}button{min-height:44px}.r-asset-actions{display:flex}</style></head><body><main id="root"></main></body></html>`;
const modules=new Map(await Promise.all(['charts.js','price-line.js','market-ui.js','wallet-ui.js','holder-ui.js','provider-chart.js'].map(async name=>['/'+name,await fs.readFile(root+'/'+name,'utf8')])));
const serveModule=async(r,u)=>{if(!modules.has(u.pathname))return false;await r.fulfill({contentType:'text/javascript',body:modules.get(u.pathname)});return true;};
let browser;const results=[];
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await sleep(100);}
 browser=await chromium.launch({headless:true});
 for(const width of [390,1440])for(const theme of ['light','dark'])for(const mode of ['reference','pool','mini']){
  const context=await browser.newContext({viewport:{width,height:700}}),page=await context.newPage(),errors=[];let reads=0;
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',async r=>{
   const u=new URL(r.request().url());assert.equal(r.request().method(),'GET');if(u.hostname==='widgets.coingecko.com')return r.fulfill({contentType:'text/javascript',body:''});if(u.origin!==origin)return r.abort();
   if(await observeChartRenderer(r))return;
   if(await serveModule(r,u))return;
   if(u.pathname==='/line-fixture')return r.fulfill({contentType:'text/html',body:html});
   if(u.pathname==='/api/chart'){reads++;await sleep(400);return r.fulfill({json:{asset:'MON',interval:'60',candles,fetchedAt:now}});}
   if(u.pathname==='/api/market-chart'){if(u.searchParams.get('interval')==='1h')return r.abort();reads++;await sleep(400);return r.fulfill({json:{asset:u.searchParams.get('asset'),points,period:u.searchParams.get('period'),source:'Read-only test fixture',sourceURL:'https://example.com',reference:'Fixture prices',fetchedAt:now,lastObservation:now,stale:false}});}
   return r.continue();
  });
  await page.goto(origin+'/line-fixture');
  await page.evaluate(async({mode,theme,asset})=>{
   document.documentElement.dataset.theme=theme;document.body.style.background=theme==='dark'?'#19191f':'#fff';document.body.style.color=theme==='dark'?'#ddd':'#222';
   const root=document.querySelector('#root');const state={theme,chartProvider:'tradingview',chartInterval:'60'};
   if(mode==='mini'){
    const {marketUI}=await import('/market-ui.js');const S={perps:{markets:[{id:'1',venue:'Perpl',symbol:'BTC',mark:1.24,last:1.24,observationAt:Math.floor(Date.now()/1000),open:true,execution:'wallet_transactions'}]}};
    const api=async(path,_,options)=>{const r=await fetch(path,options);if(!r.ok)throw Error('Read failed');return r.json();};
    const ui=marketUI({S,$:s=>document.querySelector(s),api,esc:s=>String(s??'').replaceAll('<','&lt;'),usd:v=>'$'+v,priceHTML:String,volumeHTML:String,age:()=>'',logo:()=>'',token:()=>null,
     modal:(title,body,cls)=>{S.modal?.cleanup?.();root.innerHTML='<div class="'+cls+'">'+body+'</div>';S.modal={};},trade:()=>{throw Error('No trading allowed');},finance:{perplAsset:()=>({symbol:'BTC',name:'Bitcoin'}),handle:()=>{throw Error('No trading allowed');}}});
    window.mount=()=>{ui.details('1','perps');document.querySelector('[data-mini-history]')?.click();};window.unmount=()=>{S.modal.cleanup();S.modal=null;};
   }else{
    const C=await import('/charts.js');window.unmount=C.disposeChart;
    window.mount=()=>{if(mode==='pool'){root.innerHTML='<div id="pool-chart"></div>';return C.mountPoolPriceChart({id:asset},state);}
     root.innerHTML=C.chart({id:'MON'},state);return C.mountChart({id:'MON'},state);};
   }
   window.mount();
  },{mode,theme,asset});
  if(mode==='mini')assert.equal(await page.locator('iframe').count(),0,'Perps use the small native line');
  await page.waitForFunction(()=>window.chartSeriesObserved?.at(-1)?.points.length===3);
  assert.deepEqual(await page.evaluate(()=>window.chartSeriesObserved.at(-1).points),points,'No invented points in sparse gaps');
  assert((await page.evaluate(()=>window.chartSeriesObserved)).every(s=>s.type==='line'));
  await page.waitForFunction(()=>window.chartCoverage?.()>.85);
  assert.equal(await page.locator('iframe').count(),0,'Basic pool charts render in-app');
  await page.screenshot({path:`${evidence}/line-${mode}-${width}-${theme}.png`});
  if(mode==='mini'){
   const seriesCount=await page.evaluate(()=>window.chartSeriesObserved.length);
   await page.locator('[data-mini-period="7D"]').click();await sleep(600);
   assert.equal(await page.evaluate(()=>window.chartSeriesObserved.length),seriesCount,'Period changes retain the renderer');
   assert.equal(await page.locator('iframe').count(),0);assert.deepEqual(await page.evaluate(()=>window.chartSeriesObserved.at(-1).points),points);
  }
  const before=reads;
  await page.evaluate(()=>{
   window.unmount();window.firstFrameMs=null;const at=performance.now();
   const watch=new MutationObserver(()=>{if(document.querySelector('#market-chart canvas,.r-mini-chart canvas')){watch.disconnect();requestAnimationFrame(()=>window.firstFrameMs=performance.now()-at);}});
   document.querySelector('#root').replaceChildren();watch.observe(document.querySelector('#root'),{subtree:true,childList:true});window.mount();document.querySelector('[data-mini-line]')?.click();
  });
  await page.waitForFunction(()=>window.firstFrameMs!=null);const firstFrameMs=await page.evaluate(()=>window.firstFrameMs);
  if(mode==='mini'){assert.equal(reads,before+1,'Provider fallback reads current data again');assert(firstFrameMs>=300,'Fresh data cannot paint before its upstream fixture responds');}else{assert.equal(reads,before,'Warm reopen reuses observed history');assert(firstFrameMs<=30,mode+' warm first frame '+firstFrameMs);}assert.deepEqual(errors,[]);
  const plotCoverage=await page.evaluate(()=>window.chartCoverage());results.push({width,theme,mode,firstFrameMs,plotCoverage,points:3,reads,writes:0});await context.close();
 }
 const compactProof=await browser.newPage();await compactProof.goto(origin+'/');
 const compact=await compactProof.evaluate(async()=>{const {compactPoints}=await import('/price-line.js');const raw=Array.from({length:9000},(_,i)=>({time:i+1,value:i===100?.001:i===500?100000:2+i%30}));const actual=compactPoints(raw);return {count:actual.length,first:actual[0].time,last:actual.at(-1).time,low:Math.min(...actual.map(p=>p.value)),high:Math.max(...actual.map(p=>p.value)),actual:actual.every(p=>raw[p.time-1]===p)};});
 assert(compact.count<=320&&compact.actual);assert.equal(compact.first,1);assert.equal(compact.last,9000);assert.equal(compact.low,.001);assert.equal(compact.high,100000);await compactProof.close();
 const context=await browser.newContext(),page=await context.newPage();
 await context.route('**/*',async r=>{const u=new URL(r.request().url());if(u.origin!==origin)return r.abort();assert.equal(r.request().method(),'GET');if(await observeChartRenderer(r))return;if(await serveModule(r,u))return;if(u.pathname==='/line-fixture')return r.fulfill({contentType:'text/html',body:html});if(u.pathname==='/api/chart')return r.fulfill({json:{asset:'MON',interval:'60',candles:[candles[0]],fetchedAt:now}});return r.continue();});
 await page.goto(origin+'/line-fixture');await page.evaluate(async()=>{const C=await import('/charts.js'),s={theme:'light',chartProvider:'tradingview',chartInterval:'60'};document.querySelector('#root').innerHTML=C.chart({id:'MON'},s);await C.mountChart({id:'MON'},s);});
 assert.deepEqual(await page.evaluate(()=>window.chartSeriesObserved.at(-1).points),[points[0]]);assert.equal(await page.locator('#market-chart').getAttribute('data-points'),'1');await context.close();
 await fs.writeFile(evidence+'/price-lines.json',JSON.stringify({results,singleObservation:true,compact,financialTransactions:0},null,2));console.log(JSON.stringify({cases:results.length,singleObservation:true,firstFrames:results.map(r=>r.firstFrameMs)}));
}finally{await browser?.close();server.kill();}
