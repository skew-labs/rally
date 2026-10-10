// Explicit market fixtures. User taps prepare an order; no wallet or provider writes.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33214';
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{cwd:root,env:{...process.env,RALLY_PREVIEW_PORT:'33214'},stdio:['ignore','ignore','pipe']});let diagnostics='';server.stderr.on('data',d=>diagnostics+=d);let browser,checks=0;
try {
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({headless:true,...(process.env.RALLY_CHROME_PATH?{executablePath:process.env.RALLY_CHROME_PATH}:{})});
 const id='0x'+'a'.repeat(40),token={id,address:id,symbol:'QA',name:'QA market fixture',venue:'nad.fun',nadfun:true,price:1,marketCap:100000,referenceAt:Date.now()/1000,created:Date.now()/1000,graduated:true,progressBps:10000,locked:false,tradeSupported:true,quoteSymbol:'MON',logoURI:'/assets/MON.png',creator:'0x'+'b'.repeat(40)};
 for(const width of [320,390,1440])for(const theme of ['light','dark']) {
  const context=await browser.newContext({viewport:{width,height:844},reducedMotion:width===320?'reduce':'no-preference'}),page=await context.newPage(),errors=[];
  await context.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',r=>{const q=r.request(),u=new URL(q.url());if(u.origin!==origin)return r.abort();if(q.method()!=='GET')throw Error('Financial or account write blocked');
   const body=u.pathname==='/api/nadfun/tokens'?{tokens:[token,{...token,id:'0x'+'c'.repeat(40),address:'0x'+'c'.repeat(40),symbol:'LOCKED',locked:true}],total:2,fetchedAt:Date.now()/1000}:u.pathname==='/api/nadfun/token'?token:u.pathname==='/api/nadfun/references'?{tokens:[token]}:u.pathname==='/api/nadfun/chart'?{candles:[]}:u.pathname==='/api/token-holders'?{holders:[],refreshing:false,indexed:true}:null;
   return body?r.fulfill({contentType:'application/json',body:JSON.stringify(body)}):r.continue();
  });
  await page.goto(origin+'/?view=home&section=markets&tab=memes');const quick=page.locator('.r-market-buy[aria-label="Buy QA"]');await quick.waitFor();assert(await quick.isEnabled());assert(await page.locator('.r-market-buy[aria-label="Buy LOCKED"]').isDisabled());checks+=2;
  assert(await quick.evaluate(e=>e.getBoundingClientRect().height>=44));checks++;
  await quick.click();await page.locator('#nad-order-form').waitFor();assert.equal(new URL(page.url()).searchParams.get('view'),'home');assert(await page.locator('.r-nad-panel').isVisible());checks+=2;
  const shortcut=page.locator('.r-checkout-presets button').first();await shortcut.click();assert.equal(await page.locator('#nad-order-form input[name=amount]').inputValue(),'1');assert(await shortcut.evaluate(e=>document.activeElement===e));assert(await page.locator('#nad-order-form [type=submit]').isEnabled());checks+=3;
  assert(await page.locator('#nad-order-form [type=submit]').evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight+1;}));checks++;
  await page.locator('[data-action=nad-close]').last().click();await page.locator('.r-nad-panel').waitFor({state:'detached'});assert(await quick.isVisible());assert.deepEqual(errors,[]);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));checks+=3;
  await context.close();
 }
 console.log(JSON.stringify({checks,viewports:3,themes:2,directOrderEntry:true,providerCalls:0,walletSignatures:0,financialTransactions:0}));
}finally {await browser?.close();server.kill('SIGTERM');}
