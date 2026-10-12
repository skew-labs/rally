// Disposable authenticated UI fixtures. No wallets, launches or financial calls.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('..',import.meta.url));
const origin='http://127.0.0.1:33229',out=process.env.RALLY_EVIDENCE||'/tmp/rally-profile-launch-layout';
await fs.mkdir(out,{recursive:true});
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{cwd:root,env:{...process.env,RALLY_PREVIEW_PORT:'33229'},stdio:'ignore'});
const settle=p=>p.evaluate(async()=>{await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})))});
const bounds=async(locator)=>locator.evaluate(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height};});
let browser;const results=[];
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch();
 const fixture=await browser.newContext();
 const registration=await fixture.request.post(origin+'/api/auth/register',{data:{handle:'layout_fixture',name:'Layout fixture',password:'QA-only-profile-password'},headers:{'X-Rally-Request':'1'}});
 assert.equal(registration.status(),201);const storageState=await fixture.storageState();await fixture.close();
 for(const width of [320,360,390,600,768,1024,1440])for(const theme of ['light','dark']){
  const c=await browser.newContext({storageState,viewport:{width,height:900},reducedMotion:theme==='dark'?'reduce':'no-preference'}),p=await c.newPage(),errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  await c.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);
  await p.route('**/api/bootstrap*',async r=>{const response=await r.fetch(),d=await response.json();
   d.me.name='AReallyLongProfileNameWithoutSpacesForLayoutCheck';d.me.handle='a_very_long_profile_name';d.me.bio='A longer biography stays readable without pushing the photo and Edit profile button apart.';
   const t={name:'Rally Community',symbol:'RALLY',address:'0x0000000000000000000000000000000000000001',owner:d.me.id,community:'qa-layout-community',logoURI:'/assets/MON.png',buybackBps:8000,burnBps:10000,stats:{},verifiedAt:1};
   d.communityToken={token:t};d.communities.push({id:t.community,name:t.name,members:1,joined:true,token:t});d.passwordAccount=true;
   await r.fulfill({response,json:d});
  });
  await p.route('**/api/launchpad/tokens?*',r=>r.fulfill({json:{tokens:[],communityTokens:[],total:0}}));
  await p.goto(origin+'/?view=account');await p.locator('.r-account-identity').waitFor();await settle(p);
  const identity=await p.locator('.r-account-identity').evaluate(e=>{
   const title=e.querySelector('h2'),bio=e.querySelector('.r-account-bio'),photo=e.querySelector('.r-avatar'),button=e.querySelector('button');
   return {titleHeight:title.getBoundingClientRect().height,lineHeight:parseFloat(getComputedStyle(title).lineHeight),bioTop:bio.getBoundingClientRect().top,photoBottom:photo.getBoundingClientRect().bottom,buttonBottom:button.getBoundingClientRect().bottom};
  });
  assert(identity.titleHeight<=identity.lineHeight*2+1);assert(identity.bioTop>=Math.max(identity.photoBottom,identity.buttonBottom));
  await p.locator('.r-profile-settings summary').click();
  const rows=p.locator('.r-profile-settings>button,.r-profile-settings>a');
  for(const row of await rows.all()){assert((await bounds(row)).height>=44);assert(await row.locator('.icon').count()>=1);}
  await p.getByRole('button',{name:'Edit profile',exact:true}).click();await settle(p);
  const image=await p.evaluate(()=>{const c=document.createElement('canvas');c.width=64;c.height=64;c.getContext('2d').fillRect(0,0,64,64);return c.toDataURL('image/png').split(',')[1]});
  await p.locator('#profile-photo').setInputFiles({name:'photo.png',mimeType:'image/png',buffer:Buffer.from(image,'base64')});
  const photo=await bounds(p.locator('#profile-photo-preview')),pick=await bounds(p.locator('.r-profile-photo-pick')),remove=await bounds(p.locator('#profile-photo-remove'));
  assert.equal(Math.round(photo.width),72);assert(pick.x>=photo.right);assert(remove.x>=photo.right);assert(remove.right<=width);
  const save=p.getByRole('button',{name:'Save changes'});assert((await bounds(save)).bottom<=900);
  await p.screenshot({path:`${out}/editor-${width}-${theme}.png`});
  if(width<=600){
   await p.setViewportSize({width,height:420});await settle(p);
   await p.locator('[name=bio]').focus();await p.locator('[name=bio]').scrollIntoViewIfNeeded();
   const action=await bounds(save),field=await bounds(p.locator('[name=bio]'));
   assert(action.bottom<=420&&action.y>=0,'Save stays above the reduced viewport edge');assert(field.bottom<=action.y,'Bio does not cover Save');
   await p.screenshot({path:`${out}/editor-short-${width}-${theme}.png`});await p.setViewportSize({width,height:900});
  }
  await p.getByRole('button',{name:'Remove',exact:true}).click();assert(await p.locator('#profile-photo-remove').isHidden());
  await p.getByRole('button',{name:'Close dialog',exact:true}).click();await p.locator('.r-profile-editor').waitFor({state:'detached'});
  await p.goto(origin+'/?view=launchpad');await p.locator('.cr-community-entry-actions').waitFor();await settle(p);
  for(const button of await p.locator('.cr-community-entry-actions>button').all()){
   const data=await button.evaluate(e=>{const r=e.getBoundingClientRect(),label=e.querySelector('span'),range=document.createRange();range.selectNodeContents(label);const rects=[...range.getClientRects()];return {height:r.height,left:r.left,right:r.right,lines:new Set(rects.map(x=>Math.round(x.y))).size,labelLeft:rects[0].left,labelRight:rects.at(-1).right,scroll:e.scrollWidth,client:e.clientWidth};});
   assert(data.lines===1&&data.height>=44&&data.labelLeft>=data.left&&data.labelRight<=data.right&&data.scroll<=data.client+1,'Launch actions must not split words or clip labels');
  }
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await p.screenshot({path:`${out}/launch-${width}-${theme}.png`});
  await p.locator('.cr-community-entry-actions [data-id=algorithms]').click();
  await p.locator('.cr-community-section h2').filter({hasText:'Algorithms'}).waitFor();
  assert.deepEqual(errors,[]);results.push({width,theme,profile:true,shortViewport:width<=600,launchLabelsOneLine:true,algorithmNavigation:true,reducedMotion:theme==='dark'});await c.close();
 }
 await fs.writeFile(out+'/browser.json',JSON.stringify({results,walletActions:0},null,2));console.log(JSON.stringify({cases:results.length,walletActions:0}));
}finally{await browser?.close();server.kill('SIGTERM');}
