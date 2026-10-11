// Real handlers and disposable social state; no live wallets or financial writes.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33231';
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'rally-community-ui-')),fixture=path.join(temp,'fixture.json');
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{cwd:root,env:{...process.env,RALLY_TESTING:'1',RALLY_PREVIEW_PORT:'33231',RALLY_FIXTURE_FILE:fixture},stdio:['ignore','ignore','pipe']});
let logs='',browser,checks=0;server.stderr.on('data',d=>logs+=d);
const settled=page=>page.evaluate(async()=>{await Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{})));await new Promise(r=>requestAnimationFrame(r));});
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 const data=JSON.parse(await fs.readFile(fixture,'utf8'));
 browser=await chromium.launch({headless:true,executablePath:process.env.RALLY_CHROME_PATH});
 for(const width of [320,390,768,1440])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height:960},timezoneId:'Asia/Seoul'}),page=await context.newPage(),errors=[],writes=[];
  await context.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',route=>{const r=route.request();if(!['GET','HEAD'].includes(r.method()))writes.push({url:r.url(),method:r.method()});return new URL(r.url()).origin===origin?route.continue():route.abort();});
  await page.goto(origin+'/?view=communities');await page.locator('.cx-card').first().waitFor();
  assert.equal(await page.locator('.cx-card').count(),3);checks++;
  assert.equal(await page.locator('.cx-card').first().getAttribute('data-community'),'qa-community');checks++;
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));checks++;
  await page.getByRole('button',{name:'Tokens',exact:true}).click();assert.equal(await page.locator('.cx-card').count(),1);checks++;
  await page.getByRole('searchbox',{name:'Search communities'}).fill('missing');assert.equal(await page.locator('.cx-card').count(),0);checks++;
  await page.getByRole('button',{name:'Browse all',exact:true}).click();assert.equal(await page.locator('.cx-card').count(),3);checks++;
  await page.getByRole('button',{name:'Members',exact:true}).click();assert.equal(await page.locator('.cx-card').first().getAttribute('data-community'),'qa-community');checks++;
  const card=page.locator('[data-community="qa-community"]');
  await card.getByRole('button',{name:'Buy TEST',exact:true}).click();await page.getByRole('dialog',{name:'Trade TEST'}).waitFor();
  assert((await page.locator('.r-route-tabs').innerText()).includes('PancakeSwap v2'));checks++;
  assert.equal(await page.locator('.r-pay-select b').innerText(),'USDC');checks++;
  assert.equal(new URL(page.url()).searchParams.get('view'),'communities');checks++;
  await page.getByRole('button',{name:'Close trade panel'}).click();
  await card.getByRole('button',{name:'Open QA community'}).click();await page.locator('.cx-room').waitFor();
  assert(await page.getByRole('button',{name:'Buy TEST',exact:true}).isVisible());checks++;
  assert(await page.getByRole('button',{name:'Sell TEST',exact:true}).isVisible());checks++;
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));checks++;
  await page.getByRole('button',{name:'Sell TEST',exact:true}).click();await page.getByRole('dialog',{name:'Trade TEST'}).waitFor();
  assert.equal(await page.locator('.r-pay-select b').innerText(),'TEST');checks++;
  assert((await page.locator('.r-trade-head').innerText()).includes('Sell TEST'));checks++;
  await page.getByRole('button',{name:'Close trade panel'}).click();
  await page.locator('.r-community-tabs [data-id=algorithms]').click();await page.locator('.cx-feed').waitFor();
  assert((await page.locator('.cx-feed footer').innerText()).includes('1 USDC'));checks++;
  await page.locator('.cx-feed-preview').click();await page.locator('.am-preview-foot .r-btn:not([disabled])').waitFor();
  assert.equal(await page.locator('.am-preview-foot .r-btn').innerText(),'Buy · 1 USDC');checks++;
  await page.getByRole('button',{name:'Close dialog',exact:true}).click();
  await page.locator('.r-community-tabs [data-id=posts]').click();await settled(page);
  if(process.env.RALLY_EVIDENCE_DIR&&[390,1440].includes(width)){
   await page.screenshot({path:path.join(process.env.RALLY_EVIDENCE_DIR,`qa-community-${width}-${theme}.png`)});
   await page.goto(origin+'/?view=communities');await page.locator('.cx-card').first().waitFor();await settled(page);
   await page.screenshot({path:path.join(process.env.RALLY_EVIDENCE_DIR,`qa-communities-${width}-${theme}.png`)});
  }
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);checks+=2;
  await context.close();
 }
 // Old references must not keep looking like a current market price.
 const oldContext=await browser.newContext(),oldPage=await oldContext.newPage();
 await oldContext.addInitScript(()=>{const real=Date.now.bind(Date);Date.now=()=>real()+180000;});
 await oldContext.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
 await oldPage.goto(origin+'/?view=community&id=qa-community');await oldPage.locator('.cx-room-market').waitFor();
 assert.equal(await oldPage.locator('.cx-room-market>div:nth-child(2) strong').innerText(),'—');checks++;
 assert.equal(await oldPage.locator('.cx-room-reference>span').innerText(),'Price unavailable');checks++;
 await oldContext.close();
 // One membership mutation against the disposable server, with repeat taps coalesced.
 const context=await browser.newContext({viewport:{width:390,height:900}}),page=await context.newPage();
 await context.addCookies([{name:'rally_session',value:data.cookie,url:origin}]);
 await context.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
 let joins=0;page.on('request',r=>{if(r.url().endsWith('/api/join')&&r.method()==='POST')joins++;});
 await page.goto(origin+'/?view=communities');const join=page.locator('[data-community=monad] [data-action=join]');await join.waitFor();
 await join.evaluate(b=>{b.click();b.click();});await page.locator('[data-community=monad] .cx-card-foot [data-action=community]').waitFor();
 assert.equal(joins,1);checks++;
 await page.getByRole('button',{name:'Joined',exact:true}).click();assert.equal(await page.locator('.cx-card').count(),2);checks++;
 await context.close();
 console.log(JSON.stringify({checks,views:8,membershipWrites:1,scope:'Disposable QA only; no signatures or financial submissions'}));
}catch(e){console.error(logs);throw e;}finally{await browser?.close();server.kill('SIGTERM');await fs.rm(temp,{recursive:true,force:true});}
