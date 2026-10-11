// Real static assets and handlers, isolated state; no external providers or writes.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33241';
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'rally-library-'));
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{cwd:root,env:{...process.env,RALLY_TESTING:'1',RALLY_PREVIEW_PORT:'33241',RALLY_FIXTURE_FILE:path.join(temp,'fixture.json'),RALLY_WALLET_MARKET_FIXTURE:'1'},stdio:['ignore','ignore','pipe']});
let logs='',browser;server.stderr.on('data',d=>logs+=d);let checks=0;const layouts=[];
const evidence=process.env.RALLY_EVIDENCE_DIR;
const settle=p=>p.evaluate(async()=>{await Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{})));await new Promise(r=>requestAnimationFrame(r));});
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({headless:true,executablePath:process.env.RALLY_CHROME_PATH});
 for(const width of [320,375,390,768,1280,1440])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[],writes=[],loads=[];
  await context.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',route=>{const r=route.request();if(!['GET','HEAD'].includes(r.method()))writes.push(r.url());if(/algorithm-library-.*\.json/.test(r.url()))loads.push(r.url());return new URL(r.url()).origin===origin?route.continue():route.abort();});
  await page.goto(origin+'/?view=feeds');await page.locator('.am-wallet-card').first().waitFor();assert.equal(loads.length,0);checks++;
  await page.locator('[data-action="algorithm-tab"][data-id="library"]').click();await page.locator('.al-row').first().waitFor();await settle(page);
  assert.equal(await page.locator('.al-row').count(),24);assert.equal(loads.length,1);checks+=2;
  assert.match(await page.locator('.al-open img').first().getAttribute('src'),/algorithm-brand-aqr-/);
  assert.equal(await page.locator('.al-library').getByText('Research references. No live returns.',{exact:true}).count(),0);checks+=2;
  assert.match(await page.locator('.al-save use').first().getAttribute('href'),/#bookmark$/);checks++;
  assert.match(page.url(),/section=library/);assert.equal(await page.locator('.al-library [data-action="subscribe-feed"]').count(),0);checks+=2;
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));checks++;
  await page.locator('[data-action="library-source"][data-id="a16z"]').click();assert.equal(await page.locator('.al-row').count(),3);checks++;
  await page.locator('.al-row .al-open').first().click();await page.locator('.al-detail-foot').waitFor();await settle(page);
  assert.match(await page.locator('.al-attribution').innerText(),/a16z/);assert.equal(await page.locator('.al-detail-foot [data-action="use-feed"]').count(),0);checks+=2;
  const box=await page.locator('.al-detail-modal').boundingBox(),foot=await page.locator('.al-detail-foot').boundingBox();assert(box.x>=-1&&box.x+box.width<=width+1);assert(foot.y+foot.height<=901);checks+=2;
  await page.locator('.al-detail-save').click();assert.equal(await page.locator('.al-detail-save').innerText(),'Saved');checks++;
  await page.keyboard.press('Escape');await page.locator('[role=dialog]').waitFor({state:'detached'});
  await page.locator('[data-action="library-source"][data-id=""]').click();await page.locator('[data-action="library-saved"]').click();assert.equal(await page.locator('.al-row').count(),1);checks++;
  await page.reload();await page.locator('.al-row').first().waitFor();await page.locator('[data-action="library-saved"]').click();assert.equal(await page.locator('.al-row').count(),1);checks++;
  await page.locator('[data-action="library-saved"]').click();await page.locator('#library-search').fill('Wilder');assert.equal(await page.locator('.al-row').count(),3);checks++;
  await page.locator('#library-search').fill('not-a-real-reference-987');assert.equal(await page.locator('.al-row').count(),0);checks++;
  await page.locator('[data-action="library-reset"]').click();while(await page.locator('.al-more').isVisible())await page.locator('.al-more').click();assert.equal(await page.locator('.al-row').count(),100);checks++;
  await page.evaluate(async()=>{await Promise.all([...document.querySelectorAll('.al-row img')].map(i=>{i.loading='eager';return i.decode();}));});
  if(evidence&&(width===390||width===1440)){await fs.mkdir(evidence,{recursive:true});await page.evaluate(()=>{scrollTo(0,0);document.activeElement?.blur();});await page.mouse.move(1,1);await settle(page);await page.screenshot({path:path.join(evidence,`library-${width}-${theme}.png`)});}
  await page.locator('[data-action="algorithm-tab"][data-id="market"]').click();await page.locator('.am-wallet-card').first().waitFor();assert.equal(await page.locator('.am-wallet-card').count(),3);checks++;
  await page.getByRole('button',{name:'Top ROI',exact:true}).click();assert.equal(await page.locator('.am-wallet-card').first().locator('.am-return').innerText(),'+500%');checks++;
  await page.goBack();await page.locator('.al-row').first().waitFor();assert.match(page.url(),/section=library/);checks++;
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);checks+=2;layouts.push({width,theme});await context.close();
 }
 // Failed download is recoverable and leaving during load cannot replace the next page.
 const page=await browser.newPage();let failures=1;
 await page.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
 await page.route('**/assets/algorithm-library-*.json',r=>failures-->0?r.fulfill({status:503,body:'Unavailable'}):r.continue());
 await page.goto(origin+'/?view=feeds&section=library');await page.locator('[data-action="library-retry"]').click();await page.locator('.al-row').first().waitFor();checks++;
 await page.close();
 const away=await browser.newPage();let release;const held=new Promise(r=>release=r);
 await away.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
 await away.route('**/assets/algorithm-library-*.json',async r=>{await held;await r.continue();});
 await away.goto(origin+'/?view=feeds&section=library');await away.locator('.al-loading').waitFor();
 await away.locator('[data-action=algorithm-tab][data-id=market]').click();await away.locator('.am-wallet-card').first().waitFor();
 const completed=away.waitForResponse(r=>/algorithm-library-.*\.json/.test(r.url()));release();await completed;await settle(away);
 assert.equal(await away.locator('.al-library').count(),0);assert.equal(await away.locator('.am-wallet-card').count(),3);checks+=2;
 const report={checks,layouts,references:100,sourceLogos:37,boundedRows:24,lazyCatalog:true,downloadRetry:true,legacyMarketplace:true,noWrites:true};
 if(evidence)await fs.writeFile(path.join(evidence,'library-browser.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}catch(e){console.error(logs.slice(-2000));throw e;}finally{await browser?.close();server.kill('SIGTERM');await fs.rm(temp,{recursive:true,force:true});}
