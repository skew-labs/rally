// Real form and keyboard journeys with disposable accounts; no wallet or provider calls.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {chromium} from 'playwright';
const origin='http://127.0.0.1:33216',out=process.env.RALLY_EVIDENCE||'/tmp/rally-identity-picker';
await fs.mkdir(out,{recursive:true});
const fixture=out+'/fixture.json';
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{env:{...process.env,RALLY_TESTING:'1',RALLY_PREVIEW_PORT:'33216',RALLY_FIXTURE_FILE:fixture},stdio:'ignore'});
let browser;const results=[];
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 const cookie=JSON.parse(await fs.readFile(fixture,'utf8')).cookie;
 browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 for(const width of [320,390,768,1440])for(const theme of ['light','dark']){
  const ctx=await browser.newContext({viewport:{width,height:900},colorScheme:theme,reducedMotion:theme==='dark'?'reduce':'no-preference'});
  await ctx.addCookies([{name:'rally_session',value:cookie,url:origin}]);
  await ctx.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);
  const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.stack));
  const agent={id:'qa-agent',kind:'agent',owner:'creator',name:'Codex research with a very long display name',handle:'qa_codex',avatar:'/assets/agent-openai.svg'};
  await page.route('**/api/bootstrap*',async route=>{const response=await route.fetch(),data=await response.json();data.people.push(agent);await route.fulfill({response,json:data});});
  let payload;
  await page.route('**/api/connections',async route=>{
   if(route.request().method()!=='POST')return route.continue();
   payload=route.request().postDataJSON();await route.fulfill({status:400,json:{error:'qa_capture',message:'QA submission captured'}});
  });
  await page.goto(origin+'/?view=agents',{waitUntil:'domcontentloaded'});
  await page.locator('.r-page-head [data-action=connect-agent]').count().then(async count=>{await (count?page.locator('.r-page-head [data-action=connect-agent]'):page.locator('#page [data-action=connect-agent]').first()).click()});
  const trigger=page.locator('#agent-form .ri-trigger'),list=page.locator('#agent-form [role=listbox]');
  await trigger.click();await page.getByRole('option',{name:'Codex OpenAI'}).click();
  assert.equal(await page.locator('#agent-provider').inputValue(),'codex');
  assert.equal(await page.locator('#agent-form [name=name]').inputValue(),'Codex');
  assert.equal(await trigger.getAttribute('aria-expanded'),'false');
  await page.locator('#agent-form [name=name]').fill('My research agent');
  await trigger.focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('c');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
  assert.equal(await page.locator('#agent-provider').inputValue(),'claude');
  assert.equal(await page.locator('#agent-form [name=name]').inputValue(),'My research agent');
  await trigger.click();await page.keyboard.press('Escape');assert.equal(await list.isVisible(),false);assert.equal(await page.locator('#agent-form').count(),1);
  await trigger.click();await page.keyboard.press('Home');await page.keyboard.press('Enter');assert.equal(await page.locator('#agent-provider').inputValue(),'');
  await trigger.click();await page.getByRole('option',{name:'Hermes Nous Research'}).click();
  await page.locator('#agent-form [name=handle]').fill('qa_picker');
  await page.locator('#agent-form [value="posts:write"]').uncheck();
  await page.locator('#agent-form [type=submit]').click();await page.getByRole('alert').filter({hasText:'QA submission captured'}).waitFor();
  assert.equal(payload.provider,'hermes');assert.equal(payload.name,'My research agent');assert(!payload.scopes.includes('posts:write'));assert.equal(payload.scopes.length,4);
  await trigger.click();await page.keyboard.press('Home');
  const geometry=await list.evaluate(e=>({overflow:document.documentElement.scrollWidth>innerWidth+1,rows:[...e.children].map(row=>{const r=row.getBoundingClientRect();return{left:r.left,right:r.right,height:r.height}})}));
  assert(!geometry.overflow);assert(geometry.rows.every(r=>r.left>=0&&r.right<=width&&r.height>=44));
  const logos=await list.locator('img').evaluateAll(images=>Promise.all(images.map(async image=>{await image.decode().catch(()=>{});return image.naturalWidth>0})));
  assert(logos.every(Boolean));
  await page.screenshot({animations:'disabled',path:out+`/agents-${width}-${theme}.png`});
  await page.keyboard.press('Escape');await page.getByRole('button',{name:'Close dialog',exact:true}).click();
  await page.route('**/api/launchpad/me',async route=>{await new Promise(r=>setTimeout(r,100));await route.fulfill({json:{identities:[{id:'creator',name:'QA creator',handle:'creator',kind:'person',avatar:'/assets/community-rally.png'},agent]}})});
  await page.goto(origin+'/?view=launch');const creator=page.locator('#lp-create-form .ri-trigger');await creator.waitFor();
  await page.waitForFunction(()=>document.querySelector('select[name=identity]')?.options.length===2);
  await creator.click();await page.getByRole('option',{name:/Codex research/}).click();
  assert.equal(await page.locator('select[name=identity]').inputValue(),'qa-agent');
  assert.match(await page.locator('#lp-preview-creator').textContent(),/Codex research/);
  assert.equal(await page.locator('#lp-create-form').evaluate(f=>new FormData(f).get('identity')),'qa-agent');
  await creator.click();await page.locator('#lp-create-form [role=option]').first().waitFor();
  const creatorImages=await page.locator('#lp-create-form .ri-picker img').evaluateAll(async images=>{await Promise.all(images.map(image=>image.decode().catch(()=>{})));await new Promise(r=>setTimeout(r,50));return images.map(image=>({src:image.getAttribute('src'),loaded:image.naturalWidth>0,opacity:getComputedStyle(image).opacity,cls:image.className,hidden:image.closest('[hidden]')!==null}));});
  assert(creatorImages.filter(image=>!image.hidden).every(image=>image.loaded&&image.opacity==='1')); 
  await page.screenshot({animations:'disabled',path:out+`/creator-${width}-${theme}.png`});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.keyboard.press('Escape');await page.locator('[data-action=lp-register]').click();
  await page.locator('#lp-register-form .ri-trigger').click();await page.getByRole('option',{name:/Codex research/}).click();
  assert.equal(await page.locator('#lp-register-form').evaluate(f=>new FormData(f).get('identity')),'qa-agent');
  assert.deepEqual(errors,[]);results.push({width,theme,logos:true,keyboard:true,formIdentity:true,customNamePreserved:true,permissionsPreserved:true,financialActions:0});await ctx.close();
 }
 await fs.writeFile(out+'/results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser?.close();server.kill();}
