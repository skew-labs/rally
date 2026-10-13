import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const root=path.resolve(process.env.RALLY_SOURCE||'.');
const out=process.env.RALLY_EVIDENCE||'/tmp/rally-film';fs.mkdirSync(out,{recursive:true});
const origin=process.env.RALLY_ORIGIN||'https://rallydot.com';
const live=process.env.RALLY_LIVE==='1';
const files={'/':'landing.html','/landing.css':'landing.css','/assets/landing-film.js':'assets/landing-film.js'};
const mime=name=>name.endsWith('.html')?'text/html':name.endsWith('.css')?'text/css':'text/javascript';
const isFilm=url=>/rally-film-[a-f0-9]+\.(mp4|webm)(?:\?|$)/.test(url);
const browser=await chromium.launch({args:['--no-sandbox','--disable-dev-shm-usage']});
const results=[];
try{
 for(const [width,theme] of [[320,'light'],[390,'light'],[390,'dark'],[768,'light'],[1440,'light'],[1440,'dark']]){
  const context=await browser.newContext({viewport:{width,height:width<600?844:1000},isMobile:width<600,hasTouch:width<600,colorScheme:theme,reducedMotion:width===320?'reduce':'no-preference'});
  const page=await context.newPage(),errors=[],media=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(isFilm(r.url()))media.push(r.url());});
  await context.route('**/*',route=>{
   const req=route.request(),url=new URL(req.url());
   if(!['GET','HEAD'].includes(req.method())){writes.push(req.url());return route.abort();}
   if(!live&&url.origin===origin&&files[url.pathname])return route.fulfill({body:fs.readFileSync(path.join(root,files[url.pathname])),contentType:mime(files[url.pathname])});
   return route.continue();
  });
  await page.goto(origin+'/',{waitUntil:'domcontentloaded'});
  if(await page.evaluate(()=>document.documentElement.dataset.theme)!==theme)await page.locator('.l-theme').click();
  const film=page.locator('.l-film-media'),video=page.locator('#rally-film'),trigger=page.locator('.l-film-play');
  await film.scrollIntoViewIfNeeded();await film.locator('img').evaluate(im=>im.decode());
  assert.equal(media.length,0);assert.equal(await video.getAttribute('src'),null);assert.equal(await video.getAttribute('preload'),'none');
  assert.equal(await page.locator('.l-footer-word').count(),0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  const size=await film.boundingBox();assert(Math.abs(size.width/size.height-9/16)<.001);
  await page.locator('.l-film').screenshot({path:out+`/${width}-${theme}-poster.png`});
  const playback=width===390||width===1440&&theme==='light';
  if(playback){
   if(width===1440){await trigger.focus();await page.keyboard.press('Space');}else await trigger.tap();
   await page.waitForFunction(()=>{const v=document.querySelector('#rally-film');return !v.paused&&v.currentTime>.15;},null,{timeout:20000});
   assert.equal(await video.evaluate(v=>v.controls),false);assert(await page.locator('.l-film-controls').isVisible());
   await page.locator('[data-film-toggle]').click();assert(await video.evaluate(v=>v.paused));
   await page.locator('[data-film-sound]').click();assert(await video.evaluate(v=>v.muted));
   assert.equal(await page.locator('[data-film-sound]').getAttribute('aria-label'),'Unmute film');
   await page.locator('[data-film-sound]').click();assert.equal(await video.evaluate(v=>v.muted),false);
   const seek=page.locator('.l-film-seek');await seek.focus();await page.keyboard.press('ArrowRight');
   await seek.evaluate(el=>{el.value='6';el.dispatchEvent(new Event('input',{bubbles:true}));});
   await page.waitForFunction(()=>Math.abs(document.querySelector('#rally-film').currentTime-6)<.1);
   assert.equal(await page.locator('.l-film-time').textContent(),'0:06 / 0:18');
   const targets=await page.locator('.l-film-controls button').evaluateAll(bs=>bs.filter(b=>!b.hidden).map(b=>{const r=b.getBoundingClientRect();return {width:r.width,height:r.height};}));
   assert(targets.every(b=>b.width>=44&&b.height>=44));
   const fit=await page.locator('.l-film-controls').evaluate(el=>{const r=el.getBoundingClientRect(),m=el.parentElement.getBoundingClientRect();return r.left>=m.left&&r.right<=m.right&&r.bottom<=m.bottom;});assert(fit);
   await page.locator('.l-film').screenshot({path:out+`/${width}-${theme}-controls.png`});
   if(width===1440){await page.locator('[data-film-fullscreen]').click();await page.waitForFunction(()=>document.fullscreenElement&&document.querySelector('[data-film-fullscreen]').getAttribute('aria-label')==='Exit fullscreen');await page.locator('[data-film-fullscreen]').click();await page.waitForFunction(()=>!document.fullscreenElement);}
   await page.locator('[data-film-toggle]').click();await page.waitForFunction(()=>!document.querySelector('#rally-film').paused);
   await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));await page.waitForFunction(()=>document.querySelector('#rally-film').paused);
   await film.scrollIntoViewIfNeeded();assert(await video.evaluate(v=>v.paused));
   await seek.evaluate(el=>{el.value=String(Number(el.max)-.1);el.dispatchEvent(new Event('input',{bubbles:true}));});
   await page.locator('[data-film-toggle]').click();await page.waitForFunction(()=>document.querySelector('.l-film-play-label').textContent==='Replay film');
   assert(await trigger.isVisible());await trigger.click();await page.waitForFunction(()=>document.querySelector('#rally-film').currentTime>.1&&!document.querySelector('#rally-film').paused);
  }
  await page.locator('.l-footer').scrollIntoViewIfNeeded();await page.locator('.l-footer').screenshot({path:out+`/${width}-${theme}-footer.png`});
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);results.push({width,theme,playback,initialMediaRequests:0,footerLogoRemoved:true,errors});await context.close();
 }
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});let reject=true;
 await context.route('**/*',route=>{
  const req=route.request(),url=new URL(req.url());if(!['GET','HEAD'].includes(req.method()))return route.abort();
  if(isFilm(req.url())&&reject)return route.abort();
  if(!live&&url.origin===origin&&files[url.pathname])return route.fulfill({body:fs.readFileSync(path.join(root,files[url.pathname])),contentType:mime(files[url.pathname])});return route.continue();
 });
 const page=await context.newPage();await page.goto(origin+'/',{waitUntil:'domcontentloaded'});await page.locator('.l-film-play').scrollIntoViewIfNeeded();await page.locator('.l-film-play').tap();
 await page.waitForFunction(()=>!document.querySelector('.l-film-fallback').hidden);assert.equal(await page.locator('.l-film-play-label').textContent(),'Try again');
 reject=false;await page.locator('.l-film-play').tap();await page.waitForFunction(()=>document.querySelector('#rally-film').currentTime>.1,null,{timeout:20000});await context.close();
 fs.writeFileSync(out+'/results.json',JSON.stringify({live,results,retry:true},null,2));console.log(JSON.stringify({live,layouts:results.length,playbackChecks:results.filter(r=>r.playback).length,retry:true,noInitialMedia:true}));
}finally{await browser.close();}
