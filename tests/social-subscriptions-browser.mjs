// Real page handlers with disposable subscriptions; all financial writes blocked.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('..',import.meta.url)),port='33318',origin='http://127.0.0.1:'+port;
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'rally-subscriptions-')),fixture=path.join(temp,'fixture.json');
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{cwd:root,env:{...process.env,RALLY_TESTING:'1',RALLY_SOCIAL_DISCOVERY_FIXTURE:'1',RALLY_PREVIEW_PORT:port,RALLY_FIXTURE_FILE:fixture},stdio:['ignore','ignore','pipe']});
let diagnostics='',browser;const results=[];server.stderr.on('data',d=>diagnostics+=d);
try{
 let data;for(let i=0;i<150;i++){try{data=JSON.parse(await fs.readFile(fixture));if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}assert(data,diagnostics);
 browser=await chromium.launch();
 for(const width of [320,390,768,1440])for(const theme of ['light','dark']){
  const ctx=await browser.newContext({viewport:{width,height:844},reducedMotion:theme==='dark'?'reduce':'no-preference'}),page=await ctx.newPage(),errors=[],writes=[];
  await ctx.addCookies([{name:'rally_session',value:data.cookie,url:origin}]);await ctx.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==origin)return route.abort();if(req.method()!=='GET' && req.method()!=='HEAD'){writes.push(u.pathname);return route.abort();}return route.continue();});
  const fit=async name=>{await page.evaluate(async()=>{await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),name+' horizontal overflow');if(process.env.RALLY_EVIDENCE_DIR)await page.screenshot({path:path.join(process.env.RALLY_EVIDENCE_DIR,`${name}-${width}-${theme}.png`)});};
  await page.goto(origin+'/?view=communities');await page.locator('#timeline .rd-comment').first().waitFor();assert.equal(await page.locator('.rs-community-head h1').innerText(),'Community');
  await fit('community');await page.locator('.rd-creator-token').first().waitFor();
  await page.locator('#timeline [data-action=profile][data-id=reader]').first().click();await page.locator('.r-profile-banner').waitFor();await page.locator('.rs-profile-subscribe').waitFor();await fit('creator');
  await page.locator('.rs-profile-subscribe').click();await page.locator('.am-preview-modal .rs-allocation').waitFor();await page.waitForFunction(()=>!document.querySelector('.am-preview-foot button')?.disabled);assert.match(await page.locator('.am-preview-modal').innerText(),/20% buyback allocation/);assert.match(await page.locator('.am-preview-foot').innerText(),/Subscribe · 2.5 USDC/);await fit('subscription');
  await page.goto(origin+'/?view=leaderboard');await page.locator('.rs-leader-row').first().waitFor();assert.match(await page.locator('#leader-results').innerText(),/2.5 USDC \/ 30d/);await fit('leaderboard');
  await page.locator('[data-action=creator-offers][data-id=reader]').click();await page.locator('.am-preview-modal .rs-allocation').waitFor();
  await page.goto(origin+'/?view=discover');await page.locator('.rs-token-row').first().waitFor();assert.equal(await page.locator('.rs-token-open b').first().innerText(),'QA0');await fit('search');
  await page.locator('[data-action=token-search-more]').click();await page.waitForFunction(()=>document.querySelectorAll('.rs-token-row').length===80);assert.equal(await page.locator('.rs-token-row').count(),80);
  await page.locator('#token-search').fill('QA84');await page.waitForFunction(()=>document.querySelectorAll('.rs-token-row').length===1&&document.querySelector('.rs-token-open b').textContent==='QA84');
  await page.locator('[data-action=token-search-clear]').click();await page.waitForFunction(()=>document.querySelectorAll('.rs-token-row').length===40);await page.locator('[data-action=token-search-sort][data-id=volume]').click();await page.waitForFunction(()=>document.querySelector('.rs-token-open b').textContent==='QA84');
  await page.goto(origin+'/?view=home&section=markets&tab=spot');await page.locator('#home-overview').waitFor();await page.locator('.r-spot-table tbody tr').first().waitFor();await fit('home');
  await page.goto(origin+'/?view=swipe&market=spot');await page.locator('.r-swipe-card[data-active]').waitFor();await fit('swipe');
  assert(await page.locator('.r-swipe-tabs').evaluate(el=>[...el.querySelectorAll('button')].every(b=>{const r=b.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.width>40;})),'Swipe filters fit');
  await page.locator('#swipe-deck').focus();await page.keyboard.press('ArrowDown');await page.waitForFunction(()=>document.querySelector('.r-swipe-card[data-active]')?.dataset.swipeIndex==='1');
  await page.locator('[data-action=swipe-tab][data-id=algorithms]').click();await page.locator('.sa-card[data-active]').waitFor();await fit('swipe-subscriptions');
  assert.deepEqual(errors,[],errors.join('\n'));assert.deepEqual(writes,[]);results.push({width,theme,communityToCreator:true,subscriptionTerms:true,rankingPlans:true,searchSortAndPaging:true,overflow:false,writes:0});await ctx.close();
 }
 if(process.env.RALLY_EVIDENCE_DIR)await fs.writeFile(path.join(process.env.RALLY_EVIDENCE_DIR,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser?.close();server.kill('SIGTERM');await fs.rm(temp,{recursive:true,force:true});if(!results.length)console.error(diagnostics.slice(-3000));}
