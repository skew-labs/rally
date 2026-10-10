// Disposable account + real bridge handlers; market inputs are explicit QA fixtures.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash,randomBytes} from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('..',import.meta.url)),port='33213',origin='http://127.0.0.1:'+port;
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'rally-native-perp-')),fixture=path.join(temp,'fixture.json');
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{cwd:root,env:{...process.env,RALLY_TESTING:'1',RALLY_PREVIEW_PORT:port,RALLY_FIXTURE_FILE:fixture},stdio:['ignore','ignore','pipe']});let diagnostics='';server.stderr.on('data',v=>diagnostics+=v.toString());let browser,checks=0;
try {
 let data;for(let i=0;i<100;i++){try{data=JSON.parse(await fs.readFile(fixture));if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}assert(data,diagnostics);
 browser=await chromium.launch({headless:true,...(process.env.RALLY_CHROME_PATH?{executablePath:process.env.RALLY_CHROME_PATH}:{})});
 const write=async(path,body)=>{const r=await fetch(origin+path,{method:'POST',headers:{'Content-Type':'application/json','X-Rally-Request':'1'},body:JSON.stringify(body)});const result=await r.json();assert(r.ok,JSON.stringify(result));return result;};
 const verifier=randomBytes(32).toString('base64url'),challenge=createHash('sha256').update(verifier).digest('base64url'),request=await write('/api/native/start',{challenge});
 const auth=await browser.newContext({userAgent:'Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/141.0.0.0 Mobile Safari/537.36'});
 await auth.addCookies([{name:'rally_session',value:data.cookie,url:origin}]);const p=await auth.newPage();
 p.on('pageerror',e=>console.error('Bridge error:',e.message));p.on('requestfailed',r=>console.error('Bridge load:',r.url(),r.failure()?.errorText));p.on('console',m=>{if(m.type()==='error')console.error('Bridge console:',m.text());});
 await auth.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
 await p.goto(request.url);try{await p.locator('[data-native-approve]').click({timeout:10000});}catch(e){console.error('Bridge page:',await p.locator('body').innerText());throw e;}await p.locator('.r-native-pair h2').filter({hasText:'Connection approved'}).waitFor();
 const link=await p.locator('.r-native-pair a').getAttribute('href');assert(link.startsWith('intent://account?nativeRequest='+request.id));assert(link.includes('package=com.rallydot.app'));assert(!link.includes(verifier));checks+=3;
 const claim=await write('/api/native/poll',{id:request.id,verifier}),retry=await write('/api/native/poll',{id:request.id,verifier});assert.equal(retry.session,claim.session);checks++;
 const boot=await (await fetch(origin+'/api/bootstrap?markets=0',{headers:{Cookie:'rally_session='+claim.session}})).json();assert(boot.me);checks++;
 await auth.close();
 for(const width of [320,390,768,1440])for(const theme of ['light','dark']) {
  const context=await browser.newContext({viewport:{width,height:800},reducedMotion:width===320?'reduce':'no-preference'}),page=await context.newPage(),errors=[];
  await context.addCookies([{name:'rally_session',value:data.cookie,url:origin}]);await context.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);page.on('pageerror',e=>errors.push(e.message));
  const market={id:7,venue:'Perpl',symbol:'BTC',open:true,stale:false,mark:60000,priceDecimals:2,lotDecimals:5,execution:'wallet_transactions'};
  await context.route('**/*',route=>{const url=new URL(route.request().url());if(url.origin!==origin)return route.abort();if(url.pathname==='/api/perps')return route.fulfill({contentType:'application/json',body:JSON.stringify({fetchedAt:Date.now()/1000,markets:[market]})});if(['/api/execution/','/api/quotes','/api/payments/','/api/orders'].some(x=>url.pathname.startsWith(x)))throw Error('Financial submission blocked in UI test');return route.continue();});
  await page.goto(origin+'/?view=post&post='+data.perpl);await page.locator('.rl-fill').waitFor();await page.locator('.rl-fill [data-action=perpl-order]').click();await page.locator('.r-perp-amount input').waitFor();
  const input=page.locator('.r-perp-amount input'),buy=page.locator('#perpl-order-form [type=submit]');assert(await buy.isDisabled());checks++;
  await input.fill('0.3');assert.equal(await page.locator('.r-perp-equivalent').innerText(),'≈ $18,000.00');assert.equal(await page.locator('input[name=quantity]').inputValue(),'0.3');assert(await buy.isEnabled());checks+=3;
  await page.locator('[data-amount-mode=usd]').click();assert.equal(await input.inputValue(),'18000');checks++;
  await input.fill('10');assert.match(await page.locator('.r-perp-equivalent').innerText(),/0.00016 BTC/);assert.equal(await page.locator('input[name=quantity]').inputValue(),'0.00016');checks+=2;
  const d=await page.locator('#perpl-order-form').evaluate(f=>Object.fromEntries(new FormData(f)));assert.equal(d.quantity,'0.00016');assert(!('amountMode' in d));assert(!('usd' in d));checks+=3;
  await page.locator('.r-ticket-leverage input').evaluate(e=>{e.value='4';e.dispatchEvent(new Event('input',{bubbles:true}));});assert.equal(await page.locator('[data-margin]').innerText(),'1.92 AUSD');checks++;
  await page.locator('.r-order-directions label').filter({hasText:'Sell / Short'}).click();assert.match(await buy.innerText(),/Sell \/ Short/);assert.equal(await input.inputValue(),'10');checks+=2;
  await input.fill('0.001');assert(await buy.isDisabled());checks++;
  await input.fill('10');assert(await buy.isEnabled());checks++;
  const shortcut=page.locator('[data-position-preset="25"]');await shortcut.click();assert.equal(await input.inputValue(),'25');assert.equal(await page.locator('input[name=quantity]').inputValue(),'0.00041');assert.equal(await shortcut.getAttribute('aria-pressed'),'true');assert(await shortcut.evaluate(e=>document.activeElement===e));checks+=4;
  await page.locator('[data-position-preset="10"]').click();
  await page.locator('#perpl-order-form').evaluate(f=>f.dataset.pending='true');await page.waitForTimeout(30);assert(await shortcut.isDisabled());await shortcut.evaluate(e=>e.click());assert.equal(await input.inputValue(),'10');checks+=2;
  await page.locator('#perpl-order-form').evaluate(f=>f.dataset.pending='false');await page.waitForTimeout(30);assert(await buy.isEnabled());checks++;
  const fit=await page.locator('.r-modal').evaluate(el=>{const r=el.getBoundingClientRect();const b=el.querySelector('[type=submit]').getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1&&b.top>=0&&b.bottom<=innerHeight+1&&document.documentElement.scrollWidth<=innerWidth+1;});assert(fit,`${width} ${theme} overflow`);assert.deepEqual(errors,[]);checks+=2;
  if(width===390&&process.env.RALLY_EVIDENCE_DIR){await page.waitForTimeout(250);await fs.writeFile(path.join(process.env.RALLY_EVIDENCE_DIR,'perp-input-'+theme+'.json'),JSON.stringify(await input.evaluate(e=>{const s=getComputedStyle(e);return {value:e.value,type:e.type,color:s.color,font:s.font,fontSize:s.fontSize,lineHeight:s.lineHeight,fontFamily:s.fontFamily,textIndent:s.textIndent,textFill:s.webkitTextFillColor,clipPath:s.clipPath,transform:s.transform,opacity:s.opacity,visibility:s.visibility,scroll:e.scrollLeft,rect:e.getBoundingClientRect().toJSON()};})));await page.screenshot({path:path.join(process.env.RALLY_EVIDENCE_DIR,'perp-web-'+theme+'.png')});}
  if(width<=390){await input.focus();await page.setViewportSize({width,height:430});await page.waitForTimeout(100);assert(await buy.evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight+1;}));checks++;}
  await context.close();
 }
 console.log(JSON.stringify({checks,viewports:4,themes:2,accountBridge:true,sessionRecovery:true,providerCalls:0,walletSignatures:0,financialTransactions:0}));
}finally {await browser?.close();server.kill('SIGTERM');await fs.rm(temp,{recursive:true,force:true});}
