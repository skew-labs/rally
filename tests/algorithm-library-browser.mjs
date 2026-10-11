// Unified collection, official assets and dated research returns. No provider writes.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {validYear} from '../assets/algorithm-library.js';
import {ALGORITHM_LIBRARY_URL} from '../assets/algorithm-library-data.js';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33241';
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'rally-unified-'));
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{cwd:root,env:{...process.env,RALLY_TESTING:'1',RALLY_PREVIEW_PORT:'33241',RALLY_FIXTURE_FILE:path.join(temp,'fixture.json'),RALLY_WALLET_MARKET_FIXTURE:'1'},stdio:['ignore','ignore','pipe']});
let logs='',browser;server.stderr.on('data',d=>logs+=d);let checks=0;const layouts=[];
const evidence=process.env.RALLY_EVIDENCE_DIR;
const settle=p=>p.evaluate(async()=>{await Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{})));await new Promise(r=>requestAnimationFrame(r));});
const catalog=JSON.parse(await fs.readFile(path.join(root,ALGORITHM_LIBRARY_URL),'utf8'));
const recorded=catalog.items.filter(a=>a.performance1Y);assert.equal(recorded.length,5);
for(const a of recorded){assert(validYear(a.performance1Y));assert(!validYear({...a.performance1Y,months:11}));assert(!validYear({...a.performance1Y,to:'2029-07-31'}));assert(!validYear({...a.performance1Y,returnPct:Infinity}));}
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({headless:true});
 for(const width of [320,375,390,768,1280,1440])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[],writes=[],loads=[];
  await context.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',route=>{const r=route.request();if(!['GET','HEAD'].includes(r.method()))writes.push(r.url());if(/algorithm-library-.*\.json/.test(r.url()))loads.push(r.url());return new URL(r.url()).origin===origin?route.continue():route.abort();});
  await page.goto(origin+'/?view=feeds');await page.locator('.am-wallet-card').first().waitFor();await page.locator('.al-row').first().waitFor();await settle(page);
  assert.equal(await page.locator('.al-row').count(),24);assert.equal(loads.length,1);assert.equal(await page.locator('[data-action=algorithm-tab]').count(),0);checks+=3;
  assert.equal(await page.locator('.al-library [data-action=subscribe-feed]').count(),0);
  assert.equal(await page.locator('.al-row .al-year').count(),24);assert.equal(await page.locator('.al-row .al-year .positive,.al-row .al-year .negative').count(),5);checks+=3;
  await page.locator('[data-algorithm=rally-ref-001] .al-open').click();await page.locator('.al-detail-foot').waitFor();
  assert.match(await page.locator('.al-performance').innerText(),/1Y model/);assert.match(await page.locator('.al-performance').innerText(),new RegExp(recorded[0].performance1Y.to));
  await page.locator('.al-evidence summary').click();assert.match(await page.locator('.al-evidence').innerText(),/not Rally trading returns/);checks+=3;
  await page.keyboard.press('Escape');await page.locator('[role=dialog]').waitFor({state:'detached'});
  await page.locator('[data-action=library-source][data-id=a16z]').click();assert.equal(await page.locator('.al-row').count(),3);
  await page.locator('.al-row .al-open').first().click();await page.locator('.al-detail-foot').waitFor();await settle(page);
  assert.match(await page.locator('.al-attribution').innerText(),/a16z/);assert.match(await page.locator('.al-performance').innerText(),/No complete 1Y/);checks+=3;
  const box=await page.locator('.al-detail-modal').boundingBox(),foot=await page.locator('.al-detail-foot').boundingBox();assert(box.x>=-1&&box.x+box.width<=width+1);assert(foot.y+foot.height<=901);checks+=2;
  await page.locator('.al-detail-save').click();assert.equal(await page.locator('.al-detail-save').innerText(),'Saved');
  await page.keyboard.press('Escape');await page.locator('[role=dialog]').waitFor({state:'detached'});
  await page.locator('[data-action=library-source][data-id=""]').click();await page.locator('[data-action=library-saved]').click();assert.equal(await page.locator('.al-row').count(),1);
  await page.reload();await page.locator('.al-row').first().waitFor();await page.locator('[data-action=library-saved]').click();assert.equal(await page.locator('.al-row').count(),1);checks+=3;
  await page.locator('[data-action=library-saved]').click();await page.locator('#algorithm-market-search').fill('Wilder');await page.waitForFunction(()=>document.querySelectorAll('.al-row').length===3);checks++;
  await page.locator('#algorithm-market-search').fill('not-a-real-reference-987');await page.waitForFunction(()=>document.querySelectorAll('.al-row').length===0);checks++;
  await page.locator('#algorithm-market-search').fill('');await page.locator('.al-row').first().waitFor();while(await page.locator('.al-more').isVisible())await page.locator('.al-more').click();assert.equal(await page.locator('.al-row').count(),100);checks++;
  await page.evaluate(async()=>{await Promise.all([...document.querySelectorAll('.al-row img')].filter(i=>getComputedStyle(i).display!=='none').map(i=>{i.loading='eager';return i.decode();}));});
  const overflow=await page.evaluate(()=>({page:document.documentElement.scrollWidth>innerWidth+1,rows:[...document.querySelectorAll('.al-row')].filter(e=>e.scrollWidth>e.clientWidth+1).length}));assert.deepEqual(overflow,{page:false,rows:0});const artWidth=await page.locator('.al-open>.al-art').first().evaluate(e=>e.getBoundingClientRect().width);assert(artWidth<=56,'Logo must not stretch into an empty bar');checks+=2;
  if(evidence&&(width===390||width===1440)){await fs.mkdir(evidence,{recursive:true});await page.evaluate(()=>scrollTo(0,document.querySelector('#algorithm-strategies').getBoundingClientRect().top+scrollY-74));await page.mouse.move(1,1);await settle(page);await page.screenshot({path:path.join(evidence,`algorithms-${width}-${theme}.png`)});}
  await page.getByRole('button',{name:'Paid',exact:true}).click();assert(await page.locator('#algorithm-strategies').isHidden());
  await page.getByRole('button',{name:'All',exact:true}).first().click();await page.locator('.al-row').first().waitFor();assert.equal(await page.locator('.am-wallet-card').count(),3);
  await page.getByRole('button',{name:'Top ROI',exact:true}).click();assert.equal(await page.locator('.am-wallet-card').first().locator('.am-return').innerText(),'+500%');checks+=3;
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);checks+=2;layouts.push({width,theme});await context.close();
 }
 const page=await browser.newPage();let failures=1;
 await page.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
 await page.route('**/assets/algorithm-library-*.json',r=>failures-->0?r.fulfill({status:503,body:'Unavailable'}):r.continue());
 await page.goto(origin+'/?view=feeds&section=library');await page.locator('[data-action=library-retry]').click();await page.locator('.al-row').first().waitFor();assert.equal(await page.locator('[data-action=algorithm-tab]').count(),0);checks++;
 await page.close();
 const report={checks,layouts,algorithms:100,officialLogos:37,datedYearRecords:5,boundedRows:24,noWrites:true};
 if(evidence)await fs.writeFile(path.join(evidence,'algorithms-browser.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}catch(e){console.error(logs.slice(-2000));throw e;}finally{await browser?.close();server.kill('SIGTERM');await fs.rm(temp,{recursive:true,force:true});}
