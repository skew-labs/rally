// Disposable wallet-performance fixtures. These are not real trader claims.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33229';
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'rally-market-ui-')),fixture=path.join(temp,'fixture.json');
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{cwd:root,env:{...process.env,RALLY_TESTING:'1',RALLY_PREVIEW_PORT:'33229',RALLY_FIXTURE_FILE:fixture,RALLY_WALLET_MARKET_FIXTURE:'1'},stdio:['ignore','ignore','pipe']});
let logs='',browser,checks=0;server.stderr.on('data',data=>logs+=data);
const settled=page=>page.evaluate(async()=>{await Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{})));await new Promise(r=>requestAnimationFrame(r));});
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({headless:true,executablePath:process.env.RALLY_CHROME_PATH});
 for(const width of [320,390,768,1440])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[],writes=[];
  await context.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',route=>{const request=route.request();if(!['GET','HEAD'].includes(request.method()))writes.push(request.url());return new URL(request.url()).origin===origin?route.continue():route.abort();});
  await page.goto(origin+'/?view=feeds');await page.locator('.rc-algorithm-row[data-wallet=true]').first().waitFor();
  assert.equal(await page.locator('.rc-algorithm-row[data-wallet=true]').count(),3);checks++;
  const order=()=>page.locator('.rc-algorithm-row[data-wallet=true]').evaluateAll(a=>a.map(x=>x.dataset.feed));
  const ids=await order();assert.equal(ids[0],'wallet-'+(1).toString(16).padStart(40,'0'));checks++;
  await page.getByRole('button',{name:'Top ROI',exact:true}).click();assert.equal((await order())[0],'wallet-'+(2).toString(16).padStart(40,'0'));checks++;
  assert.equal(await page.locator('.rc-algorithm-row[data-wallet=true]').first().locator('.rc-row-result>b').innerText(),'+500%');checks++;
  await page.locator('.rc-algorithm-row[data-wallet=true]').first().click();await page.locator('.am-performance>strong').waitFor();await settled(page);
  assert((await page.locator('.am-performance>strong').innerText()).includes('+50'));checks++;
  assert.equal(await page.locator('.am-preview-foot .r-btn').innerText(),'Track wallet');checks++;
  assert.equal(await page.locator('.am-about').getAttribute('open'),null);assert(!await page.getByText('40 * wallet_buyers + 20 * wallet_exits + recency',{exact:true}).isVisible());checks++;
  const footer=await page.locator('.am-preview-foot').boundingBox();assert(footer.y+footer.height<=900);checks++;
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));checks++;
  await page.locator('.am-trade>summary').click();assert(await page.locator('.am-trade-proof a').isVisible());checks++;
  await page.locator('.am-preview-foot .r-btn').click();await page.waitForURL('**/?view=home&section=feed');
  assert.equal(await page.evaluate(()=>localStorage.getItem('rally:guest-feed')),ids[2]);checks++;
  await page.goto(origin+'/?view=algorithms');await page.locator('.rc-algorithm-row[data-wallet=true]').first().waitFor();assert.equal(await page.locator('.r-algorithm-card code').count(),0);checks++;
  await page.getByRole('button',{name:'Paid',exact:true}).click();assert.equal(await page.locator('.rc-algorithm-row[data-wallet=true]').count(),0);assert.equal(await page.locator('#algorithm-market-list .rc-algorithm-row').count(),1);checks++;
  await page.locator('#algorithm-market-list .rc-algorithm-row').click();await page.locator('.am-preview-foot .r-btn').waitFor();assert.equal(await page.locator('.am-preview-foot .r-btn').innerText(),'Buy · 1 USDC');checks++;
  assert(!await page.locator('.am-performance').isVisible());checks++;
  await page.getByRole('button',{name:'Close dialog',exact:true}).click();await page.locator('[role=dialog]').waitFor({state:'detached'});
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);checks+=2;
  await context.close();
 }
 console.log(JSON.stringify({checks,views:8,scope:'Synthetic UI only, provider-blocked; no wallet or financial operations'}));
}catch(e){console.error(logs);throw e;}finally{await browser?.close();server.kill('SIGTERM');await fs.rm(temp,{recursive:true,force:true});}
