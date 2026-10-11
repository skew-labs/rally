// Actual renderer + delayed read fixtures. No accounts, wallets or provider writes.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';
import {observeChartRenderer} from './chart-observer.mjs';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33218';
const evidence=process.env.RALLY_EVIDENCE||'/tmp/rally-chart-evidence';await fs.mkdir(evidence,{recursive:true});
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{cwd:root,env:{...process.env,RALLY_PREVIEW_PORT:'33218'},stdio:['ignore','ignore','pipe']});
let browser,diagnostics='';server.stderr.on('data',d=>diagnostics+=d);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const id='0x'+'a'.repeat(40),now=Math.floor(Date.now()/1000);
const token={id,address:id,symbol:'BUSY',name:'Busy Land',venue:'nad.fun',nadfun:true,price:.002,marketCap:2000000,referenceAt:now,created:now,graduated:true,progressBps:10000,locked:false,tradeSupported:true,quoteSymbol:'MON',logoURI:'/assets/MON.png',creator:'0x'+'b'.repeat(40)};
const candles=Array.from({length:30},(_,i)=>({time:now-3600*(30-i),open:1+i*.01,high:1.03+i*.01,low:.97+i*.01,close:1.02+i*.01,volume:10}));
const holders={asset:id,indexed:true,total:1412,source:'nad.fun',fetchedAt:now,refreshing:false,holders:[
 {address:'0x'+'1'.repeat(40),name:'',amount:'890567000.123456789123456789'},
 {address:'0x'+'2'.repeat(40),name:'A very long holder nickname that must not push the balance outside the panel',amount:'50000000'},
 {address:'0x'+'3'.repeat(40),name:'',amount:'22501200'},
 {address:'0x'+'4'.repeat(40),name:'',amount:'0.00000000123456'},
]};
const results=[];
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await sleep(100);}
 browser=await chromium.launch({headless:true});
 for(const width of [320,390,768,1440])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height:900},reducedMotion:width===320?'reduce':'no-preference'}),page=await context.newPage(),errors=[],requests=[];
  await context.addInitScript(theme=>localStorage.setItem('rally-theme',theme),theme);page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',async r=>{
   const q=r.request(),u=new URL(q.url());if(u.origin!==origin)return r.abort();assert.equal(q.method(),'GET','No writes allowed');
   if(await observeChartRenderer(r))return;
   let body;
   if(u.pathname==='/api/nadfun/tokens')body={tokens:[token],total:1,fetchedAt:now};
   else if(u.pathname==='/api/nadfun/references')body={tokens:[token]};
   else if(u.pathname==='/api/nadfun/token'){requests.push({kind:'token',at:Date.now()});await sleep(650);body=token;}
   else if(u.pathname==='/api/nadfun/chart'){
    const interval=u.searchParams.get('interval');requests.push({kind:'chart',interval,at:Date.now()});
    await sleep(interval==='15'?650:80);
    body={token:id,interval,candles,source:'nad.fun',fetchedAt:now,stale:false,refreshing:false};
   }else if(u.pathname==='/api/token-holders'){await sleep(500);body=holders;}
   return body?r.fulfill({contentType:'application/json',body:JSON.stringify(body)}):r.continue();
  });
  await page.goto(origin+'/?view=home&section=markets&tab=memes');
  const buy=page.locator('.r-market-buy');
  try{await buy.waitFor({timeout:15000});}catch(e){console.error(JSON.stringify({url:page.url(),errors,body:(await page.locator('body').innerText()).slice(0,2000)}));await page.screenshot({path:evidence+'/failure.png'});throw e;}
  await buy.click();await page.waitForFunction(()=>document.querySelector('#nad-chart')?.dataset.series==='line');
  const observed=await page.evaluate(()=>window.chartSeriesObserved);
  assert(observed.length>0);assert(observed.every(s=>s.type==='line'),'Basic price charts must use real line series');
  assert.deepEqual(observed.at(-1).points,candles.map(({time,close})=>({time,value:close})),'Keep actual closes and sparse observation times');
  assert.equal(await page.locator('#nad-chart').getAttribute('data-series'),'line');
  const chartRequest=requests.find(r=>r.kind==='chart'),identity=requests.find(r=>r.kind==='token');assert(chartRequest.at<identity.at+300,'Chart must start alongside identity');
  await page.locator('.r-holder').first().waitFor();
  assert.equal(await page.locator('.r-holder').first().locator('small').count(),0,'Unnamed address must appear only once');
  assert.match(await page.locator('.r-holder-amount').first().innerText(),/890.6M/);
  assert.equal(await page.locator('.r-holder-amount').first().getAttribute('title'),holders.holders[0].amount+' tokens');
  await page.locator('#nad-holders').scrollIntoViewIfNeeded();
  const geometry=await page.evaluate(()=>{
   const panel=document.querySelector('.r-nad-panel').getBoundingClientRect(),list=document.querySelector('#nad-holders').getBoundingClientRect();
   const overflow=[...document.querySelectorAll('.r-holder,.r-holder-amount,.r-holder-identity,.r-holders-title')].filter(e=>{const r=e.getBoundingClientRect();return r.left<list.left-1||r.right>list.right+1;}).map(e=>e.className);
   return {left:list.left-panel.left,right:panel.right-list.right,overflow,pageOverflow:document.documentElement.scrollWidth>innerWidth+1,panelOverflow:document.querySelector('.r-nad-content').scrollWidth>document.querySelector('.r-nad-content').clientWidth+1};
  });
  assert(geometry.left>=19&&geometry.right>=19,JSON.stringify(geometry));assert.deepEqual(geometry.overflow,[]);assert(!geometry.pageOverflow&&!geometry.panelOverflow);
  await page.screenshot({path:`${evidence}/holders-${width}-${theme}.png`});
  await page.locator('[data-action=nad-interval][data-id="15"]').click();
  await page.locator('[data-action=nad-interval][data-id="240"]').click();
  await page.waitForFunction(()=>document.querySelector('#nad-chart')?.dataset.interval==='240');await sleep(750);
  assert.equal(await page.locator('#nad-chart').getAttribute('data-interval'),'240','Old interval response cannot replace current chart');
  // Interval changes must not dispose the still-open one-tap checkout controller.
  await page.locator('.r-checkout-presets button').first().click();assert.equal(await page.locator('#nad-order-form input[name=amount]').inputValue(),'1');
  await page.locator('[data-action=nad-close]').last().click();await page.locator('.r-nad-panel').waitFor({state:'detached'});
  const before=requests.filter(r=>r.kind==='chart').length;
  await page.evaluate(()=>{
   window.chartPaintMs=null;window.chartFirstFrameMs=null;window.chartSetupMs=null;window.tokenCompleteFrameMs=null;document.addEventListener('click',e=>{if(!e.target.closest('.r-market-buy'))return;const at=performance.now();const watch=new MutationObserver(()=>{if(document.querySelector('#nad-chart canvas')&&document.querySelector('#nad-holders')?.dataset.holdersReady==='true'&&document.querySelector('#nad-holders .r-holder')){watch.disconnect();window.chartSetupMs=performance.now()-at;requestAnimationFrame(()=>{window.chartFirstFrameMs=performance.now()-at;window.tokenCompleteFrameMs=window.chartFirstFrameMs;requestAnimationFrame(()=>window.chartPaintMs=performance.now()-at);});}});watch.observe(document.querySelector('#trade-root'),{childList:true,subtree:true});},{once:true,capture:true});
  });
  const start=Date.now();await buy.click();await page.locator('#nad-chart canvas').first().waitFor();await page.waitForFunction(()=>window.chartPaintMs!=null);const {paintMs,firstFrameMs,setupMs}=await page.evaluate(()=>({paintMs:window.chartPaintMs,firstFrameMs:window.chartFirstFrameMs,setupMs:window.chartSetupMs}));
  const reopenMs=Date.now()-start;assert.equal(requests.filter(r=>r.kind==='chart').length,before,'Reopen must reuse the snapshot');
  assert(firstFrameMs<=30,'Cached token chart and holders must share a first frame within 30ms: '+firstFrameMs);assert(paintMs<100,'Warm chart must not wait for a 650ms identity read: '+paintMs);assert.deepEqual(errors,[]);results.push({width,theme,...geometry,reopenMs,setupMs,firstFrameMs,paintMs,chartRequests:before});await context.close();
 }
 // A stale snapshot stays on screen while polling, without recreating the chart.
 const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();let updates=0;
 await context.route('**/*',r=>{
  const u=new URL(r.request().url());if(u.origin!==origin)return r.abort();assert.equal(r.request().method(),'GET');let body;
  if(u.pathname==='/api/nadfun/tokens')body={tokens:[token],total:1};
  else if(u.pathname==='/api/nadfun/token')body=token;
  else if(u.pathname==='/api/nadfun/references')body={tokens:[token]};
  else if(u.pathname==='/api/token-holders')body=holders;
  else if(u.pathname==='/api/nadfun/chart'){updates++;body={token:id,interval:'60',candles,source:'nad.fun',fetchedAt:updates===1?now-100:now,stale:updates===1,refreshing:updates===1,retryAfter:2};}
  return body?r.fulfill({contentType:'application/json',body:JSON.stringify(body)}):r.continue();
 });
 await page.goto(origin+'/?view=home&section=markets&tab=memes');await page.locator('.r-market-buy').click();await page.locator('#nad-chart canvas').first().waitFor();
 await sleep(100);assert.equal(updates,1,'A stale venue response must not trigger another immediate background read');
 await page.locator('[data-action=nad-close]').last().click();await page.locator('.r-nad-panel').waitFor({state:'detached'});
 await page.locator('.r-market-buy').click();await page.locator('#nad-chart canvas').first().waitFor();
 await page.waitForFunction(()=>!document.querySelector('#nad-chart')?.dataset.preview);
 assert.equal(updates,1,'Rapid reopening must share the stale response and its pending refresh');
 await page.evaluate(()=>window.firstChartCanvas=document.querySelector('#nad-chart canvas'));
 await page.waitForFunction(()=>document.querySelector('#nad-chart-status')?.textContent==='nad.fun data');
 assert.equal(updates,2);assert(await page.evaluate(()=>window.firstChartCanvas===document.querySelector('#nad-chart canvas')));
 await context.close();
 // A cold request timeout must not strand the quote preview after the server warms.
 const retryContext=await browser.newContext({viewport:{width:390,height:850}}),retryPage=await retryContext.newPage();let attempts=0;
 await retryContext.route('**/*',async r=>{const u=new URL(r.request().url());if(u.origin!==origin)return r.abort();assert.equal(r.request().method(),'GET');let body;
  if(u.pathname==='/api/nadfun/tokens')body={tokens:[token],total:1};else if(u.pathname==='/api/nadfun/token')body=token;else if(u.pathname==='/api/nadfun/references')body={tokens:[token]};else if(u.pathname==='/api/token-holders')body=holders;
  else if(u.pathname==='/api/nadfun/chart'){attempts++;if(attempts===1){await sleep(150);return r.fulfill({status:503,json:{message:'Read-only fixture timeout'}});}body={token:id,interval:u.searchParams.get('interval'),candles,source:'nad.fun',fetchedAt:now,stale:false,refreshing:false};}
  return body?r.fulfill({json:body}):r.continue();});
 await retryPage.goto(origin+'/?view=home&section=markets&tab=memes');await retryPage.locator('.r-market-buy').waitFor();await retryPage.evaluate(()=>document.querySelector('.r-market-buy').click());
 await retryPage.waitForFunction(()=>document.querySelector('#nad-chart-status')?.textContent==='nad.fun · Updating history');await retryPage.waitForFunction(()=>document.querySelector('#nad-chart')?.dataset.series==='line',{},{timeout:10000});assert.equal(attempts,2);assert.equal(await retryPage.locator('.r-holder').count(),4);await retryContext.close();
 await fs.writeFile(evidence+'/browser.json',JSON.stringify({results,financialTransactions:0,providerCalls:0,coldRetryRecovered:true},null,2));console.log(JSON.stringify(results));
}finally{await browser?.close();server.kill('SIGTERM');}
