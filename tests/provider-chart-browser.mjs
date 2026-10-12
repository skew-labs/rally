import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33220';
const evidence=process.env.RALLY_EVIDENCE||'/tmp/rally-provider-evidence';await fs.mkdir(evidence,{recursive:true});
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{cwd:root,env:{...process.env,RALLY_PREVIEW_PORT:'33220'},stdio:'ignore'});
const sleep=ms=>new Promise(r=>setTimeout(r,ms)),now=Math.floor(Date.now()/1000),id='0x'+'a'.repeat(40);
const token={id,address:id,chainId:143,symbol:'BUSY',name:'Busy Land',venue:'nad.fun',nadfun:true,price:.002,marketCap:2000000,referenceAt:now,created:now,graduated:true,progressBps:10000,locked:false,tradeSupported:true,quoteSymbol:'MON',logoURI:'/assets/MON.png',creator:'0x'+'b'.repeat(40)};
const points=[{time:now-7200,value:.002},{time:now-3600,value:.0022},{time:now,value:.0021}];
let browser;const results=[];
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await sleep(100);}
 browser=await chromium.launch({headless:true});
 for(const width of [320,390,768,1440])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),reads=[],errors=[];let providerReads=0;
  await context.addInitScript(theme=>localStorage.setItem('rally-theme',theme),theme);page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',async r=>{
   const q=r.request(),u=new URL(q.url());assert.equal(q.method(),'GET','No financial writes');
   if(u.hostname==='www.geckoterminal.com'){assert(u.pathname.includes('/monad/tokens/'+id));providerReads++;return r.fulfill({contentType:'text/html',body:'<!doctype html><body>Provider embed fixture</body>'});}
   if(u.origin!==origin)return r.abort();let body;
   if(u.pathname==='/api/nadfun/tokens')body={tokens:[token],total:1,fetchedAt:now};
   else if(u.pathname==='/api/nadfun/references')body={tokens:[token]};
   else if(u.pathname==='/api/nadfun/token'){await sleep(1500);body=token;}
   else if(u.pathname==='/api/token-holders')body={asset:id,indexed:true,total:1,fetchedAt:now,holders:[{address:'0x'+'1'.repeat(40),amount:'890567000',name:''}]};
   else if(u.pathname==='/api/nadfun/chart')throw Error('Indexed provider charts must not enter the nad.fun queue');
   else if(u.pathname==='/api/market-chart'){assert.equal(u.searchParams.get('fresh'),'1');reads.push(q.url());await sleep(80);body={asset:id,points,reference:'Monad pool reference',source:'GeckoTerminal · CoinGecko',sourceURL:'https://www.geckoterminal.com/monad/tokens/'+id,fetchedAt:now,lastObservation:now,freshRead:true,cached:false};}
   return body?r.fulfill({json:body}):r.continue();
  });
  await page.goto(origin+'/?view=home&section=markets&tab=memes');await page.locator('.r-market-buy').waitFor();
  await page.locator('.r-market-buy').click();await page.locator('#nad-chart iframe').waitFor();
  const frame=page.locator('#nad-chart iframe');assert.match(await frame.getAttribute('src'),new RegExp('/monad/tokens/'+id));assert.equal(await frame.getAttribute('sandbox'),'allow-scripts allow-same-origin');
  assert.equal(reads.length,0);await page.locator('[data-action=nad-interval][data-id="240"]').click();await page.waitForFunction(()=>document.querySelector('#nad-chart iframe')?.src.includes('resolution=4h'));
  await page.locator('[data-action=nad-chart-line]').click();await page.waitForFunction(()=>document.querySelector('#nad-chart')?.dataset.series==='line');assert.equal(reads.length,1);
  await page.locator('[data-action=nad-chart-retry]').count();
  const geometry=await page.evaluate(()=>({pageOverflow:document.documentElement.scrollWidth>innerWidth+1,panelOverflow:document.querySelector('.r-nad-content').scrollWidth>document.querySelector('.r-nad-content').clientWidth+1}));assert(!geometry.pageOverflow&&!geometry.panelOverflow);
  await page.locator('[data-action=nad-interval][data-id="15"]').click();await page.waitForFunction(()=>document.querySelector('#nad-chart')?.dataset.interval==='15');assert.equal(reads.length,2,'Every line interval must perform a fresh provider read');
  await page.screenshot({path:`${evidence}/provider-${width}-${theme}.png`});assert.deepEqual(errors,[]);results.push({width,theme,...geometry,providerReads,freshReads:reads.length,writes:0});await context.close();
 }
 // A third-party coin script never receives Rally's origin, storage or wallet.
 const context=await browser.newContext(),page=await context.newPage();await context.route('https://widgets.coingecko.com/**',r=>r.fulfill({contentType:'text/javascript',body:''}));
 await page.goto(origin+'/');await page.evaluate(async()=>{const P=await import('/provider-chart.js');const host=document.createElement('div');document.body.replaceChildren(host);P.mountProviderChart(host,{kind:'coin',coin:'bitcoin'});});
 assert.equal(await page.locator('iframe').getAttribute('sandbox'),'allow-scripts');
 const iframe=page.frames().find(f=>f!==page.mainFrame());assert(iframe);await iframe.waitForLoadState();assert(await iframe.evaluate(()=>{try{parent.localStorage.getItem('rally-theme');return false;}catch{return true;}}));await context.close();
 await fs.writeFile(evidence+'/browser.json',JSON.stringify({results,isolatedCoinWidget:true,financialTransactions:0},null,2));console.log(JSON.stringify({cases:results.length,isolatedCoinWidget:true}));
}finally{await browser?.close();server.kill('SIGTERM');}
