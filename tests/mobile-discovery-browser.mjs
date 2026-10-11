// Mobile density and algorithm swipe navigation. Disposable state; no orders.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33235';
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'rally-mobile-discovery-'));
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{cwd:root,env:{...process.env,RALLY_TESTING:'1',RALLY_PREVIEW_PORT:'33235',RALLY_FIXTURE_FILE:path.join(temp,'fixture.json'),RALLY_WALLET_MARKET_FIXTURE:'1'},stdio:['ignore','ignore','pipe']});
let browser,logs='',checks=0;server.stderr.on('data',d=>logs+=d);
const check=(value,message)=>{assert(value,message);checks++;};
const settle=p=>p.evaluate(async()=>{await Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{})));await new Promise(r=>requestAnimationFrame(r));});
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({headless:true,executablePath:process.env.RALLY_CHROME_PATH});
 for(const [width,height] of [[320,720],[390,844],[844,390],[1440,960]])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height},hasTouch:width!==1440,reducedMotion:width===320?'reduce':'no-preference'}),page=await context.newPage(),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));await context.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);
  await context.route('**/*',r=>{if(!['GET','HEAD'].includes(r.request().method())){writes.push(r.request().url());return r.abort();}return new URL(r.request().url()).origin===origin?r.continue():r.abort();});
  await page.goto(origin+'/?view=communities');await page.locator('.cx-card').first().waitFor();
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'community fits');
  if(width!==1440){const boxes=await page.locator('.cx-card').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,w:r.width,h:r.height};}));check(boxes.every(b=>b.x===boxes[0].x),'single community column');check(boxes.every(b=>b.h<145),'community row density');}
  await settle(page);if(process.env.RALLY_EVIDENCE_DIR)await page.screenshot({path:path.join(process.env.RALLY_EVIDENCE_DIR,`web-communities-${width}-${theme}.png`)});
  await page.goto(origin+'/?view=feeds');await page.locator('.am-wallet-card').first().waitFor();
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'algorithm fits');
  if(width!==1440){const boxes=await page.locator('.am-wallet-card').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,h:r.height};}));check(boxes.every(b=>b.x===boxes[0].x),'single algorithm column');check(boxes.every(b=>b.h<145),'algorithm row density');}
  await settle(page);if(process.env.RALLY_EVIDENCE_DIR)await page.screenshot({path:path.join(process.env.RALLY_EVIDENCE_DIR,`web-list-${width}-${theme}.png`)});
  await page.getByRole('button',{name:'Swipe',exact:true}).click();await page.locator('.sa-card[data-active]').waitFor();await settle(page);
  check(await page.locator('[data-action=swipe-tab][data-id=algorithms]').getAttribute('aria-pressed')==='true','algorithm tab selected');
  check((await page.locator('.sa-card[data-active] .sa-result').innerText()).includes('100%'),'sampled wallet results');
  check(await page.locator('[data-swipe-index]').count()<=5,'bounded swipe window');
  check(await page.locator('.r-quick-fields').count()===0,'no order fields on algorithm');
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'swipe fits');
  await page.locator('.sa-card[data-active] .r-swipe-direction.skip').click();await page.waitForFunction(()=>document.querySelector('.sa-card[data-active]')?.dataset.swipeIndex==='1');
  check((await page.locator('.sa-card[data-active] .sa-result').innerText()).includes('150%'),'next algorithm');
  if(width===390){const box=await page.locator('.sa-card[data-active] .sa-identity').boundingBox();await page.mouse.move(box.x+10,box.y+25);await page.mouse.down();await page.mouse.move(box.x+box.width-10,box.y+25,{steps:12});await page.mouse.up();}else await page.locator('.sa-card[data-active] .r-swipe-direction.buy').click();await page.locator('.am-preview-foot .r-btn:not([disabled])').waitFor();
  check(await page.locator('.am-preview-foot .r-btn').innerText()==='Get for free','free preview');
  await page.getByRole('button',{name:'Close dialog',exact:true}).click();await page.locator('.am-preview-modal').waitFor({state:'detached'});
  check(await page.locator('.sa-card[data-active]').getAttribute('data-swipe-index')==='1','position preserved after preview');
  await settle(page);if(process.env.RALLY_EVIDENCE_DIR)await page.screenshot({path:path.join(process.env.RALLY_EVIDENCE_DIR,`web-swipe-${width}-${theme}.png`)});
  await page.getByRole('button',{name:'Exit swipe mode',exact:true}).click();await page.locator('.am-wallet-card').first().waitFor();
  check(new URL(page.url()).searchParams.get('view')==='feeds','return to marketplace');
  check(errors.length===0,'no browser errors '+errors.join(','));check(writes.length===0,'no writes '+writes.join(','));await context.close();
 }
 console.log(JSON.stringify({checks,layouts:8,walletSignatures:0,financialSubmissions:0}));
}catch(e){console.error(logs);throw e;}finally{await browser?.close();server.kill('SIGTERM');await fs.rm(temp,{recursive:true,force:true});}
