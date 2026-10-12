// Public read-only data; inspect cells and labels, not just page overflow.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
const origin=process.env.RALLY_PREVIEW_ORIGIN||'http://127.0.0.1:33316';
const out=process.env.RALLY_EVIDENCE||'/tmp/rally-mobile-fit';await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch(),reads=new Map(),results=[];let writes=0;
const settle=p=>p.evaluate(async()=>{await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));});
const sizes=process.env.RALLY_QUICK?[[320,740],[390,844]]:[[320,740],[360,800],[390,844],[430,932],[600,900],[720,900],[760,900],[768,900],[844,390],[1440,900]];
try{
 for(const [width,height] of sizes)for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height},isMobile:width<1000,hasTouch:width<1000,colorScheme:theme,reducedMotion:width===320?'reduce':'no-preference'});
  await context.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);const page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
   const req=route.request();if(req.method()!=='GET'){writes++;return route.abort();}
   const url=new URL(req.url()),key=url.pathname+url.search;
   if(!reads.has(key))reads.set(key,fetch('https://rallydot.com'+key).then(async r=>({status:r.status,contentType:r.headers.get('content-type')||'application/json',body:await r.text()})));
   try{await route.fulfill(await reads.get(key));}catch{await route.abort().catch(()=>{});}
  });
  for(const view of ['spot','perps']){
   await page.goto(origin+'/?view=home&section=markets&tab='+view);const table=page.locator('.r-'+view+'-table');await table.locator('tbody tr').first().waitFor({timeout:45000});await settle(page);
   const failures=await table.locator('tbody tr').evaluateAll(rows=>rows.slice(0,20).flatMap((row,i)=>{
    const outer=row.getBoundingClientRect(),fail=[];
    for(const cell of row.children){if(!cell.getClientRects().length)continue;const r=cell.getBoundingClientRect();
     if(r.top<outer.top-1||r.bottom>outer.bottom+1||r.left<outer.left-1||r.right>outer.right+1)fail.push({row:i,text:cell.innerText,kind:'cell outside row'});
     if(cell.matches('.r-number')&&cell.scrollWidth>cell.clientWidth+1)fail.push({row:i,text:cell.innerText,kind:'clipped price'});
    }return fail;
   }));
   assert.deepEqual(failures,[],`${view} at ${width}: cells and prices fit`);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   const action=await table.locator('tbody tr').first().locator('td:last-child button').boundingBox();assert(action.width>=44&&action.height>=44);
   await table.evaluate(e=>scrollTo(0,e.getBoundingClientRect().top+scrollY-72));await page.screenshot({path:`${out}/${view}-${width}-${theme}.png`});
   results.push({view,width,height,theme,cellsFit:true,priceVisible:true});
  }
  await page.goto(origin+'/?view=swipe');await page.locator('.r-swipe-card[data-active]').first().waitFor({timeout:45000});await settle(page);
  for(const mode of ['spot','perps','prediction','algorithms']){
   const button=page.locator(`[data-action=swipe-tab][data-id=${mode}]`);await button.click();await settle(page);
   assert.equal(await button.getAttribute('aria-pressed'),'true');
   const fit=await page.locator('.r-swipe-tabs').evaluate(host=>{
    const outer=host.getBoundingClientRect();return [...host.querySelectorAll('button')].every(e=>{
     const r=e.getBoundingClientRect(),range=document.createRange();range.selectNodeContents(e);const text=range.getBoundingClientRect();
     return r.width>=44&&r.height>=44&&r.left>=outer.left&&r.right<=outer.right+1&&text.left>=r.left-1&&text.right<=r.right+1;
    });
   });assert(fit,`All Swipe labels and targets fit ${width} ${mode}`);
  }
  await page.locator('.sa-card[data-active]').waitFor({timeout:45000});await settle(page);
  const deck=await page.locator('.r-swipe-deck').boundingBox(),nav=await page.locator('.r-mobile-nav').boundingBox();
  assert(deck.height>120&&deck.y>=0&&deck.y+deck.height<=height+1);if(nav?.height>0&&nav.width>width/2)assert(deck.y+deck.height<=nav.y+1);
  await page.screenshot({path:`${out}/swipe-${width}-${theme}.png`});
  // Native horizontal/vertical gestures and keyboard navigation remain available.
  const next=page.locator('.sa-card[data-active] .r-swipe-direction.skip');if(await next.count())await next.click();
  await page.getByRole('button',{name:'Exit swipe mode',exact:true}).click();await page.waitForFunction(()=>document.body.dataset.view!=='swipe');
  assert.equal(errors.length,0,errors.join('\n'));results.push({view:'swipe',width,height,theme,allTabsFit:true,deckVisible:true,exitWorks:true});await context.close();
 }
 assert.equal(writes,0);await fs.writeFile(out+'/results.json',JSON.stringify({results,writes},null,2));console.log(JSON.stringify({cases:results.length,writes}));
}finally{await browser.close();}
