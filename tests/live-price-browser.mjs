import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33221';
const evidence=process.env.RALLY_EVIDENCE||'/tmp/rally-live-price';await fs.mkdir(evidence,{recursive:true});
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{cwd:root,env:{...process.env,RALLY_PREVIEW_PORT:'33221'},stdio:'ignore'});
const sleep=ms=>new Promise(r=>setTimeout(r,ms)),id='0x'+'a'.repeat(40),now=Math.floor(Date.now()/1000);
const token={id,address:id,chainId:143,symbol:'BUSY',name:'Busy Land',venue:'nad.fun',nadfun:true,price:.002,marketCap:2000000,referenceAt:now,created:now,graduated:true,progressBps:10000,locked:false,tradeSupported:true,quoteSymbol:'MON',logoURI:'/assets/MON.png',creator:'0x'+'b'.repeat(40)};
let browser;const results=[];
try {
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await sleep(100);}
 browser=await chromium.launch({headless:true});
 for(const width of [320,390,768,1440])for(const theme of ['light','dark']) {
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[];let reads=0;
  await context.addInitScript(theme=>{if(window.top===window)localStorage.setItem('rally-theme',theme);},theme);page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',r=>{
   const request=r.request(),u=new URL(request.url());assert.equal(request.method(),'GET');if(u.origin!==origin)return r.abort();
   let data;
   if(u.pathname==='/api/nadfun/tokens')data={tokens:[token],total:1,fetchedAt:now};
   if(u.pathname==='/api/nadfun/references')data={tokens:[token]};
   if(u.pathname==='/api/nadfun/token')data=token;
   if(u.pathname==='/api/token-holders')data={asset:id,indexed:true,total:1,fetchedAt:now,holders:[{address:'0x'+'1'.repeat(40),amount:'890567000'}]};
   if(u.pathname==='/api/market-chart')data={asset:id,kind:'spot',freshRead:true,period:u.searchParams.get('period'),interval:u.searchParams.get('interval'),points:[{time:now-3600,value:.002},{time:now,value:.0021}],candles:[{time:now-3600,open:.002,high:.0022,low:.0019,close:.0021}],reference:'Fixture price',source:'Fixture',sourceURL:'https://example.com',lastObservation:now};
   if(u.pathname==='/api/market-ticks') { assert.equal(u.searchParams.get('asset'),id);assert.equal(u.searchParams.get('kind'),'spot');reads++;const n=reads;data={asset:id,kind:'spot',epoch:'real-observations',cursor:n,source:'nad.fun USD reference',stale:false,observationType:'price_update',points:[{id:n,time:now+n,value:.002+n*.00001}]}; }
   return data?r.fulfill({json:data}):r.continue();
  });
  await page.goto(origin+'/?view=home&section=markets&tab=memes');await page.locator('.r-market-buy').click();
  await page.waitForFunction(()=>document.querySelector('#nad-chart')?.dataset.series==='line');
  await page.locator('[data-action=nad-live-mode][data-id=candles]').click();await page.waitForFunction(()=>document.querySelector('#nad-chart')?.dataset.series==='candles');
  await page.locator('[data-action=nad-live-mode][data-id=history]').click();await page.waitForFunction(()=>document.querySelector('#nad-chart')?.dataset.series==='line');
  await page.locator('[data-action=nad-live-mode][data-id=line]').click();await page.waitForFunction(()=>document.querySelector('#nad-chart')?.dataset.series==='live-line');
  await page.waitForFunction(()=>Number(document.querySelector('#nad-chart')?.dataset.points)>=2);
  await page.locator('[data-action=nad-live-mode][data-id=ticks]').click();await page.waitForFunction(()=>document.querySelector('#nad-chart')?.dataset.series==='ticks');
  await page.locator('[data-action=nad-tick-window][data-id="120"]').click();
  assert.equal(await page.locator('#nad-chart').getAttribute('data-tick-window'),'120');
  const bounds=await page.evaluate(()=>{const host=document.querySelector('#nad-chart'),canvas=host.querySelector('canvas'),panel=document.querySelector('.r-nad-content');return {pageOverflow:document.documentElement.scrollWidth>innerWidth+1,panelOverflow:panel.scrollWidth>panel.clientWidth+1,chartOverflow:canvas.getBoundingClientRect().right>host.getBoundingClientRect().right+1,points:Number(host.dataset.points),selected:[...document.querySelectorAll('[data-action=nad-live-mode]')].filter(b=>b.getAttribute('aria-pressed')==='true').map(b=>b.dataset.id),caption:document.querySelector('#nad-chart-status').textContent};});
  assert.deepEqual(bounds.selected,['ticks']);
  assert(!bounds.pageOverflow&&!bounds.panelOverflow&&!bounds.chartOverflow);assert(bounds.caption.includes('nad.fun USD reference'));
  await page.screenshot({path:`${evidence}/ticks-${width}-${theme}.png`});await page.getByRole('button',{name:'Close token trade',exact:true}).click();const before=reads;await sleep(1200);assert.equal(reads,before,'Closed sheets must stop polling');assert.deepEqual(errors,[]);
  results.push({width,theme,...bounds,errors,financialTransactions:0});await context.close();
 }
 const page=await browser.newPage();await page.goto(origin+'/');
 const frames=await page.evaluate(async origin=>{
  const L=await import(origin+'/live-price.js'),report=[];
  const raw=Array.from({length:500},(_,i)=>({id:i+1,time:100+i,value:12+i*.001})),merged=L.mergeTicks([],{points:raw,epoch:'a'},null);
  if(merged.length!==240||merged.at(-1).value!==raw.at(-1).value)throw Error('Tick ring lost observed data');
  if(L.mergeTicks(merged,{points:[],epoch:'b'},'a').length)throw Error('Source reset retained unrelated data');
  const raf=window.requestAnimationFrame,caf=window.cancelAnimationFrame;
  try {
   for(const hz of [60,120,144]) {
    let queue=new Map(),id=0,count=0;window.requestAnimationFrame=fn=>{queue.set(++id,fn);return id;};window.cancelAnimationFrame=id=>queue.delete(id);
    const host=document.createElement('div');host.style.cssText='width:600px;height:200px';document.body.replaceChildren(host);const chart=L.livePriceChart(host);
    const samples=raw.slice(0,60),snapshot=JSON.stringify(samples);chart.setData(samples);chart.setData([...samples,raw[60]]);const start=performance.now();
    for(let i=1;queue.size&&i<200;i++){const pending=[...queue.values()];queue.clear();pending.forEach(fn=>fn(start+i*1000/hz));count++;}
    if(queue.size||JSON.stringify(samples)!==snapshot)throw Error('Frame loop modified ticks or did not stop');
    const stats=chart.stats();report.push({simulatedHz:hz,animationFrames:count,...stats});chart.dispose();
   }
  } finally {window.requestAnimationFrame=raf;window.cancelAnimationFrame=caf;}
  return report;
 },origin);
 assert(frames.every(f=>!f.animating&&f.meanDrawMs<1000/144));await page.emulateMedia({reducedMotion:'reduce'});
 const reduced=await page.evaluate(async origin=>{const L=await import(origin+'/live-price.js'),host=document.createElement('div');host.style.cssText='width:390px;height:200px';document.body.replaceChildren(host);const c=L.livePriceChart(host);c.setData([{id:1,time:1,value:2}]);c.setData([{id:1,time:1,value:2},{id:2,time:2,value:3}]);const stats=c.stats();c.dispose();return stats;},origin);assert(!reduced.animating);
 await fs.writeFile(evidence+'/browser.json',JSON.stringify({results,frames,reduced,financialTransactions:0},null,2));console.log(JSON.stringify({cases:results.length,frames,reduced}));
} finally {await browser?.close();server.kill('SIGTERM');}
