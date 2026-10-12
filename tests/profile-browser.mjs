import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33227';
const out=process.env.RALLY_EVIDENCE||'/tmp/rally-profile';await fs.mkdir(out,{recursive:true});
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{cwd:root,env:{...process.env,RALLY_PREVIEW_PORT:'33227'},stdio:'ignore'});
let browser,checks=0;const pause=ms=>new Promise(r=>setTimeout(r,ms));
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await pause(100);}
 browser=await chromium.launch();
 for(const width of [320,390,768,1440])for(const theme of ['light','dark']){
  const c=await browser.newContext({viewport:{width,height:850}}),p=await c.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  await c.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);
  const handle=`qa_${width}_${theme}`;
  const registration=await p.request.post(origin+'/api/auth/register',{data:{handle,name:'Original Name',password:'QA-only-profile-password'},headers:{'X-Rally-Request':'1'}});assert.equal(registration.status(),201);
  await p.goto(origin+'/?view=account');await p.getByRole('button',{name:'Edit profile',exact:true}).click();
  await p.locator('[name=handle]').fill('rally');await p.getByRole('button',{name:'Save changes'}).click();
  await p.locator('.r-form-error').filter({hasText:'That username is taken'}).waitFor();assert.equal(await p.locator('[name=name]').inputValue(),'Original Name');checks++;
  await p.locator('[name=handle]').fill(handle+'_new');await p.locator('[name=name]').fill('New Name');await p.locator('[name=bio]').fill('Saved on web and Android');
  const image=await p.evaluate(()=>{const c=document.createElement('canvas');c.width=900;c.height=600;const x=c.getContext('2d');x.fillStyle='#7963ef';x.fillRect(0,0,900,600);return c.toDataURL('image/png').split(',')[1];});
  await p.locator('#profile-photo').setInputFiles({name:'avatar.png',mimeType:'image/png',buffer:Buffer.from(image,'base64')});
  await p.screenshot({path:`${out}/profile-edit-${width}-${theme}.png`});
  // A successful save must not depend on another bootstrap or any market read.
  await p.route('**/api/bootstrap*',r=>r.fulfill({status:503,json:{message:'QA bootstrap unavailable'}}));
  let saves=0;p.on('request',r=>{if(new URL(r.url()).pathname==='/api/profile'&&r.method()==='POST')saves++;});
  await p.getByRole('button',{name:'Save changes'}).click();await p.locator('#profile-form').waitFor({state:'detached'});
  await p.locator('.r-account-identity h2').filter({hasText:'New Name'}).waitFor();assert.equal(saves,1);checks++;
  const identity=await p.request.get(origin+'/api/bootstrap?markets=0').then(r=>r.json());assert.equal(identity.me.name,'New Name');assert.equal(identity.me.handle,handle+'_new');assert.match(identity.me.avatar,/^\/media\/[a-f0-9]{32}$/);checks++;
  const anonymous=await browser.newContext();assert.equal((await anonymous.request.get(origin+identity.me.avatar)).status(),200);await anonymous.close();checks++;
  await p.unroute('**/api/bootstrap*');await p.reload();await p.locator('.r-account-identity h2').filter({hasText:'New Name'}).waitFor();checks++;
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(errors,[]);checks++;
  await p.locator('.r-account-identity img.is-loaded').waitFor();assert(await p.locator('.r-account-identity img').evaluate(i=>i.naturalWidth===512));checks++;await p.screenshot({path:`${out}/profile-${width}-${theme}.png`});
  await p.getByRole('button',{name:'Edit profile',exact:true}).click();await p.getByRole('button',{name:'Remove',exact:true}).click();await p.getByRole('button',{name:'Save changes'}).click();await p.locator('#profile-form').waitFor({state:'detached'});assert.equal((await p.request.get(origin+'/api/bootstrap?markets=0').then(r=>r.json())).me.avatar,'');checks++;
  await c.close();
 }
 console.log(JSON.stringify({checks,viewports:4,themes:2,canonicalSave:true,photoUploadAndPublicRead:true,duplicateHandleErrorVisible:true,bootstrapFailureIndependent:true,walletActions:0}));
}finally{await browser?.close();server.kill('SIGTERM');}
