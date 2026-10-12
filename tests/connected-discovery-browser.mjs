// Remote disposable preview. Public GET data only; every write is rejected.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
const origin=process.env.RALLY_PREVIEW_ORIGIN||'http://127.0.0.1:33313';
const out=process.env.RALLY_EVIDENCE||'/tmp/rally-connected-discovery';await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch(),results=[],reads=new Map();let writes=0;
try {
 for(const width of (process.env.RALLY_QUICK?[320]:[320,390,768,1440]))for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width,height:900},colorScheme:theme,reducedMotion:width===768?'reduce':'no-preference'});
  await context.addInitScript(theme=>{localStorage.setItem('rally-theme',theme);},theme);
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>{errors.push(e.stack);console.error(e.stack);});
  await page.route('**/api/**',async route=>{
   const req=route.request(),url=new URL(req.url());
   if(req.method()!=='GET'){writes++;return route.abort();}
   const path=url.pathname+url.search;
   if(!reads.has(path))reads.set(path,fetch('https://rallydot.com'+path).then(async r=>({status:r.status,contentType:r.headers.get('content-type')||'application/json',body:await r.text()})));
   try {await route.fulfill(await reads.get(path));}catch {await route.abort();}
  });
  await page.route('**/assets/token-art-*.webp',async route=>{try{const r=await route.fetch({url:'https://rallydot.com'+new URL(route.request().url()).pathname});await route.fulfill({response:r});}catch{await route.abort().catch(()=>{});}});
  await page.goto(origin+'/?view=home&section=markets&tab=memes');
  await page.locator('#home-overview .rc-algorithm-row').first().waitFor();
  await page.locator('.nad-table .r-coin-cell').first().waitFor();
  assert.equal(await page.locator('#home-balance strong').innerText(),'—');
  assert(await page.locator('#home-overview .rc-algorithm-row').count()<=2);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  // A narrow grid can fit the viewport while individual cells still overlap rows.
  const collisions=await page.locator('.nad-table tbody tr').evaluateAll(rows=>rows.slice(0,8).flatMap(row=>{
   const outer=row.getBoundingClientRect();
   return [...row.children].filter(cell=>cell.getClientRects().length).flatMap(cell=>{
    const box=cell.getBoundingClientRect();
    return box.top<outer.top-1||box.bottom>outer.bottom+1||box.left<outer.left-1||box.right>outer.right+1?[cell.cellIndex]:[];
   });
  }));
  assert.deepEqual(collisions,[],'Token cells stay inside their own row');
  const buyTarget=await page.locator('.nad-table .r-market-buy').first().boundingBox();
  assert(buyTarget.width>=44&&buyTarget.height>=44,'Compact Buy remains touchable');
  await page.screenshot({path:`${out}/home-${width}-${theme}.png`});
  const coin=page.locator('.nad-table .r-coin-cell').first();await coin.scrollIntoViewIfNeeded();
  const scroll=await page.evaluate(()=>scrollY);await coin.click();
  await page.locator('.r-nad-panel .rc-token-dock').waitFor();
  await page.evaluate(async()=>{await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));});
  await page.waitForFunction(()=>document.querySelector('#nad-chart canvas')||document.querySelector('#nad-chart svg')||document.querySelector('#nad-chart .nad-chart-empty'),null,{timeout:45000});
  await page.evaluate(()=>window.originalChart=document.querySelector('#nad-chart'));
  const dock=await page.locator('.rc-token-dock').boundingBox();assert(dock.y>=0&&dock.y+dock.height<=900);
  await page.locator('[data-info-tab=community]').click();assert(await page.locator('#rc-pane-community').isVisible());
  await page.locator('[data-info-tab=community]').press('ArrowRight');assert(await page.locator('#rc-pane-details').isVisible());
  await page.locator('[data-info-tab=holders]').click();
  assert(await page.evaluate(()=>window.originalChart===document.querySelector('#nad-chart')));
  await page.locator('.r-nad-content').evaluate(e=>e.scrollTop=0);await page.screenshot({path:`${out}/token-${width}-${theme}.png`});
  const buy=page.locator('.rc-token-dock [data-open-order=buy]');if(await buy.isEnabled()){
   await buy.click();assert(await page.locator('#nad-order-form input[name=amount]').isVisible());await page.locator('#nad-order-form input[name=amount]').fill('1');
   assert.equal(await page.locator('.rc-token-dock').isVisible(),false);
   await page.locator('.rc-back-chart').click();assert(await buy.isVisible());assert(await page.evaluate(()=>window.originalChart===document.querySelector('#nad-chart')));
  }
  await page.locator('[data-action=nad-close]').last().click();await page.waitForFunction(()=>!document.querySelector('.r-nad-panel'));
  assert(Math.abs((await page.evaluate(()=>scrollY))-scroll)<3);
  await page.locator('#home-overview [data-nav=feeds]').click();await page.locator('#algorithm-market-list .rc-algorithm-row').first().waitFor();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:`${out}/algorithms-${width}-${theme}.png`});
  if(width===390&&theme==='light')for(const [tab,action] of [['spot','market-detail'],['perps','perp-detail']]){
   await page.goto(origin+'/?view=home&section=markets&tab='+tab);
   const token=page.locator('[data-action='+action+']').first();await token.waitFor({timeout:45000});await token.click();
   await page.locator('.r-asset-modal').waitFor();await page.evaluate(async()=>{await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));});
   await page.evaluate(()=>window.assetChart=document.querySelector('.r-mini-chart'));
   await page.locator('[data-info-tab=community]').click();assert(await page.locator('#rc-pane-community').isVisible());
   assert(await page.evaluate(()=>window.assetChart===document.querySelector('.r-mini-chart')));
   const actions=await page.locator('.r-asset-actions').boundingBox();assert(actions.y>=0&&actions.y+actions.height<=900);
   await page.screenshot({path:`${out}/${tab}-390-light.png`});
   await page.getByRole('button',{name:'Close dialog',exact:true}).click();
  }
  assert.deepEqual(errors,[]);results.push({width,theme,chartPreserved:true,restoredScroll:true,overflow:false,errors});await context.close();
 }
 assert.equal(writes,0);await fs.writeFile(out+'/results.json',JSON.stringify({results,writes},null,2));console.log(JSON.stringify({cases:results.length,writes}));
}finally {await browser.close();}
