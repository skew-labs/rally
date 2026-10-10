// Actual account/feature handlers in temporary state. No live provider, wallet or funds.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('..',import.meta.url)),port=process.env.RALLY_PREVIEW_PORT||'33211',origin='http://127.0.0.1:'+port;
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'rally-social-loop-ui-')),fixture=path.join(temp,'fixture.json');
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{cwd:root,env:{...process.env,RALLY_TESTING:'1',RALLY_PREVIEW_PORT:port,RALLY_FIXTURE_FILE:fixture},stdio:['ignore','ignore','pipe']});let diagnostics='';server.stderr.on('data',v=>diagnostics+=v.toString());let browser,checks=0;
try{
 let data;for(let i=0;i<120;i++){if(server.exitCode!==null)throw Error(diagnostics);try{data=JSON.parse(await fs.readFile(fixture));if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}assert(data,'Fixture unavailable');
 browser=await chromium.launch({headless:true,...(process.env.RALLY_CHROME_PATH?{executablePath:process.env.RALLY_CHROME_PATH}:{})});
 for(const width of [360,390,768,1440])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[];
  await context.addCookies([{name:'rally_session',value:data.cookie,url:origin}]);await context.addInitScript(value=>localStorage.setItem('rally-theme',value),theme);
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',route=>{const url=new URL(route.request().url());if(url.origin!==origin&& !['data:','blob:'].includes(url.protocol))return route.abort();if(['/api/execution/','/api/payments/','/api/auth/wallet/','/api/quotes','/api/orders'].some(p=>url.pathname.startsWith(p)))throw Error('Financial request in UI test');return route.continue();});
  const fit=async(label)=>{assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Overflow '+label);assert.deepEqual(errors,[],label);const modal=page.locator('.r-modal');if(await modal.count()){const b=await modal.boundingBox();assert(b.x>=-1&&b.x+b.width<=width+1,'Modal overflow '+label);}checks+=2;};
  await page.goto(origin+'/?view=post&id='+data.signal);await page.locator('.rl-signal').waitFor();assert.match(await page.locator('.rl-signal').innerText(),/Target/);checks++;await fit('signal');
  await page.locator('[data-action=signal-details]').click();await page.locator('.r-modal .rl-signal').waitFor();await fit('signal details');await page.locator('[data-action=close-modal]').click();
  await page.goto(origin+'/?view=account');await page.locator('[data-action=benefits-open]').first().click();await page.locator('.rl-tier').waitFor();await fit('benefits');
  await page.locator('[data-action=benefits-edit]').click();await page.locator('#rl-benefits-form').waitFor();await page.locator('[name=label-0]').fill('Holder');await page.locator('#rl-benefits-form [type=submit]').click();await page.locator('.rl-tier').waitFor();assert.match(await page.locator('.rl-tier').innerText(),/Holder/);checks++;await fit('benefits save');await page.locator('[data-action=close-modal]').click();
  await page.locator('[data-action=push-settings]').click();await page.locator('.rl-settings').waitFor();assert.match(await page.locator('.rl-settings').innerText(),/Firebase/);checks++;await fit('push settings');await page.locator('[data-action=market-alert-settings]').click();await page.locator('[data-alert]').check();await page.waitForFunction(async()=>{const r=await fetch('/api/market-alerts');return (await r.json()).alerts.some(x=>x.enabled)});checks++;await fit('market alerts');await page.locator('[data-action=close-modal]').click();
  await page.goto(origin+'/?view=leaderboard');await page.locator('[data-action=weekly-league]').click();await page.locator('.rl-league').waitFor();await page.locator('[data-action=league-enroll]').click();await page.locator('.rl-league-row').waitFor();assert.match(await page.locator('.rl-league-row').innerText(),/pending/);checks++;await fit('weekly league');await page.locator('[data-action=close-modal]').click();
  await page.goto(origin+'/?view=home&section=feed');await page.locator('[data-action=mode][data-id=trades]').click();await page.locator('.rl-fill').waitFor();assert.match(await page.locator('.rl-fill').innerText(),/1 TEST/);checks++;await fit('following fill');
  // Publish through the actual composer and keep immutable entry terms.
  if(width===390&&theme==='light'){await page.locator('button[data-action=compose]:visible').first().click();await page.locator('#compose-form').waitFor();await page.locator('[name=text]').fill('QA composer signal; temporary state only.');await page.locator('[name=asset]').selectOption(data.token);await page.locator('.rl-signal-form summary').click();await page.locator('[name=signalEnabled]').check();await page.locator('[name=signalTarget]').fill('0.02');await page.locator('[name=signalStop]').fill('0.005');await page.locator('#compose-form [type=submit]').click();await page.locator('#page .rl-signal').waitFor();assert.match(await page.locator('#page .rl-signal').innerText(),/At publication/);checks++;await fit('composer publication');}
  if(width===390&&theme==='light'){
   await page.route('**/api/perps',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({fetchedAt:Date.now()/1000,markets:[{id:7,venue:'Perpl',symbol:'QA BTC',open:true,stale:false,mark:63000,priceDecimals:2,lotDecimals:3}]})}));
   await page.goto(origin+'/?view=post&post='+data.perpl);await page.locator('.rl-fill').waitFor();await page.locator('.rl-fill [data-action=perpl-order]').click();await page.locator('#perpl-order-form').waitFor();assert.match(await page.locator('.r-modal').innerText(),/QA BTC perpetual/);checks++;await fit('shared Perpl cold start');await page.locator('[data-action=close-modal]').click();
  }
  // A context transition must not itself send a trade.
  await page.goto(origin+'/?view=post&post='+data.trade);await page.locator('.rl-fill').waitFor();await fit('notification deep link');
  const output=process.env.RALLY_EVIDENCE_DIR;if(output&&width===390){await page.waitForTimeout(300);await page.screenshot({path:path.join(output,'social-loop-'+theme+'.png'),fullPage:false});}
  await context.close();
 }
 console.log(JSON.stringify({checks,viewports:4,themes:2,providerCalls:0,walletRequests:0,financialTransactions:0}));
}finally{await browser?.close();server.kill('SIGTERM');await fs.rm(temp,{recursive:true,force:true});}
