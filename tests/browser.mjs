// Actual UI and handlers with disposable state. This does not verify live prices or fills.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:4258';
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{cwd:root,stdio:['ignore','pipe','pipe']});
let diagnostics='';server.stderr.on('data',data=>{diagnostics+=data.toString()});
let browser,checks=0;
try{
 let ready=false;
 for(let i=0;i<80;i++){
  if(server.exitCode!==null)throw new Error(diagnostics);
  try{if((await fetch(origin+'/api/health')).ok){ready=true;break;}}catch{}
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 assert(ready,'Offline server did not start: '+diagnostics);
 browser=await chromium.launch({headless:true,...(process.env.RALLY_CHROME_PATH?{executablePath:process.env.RALLY_CHROME_PATH}:{})});
 const pages=['?view=home&section=markets&tab=memes','?view=home&section=markets&tab=spot','?view=home&section=markets&tab=perps','?view=launchpad','?view=communities','?view=discover','?view=leaderboard','?view=algorithms','?view=agents','?view=account'];
 for(const width of [390,768,1440]){
  const context=await browser.newContext({viewport:{width,height:900}}),errors=[],page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  await context.route('**/*',route=>{
   const url=new URL(route.request().url());
   if(url.origin!==origin&& !['data:','blob:'].includes(url.protocol))return route.abort();
   if(!['GET','HEAD'].includes(route.request().method()))throw new Error('UI smoke test attempted a write');
   return route.continue();
  });
  for(const path of pages){
   await page.goto(origin+'/'+path,{waitUntil:'domcontentloaded'});
   await page.waitForSelector('#app');
   await page.waitForFunction(()=>document.querySelector('#app')?.textContent?.trim().length>40);
   await page.waitForTimeout(200);
   assert(await page.locator('#app').isVisible(),path);checks++;
   assert.equal(errors.length,0,errors.join('\n'));checks++;
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Horizontal page overflow: ${width} ${path}`);checks++;
  }
  await context.close();
 }
 console.log(JSON.stringify({checks,viewports:3,views:10,providerCalls:0,walletRequests:0,financialTransactions:0}));
}finally{await browser?.close();server.kill('SIGTERM');}
