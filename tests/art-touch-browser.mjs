// Disposable UI fixtures; pointer gestures, recovery and back navigation, no writes.
import assert from 'node:assert/strict';import {spawn} from 'node:child_process';import {chromium} from 'playwright';import fs from 'node:fs/promises';
const origin='http://127.0.0.1:33223',out=process.env.RALLY_EVIDENCE||'/tmp/rally-art-touch';await fs.mkdir(out,{recursive:true});
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{env:{...process.env,RALLY_PREVIEW_PORT:'33223'},stdio:['ignore','ignore','pipe']});let browser,writes=0;const results=[];
try{
 for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch();
 for(const width of [320,390,1440])for(const reduced of [false,true]){
  const ctx=await browser.newContext({viewport:{width,height:844},reducedMotion:reduced?'reduce':'no-preference'}),page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const tokens=Array.from({length:40},(_,i)=>({id:'0x'+(i+1000).toString(16).padStart(40,'0'),address:'0x'+(i+1000).toString(16).padStart(40,'0'),symbol:'QA'+i,name:'Fixture '+i,price:1,change:40-i,volume:1,stale:false,fetchedAt:Date.now()/1000,...(i===1?{}:{logoThumbURI:'/assets/absent-thumbnail.png',logoCandidates:['/assets/absent-other.png','/assets/MON.png'],logoURI:'/assets/MON.png'})}));
  await page.route('**/*',r=>{const q=r.request(),u=new URL(q.url());if(!['GET','HEAD'].includes(q.method())){writes++;return r.abort();}if(u.origin!==origin)return r.abort();if(u.pathname==='/api/market-catalog')return r.fulfill({contentType:'application/json',body:JSON.stringify({tokens,total:40,nextOffset:null})});return r.continue();});
  await page.goto(origin+'/?view=discover');await page.locator('.rs-token-row').first().waitFor();
  const image=page.locator('.rs-token-row img').first();await page.waitForFunction(()=>{const i=document.querySelector('.rs-token-row img');return i?.naturalWidth>0&&i.classList.contains('is-loaded');});assert((await image.getAttribute('src')).endsWith('/assets/MON.png'));
  const fallback=page.locator('.rs-token-row').nth(1).locator('[data-art-tone]');assert.equal(await fallback.locator('img').count(),0);
  const button=page.locator('.rs-token-open').first(),bounds=await button.boundingBox();await page.mouse.move(bounds.x+20,bounds.y+20);await page.mouse.down();assert(await button.evaluate(e=>e.classList.contains('r-is-pressed')));await page.mouse.move(bounds.x+20,bounds.y+40);assert(!(await button.evaluate(e=>e.classList.contains('r-is-pressed'))));await page.mouse.up();
  // A cancelled drag must release its visual state; opening/closing keeps the list.
  await page.keyboard.press('Escape');await page.waitForTimeout(180);await button.click();await page.locator('.r-asset-modal').waitFor();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.keyboard.press('Escape');await page.locator('.r-asset-modal').waitFor({state:'detached'});await page.waitForTimeout(100);
  assert(await button.isVisible());assert.equal(new URL(page.url()).searchParams.get('view'),'discover');
  await page.screenshot({path:out+`/search-${width}-${reduced?'reduced':'motion'}.png`});
  assert.deepEqual(errors,[]);results.push({width,reduced,imageRecovered:true,pressCancelled:true,backPreserved:true});await ctx.close();
 }
 assert.equal(writes,0);await fs.writeFile(out+'/results.json',JSON.stringify({checks:results,writes},null,2));console.log(JSON.stringify({checks:results.length,writes}));
}finally{await browser?.close();server.kill('SIGTERM');}
