import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33220';
const evidence=process.env.RALLY_EVIDENCE||'/tmp/rally-holders';await fs.mkdir(evidence,{recursive:true});
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{cwd:root,env:{...process.env,RALLY_PREVIEW_PORT:'33220'},stdio:'ignore'});
const sleep=ms=>new Promise(r=>setTimeout(r,ms)),asset='0x'+'a'.repeat(40),now=Math.floor(Date.now()/1000);
const holders=Array.from({length:20},(_,i)=>({address:'0x'+(i+1).toString(16).padStart(40,'0'),name:i===1?'A long nickname '.repeat(5):'',amount:i===3?'0.00000000123456':i===4?'1'+'0'.repeat(70):'890567000.123456789123456789'}));
const snapshot={asset,indexed:true,total:1412,source:'nad.fun',fetchedAt:now,holders,refreshing:false};
const source=await fs.readFile(root+'/holder-ui.js','utf8'),css=await fs.readFile(root+'/wallet.css','utf8');
const html='<!doctype html><html><head><link rel="stylesheet" href="/wallet.css"><style>body{margin:0;font:14px Arial;background:var(--paper);color:var(--text);--paper:#fff;--raised:#f2f2f5;--muted:#73737c;--line:#ddd;--accent:#9178ff}html[data-theme=dark] body{--paper:#19191f;--raised:#24242b;--muted:#aaa;--line:#333;--text:#eee}main{padding:20px;max-width:600px;margin:auto;min-width:0}</style></head><body><main><section id="holders" class="r-holders"></section></main></body></html>';
let browser;const results=[];
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await sleep(100);}
 browser=await chromium.launch({headless:true});
 for(const width of [320,390,1440])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height:850}}),page=await context.newPage();let reads=0;const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',async r=>{
   const u=new URL(r.request().url());assert.equal(r.request().method(),'GET');if(u.origin!==origin)return r.abort();
   if(u.pathname==='/holder-fixture')return r.fulfill({contentType:'text/html',body:html});
   if(u.pathname==='/holder-ui.js')return r.fulfill({contentType:'text/javascript',body:source});
   if(u.pathname==='/wallet.css')return r.fulfill({contentType:'text/css',body:css});
   if(u.pathname==='/api/token-holders'){reads++;await sleep(450);return r.fulfill({json:snapshot});}
   return r.continue();
  });
  await page.goto(origin+'/holder-fixture');
  await page.evaluate(async({theme,asset})=>{
   document.documentElement.dataset.theme=theme;window.H=await import('/holder-ui.js');window.c={api:async p=>(await fetch(p)).json(),esc:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),age:()=> 'now'};
   await Promise.all([H.warmHolders(c,asset),H.warmHolders(c,asset)]);
   window.mount=()=>H.mountHolders(c,document.querySelector('#holders'),asset);
  },{theme,asset});assert.equal(reads,1,'Intent and mount must share an upstream read');
  const firstFrameMs=await page.evaluate(async()=>{const at=performance.now();window.mount();await new Promise(requestAnimationFrame);return performance.now()-at;});
  assert(firstFrameMs<=30,'Holders first frame '+firstFrameMs);assert.equal(await page.locator('.r-holder').count(),20);assert.equal(reads,1);
  const geometry=await page.locator('#holders').evaluate(host=>{const b=host.getBoundingClientRect();return [...host.querySelectorAll('.r-holder,.r-holder-identity,.r-holder-amount')].map(e=>({class:e.className,b:e.getBoundingClientRect()})).filter(x=>x.b.left<b.left-1||x.b.right>b.right+1).map(x=>x.class);});assert.deepEqual(geometry,[]);
  assert.equal(await page.locator('.r-holder').first().locator('small').count(),0);assert.equal(await page.locator('.r-holder-amount').first().getAttribute('title'),holders[0].amount+' tokens');
  await page.screenshot({path:`${evidence}/holders-${width}-${theme}.png`});
  await page.waitForFunction(()=>localStorage.getItem('rally:holder-snapshots:v1'));
  await page.reload();
  const restoredMs=await page.evaluate(async asset=>{const H=await import('/holder-ui.js'),c={api:async p=>(await fetch(p)).json(),esc:String,age:()=> 'now'},at=performance.now();H.mountHolders(c,document.querySelector('#holders'),asset);await new Promise(requestAnimationFrame);return performance.now()-at;},asset);
  assert(restoredMs<=30,'Restored holder first frame '+restoredMs);assert.equal(await page.locator('.r-holder').count(),20);assert.equal(reads,1);assert.deepEqual(errors,[]);
  results.push({width,theme,firstFrameMs,restoredMs,rows:20,reads,overflow:geometry});await context.close();
 }
 const context=await browser.newContext(),page=await context.newPage();let requests=0;
 await context.addInitScript(({asset,snapshot})=>localStorage.setItem('rally:holder-snapshots:v1',JSON.stringify([{...snapshot,fetchedAt:snapshot.fetchedAt-100}])),{asset,snapshot});
 await context.route('**/*',async r=>{const u=new URL(r.request().url());assert.equal(r.request().method(),'GET');if(u.origin!==origin)return r.abort();if(u.pathname==='/holder-fixture')return r.fulfill({contentType:'text/html',body:html});if(u.pathname==='/wallet.css')return r.fulfill({contentType:'text/css',body:css});if(u.pathname==='/holder-ui.js')return r.fulfill({contentType:'text/javascript',body:source});if(u.pathname==='/api/token-holders'){requests++;await sleep(700);return r.fulfill({json:{...snapshot,asset:'0x'+'b'.repeat(40)}});}return r.continue();});
 await page.goto(origin+'/holder-fixture');await page.evaluate(async asset=>{const H=await import('/holder-ui.js');window.done=H.mountHolders({api:async p=>(await fetch(p)).json(),esc:String,age:()=> '2m'},document.querySelector('#holders'),asset);},asset);
 assert.equal(await page.locator('.r-holder').count(),20);assert.match(await page.locator('.r-holders-title').innerText(),/Last known/);await page.evaluate(()=>window.done);assert.equal(await page.locator('.r-holder').count(),20);assert.equal(requests,1);await context.close();
 await fs.writeFile(evidence+'/holders.json',JSON.stringify({results,stalePreserved:true,crossTokenResponseRejected:true,financialTransactions:0},null,2));console.log(JSON.stringify({cases:results.length,firstFrameMs:results.map(x=>x.firstFrameMs),restoredMs:results.map(x=>x.restoredMs)}));
}finally{await browser?.close();server.kill();}
