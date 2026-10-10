// Real reaction handlers against a disposable database; no owner sessions or trades.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('..',import.meta.url)),port='33215',origin='http://127.0.0.1:'+port;
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'rally-experience-')),fixture=path.join(temp,'fixture.json');
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{cwd:root,env:{...process.env,RALLY_TESTING:'1',RALLY_PREVIEW_PORT:port,RALLY_FIXTURE_FILE:fixture},stdio:['ignore','ignore','pipe']});
let diagnostics='',browser,checks=0;server.stderr.on('data',v=>diagnostics+=v);
try {
 let data;for(let i=0;i<100;i++){try{data=JSON.parse(await fs.readFile(fixture));if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}assert(data,diagnostics);
 browser=await chromium.launch({headless:true,...(process.env.RALLY_CHROME_PATH?{executablePath:process.env.RALLY_CHROME_PATH}:{})});
 for(const theme of ['light','dark']) {
  for(const kind of ['like','save'])assert((await fetch(origin+'/api/reaction',{method:'POST',headers:{Cookie:'rally_session='+data.cookie,'Content-Type':'application/json','X-Rally-Request':'1'},body:JSON.stringify({post:data.signal,kind,active:false})})).ok);
  const context=await browser.newContext({viewport:{width:360,height:820},reducedMotion:theme==='dark'?'reduce':'no-preference'}),page=await context.newPage(),errors=[];
  await context.addCookies([{name:'rally_session',value:data.cookie,url:origin}]);await context.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);page.on('pageerror',e=>errors.push(e.message));
  const pending=new Map(),requests=[];let fail=false;
  const queued=async condition=>{for(let i=0;i<250;i++){if(condition())return;await page.waitForTimeout(20);}assert(condition(),'Reaction did not reach the QA response gate');};
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());if(url.origin!==origin)return route.abort();
   if(['/api/execution/','/api/quotes','/api/payments/','/api/orders'].some(x=>url.pathname.startsWith(x)))throw Error('Financial submission blocked');
   if(url.pathname!=='/api/reaction')return route.continue();
   const body=request.postDataJSON();requests.push(body.kind);
   if(fail)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'QA temporary outage'})});
   const response=await route.fetch(),result=await response.json();
   // An independently returned reaction can contain stale fields for the other kind.
   if(body.kind==='like')result.saved=false;else {result.liked=false;result.likes=0;}
   await new Promise(resolve=>pending.set(body.kind,resolve));pending.delete(body.kind);
   await route.fulfill({response,body:JSON.stringify(result)});
  });
  await page.goto(origin+'/?view=post&id='+data.signal);const article=page.locator(`[data-post="${data.signal}"]`),like=article.locator('[data-action=like]'),save=article.locator('[data-action=save]');await like.waitFor();
  await article.evaluate(el=>{window.qaArticle=el;window.qaBody=el.querySelector('.r-post-body');});
  await like.click();await page.waitForFunction(()=>document.querySelector('[data-action=like]').getAttribute('aria-busy')==='true');
  assert(await like.isDisabled());assert.equal(await like.getAttribute('aria-pressed'),'true');assert.equal(await like.locator('span').innerText(),'1');checks+=3;
  await like.evaluate(el=>el.dispatchEvent(new MouseEvent('click',{bubbles:true})));await save.click();
  await page.waitForFunction(()=>document.querySelector('[data-action=save]').getAttribute('aria-busy')==='true');
  await queued(()=>pending.size===2);
  assert.deepEqual(requests,['like','save']);assert.equal(await save.getAttribute('aria-pressed'),'true');checks+=2;
  pending.get('save')();await page.waitForFunction(()=>document.querySelector('[data-action=save]').getAttribute('aria-busy')==='false');
  pending.get('like')();await page.waitForFunction(()=>document.querySelector('[data-action=like]').getAttribute('aria-busy')==='false');
  assert.equal(await save.getAttribute('aria-pressed'),'true');assert.equal(await like.getAttribute('aria-pressed'),'true');checks+=2;
  assert(await article.evaluate(el=>el===window.qaArticle && el.querySelector('.r-post-body')===window.qaBody));checks++;
  fail=true;await like.click();await page.waitForFunction(()=>document.querySelector('[data-action=like]').getAttribute('aria-busy')==='false');
  assert.equal(await like.getAttribute('aria-pressed'),'true');assert.equal(await like.locator('span').innerText(),'1');assert(!(await like.isDisabled()));assert(await article.evaluate(el=>el===window.qaArticle));checks+=4;
  fail=false;await like.click();await queued(()=>pending.has('like'));pending.get('like')();await page.waitForFunction(()=>document.querySelector('[data-action=like]').getAttribute('aria-busy')==='false');
  assert.equal(await like.getAttribute('aria-pressed'),'false');assert.equal(await like.locator('span').innerText(),'');assert.equal(await save.getAttribute('aria-pressed'),'true');checks+=3;
  assert(await like.evaluate(el=>{const r=el.getBoundingClientRect();return r.height>=44&&r.width>=44;}));assert.deepEqual(errors,[]);checks+=2;
  await page.goto(origin+'/?view=home&section=feed');await page.locator('.r-post').first().waitFor();
  const geometry=await page.evaluate(()=>({post:document.querySelector('.r-post').getBoundingClientRect().top,strip:getComputedStyle(document.querySelector('.r-market-strip')).display,width:document.documentElement.scrollWidth}));
  assert(geometry.post<510,JSON.stringify(geometry));assert.equal(geometry.strip,'none');assert(geometry.width<=361);checks+=3;
  if(process.env.RALLY_EVIDENCE_DIR)await page.screenshot({path:path.join(process.env.RALLY_EVIDENCE_DIR,'feed-after-'+theme+'.png')});
  await context.close();
 }
 console.log(JSON.stringify({checks,themes:2,optimisticFeedback:true,duplicateRequestsBlocked:true,concurrentReactions:true,errorRollback:true,readingDOMPreserved:true,financialTransactions:0,walletSignatures:0}));
}finally{await browser?.close();server.kill('SIGTERM');await fs.rm(temp,{recursive:true,force:true});}
