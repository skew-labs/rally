import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {chromium} from 'playwright';
const origin='http://127.0.0.1:33217',out=process.env.RALLY_EVIDENCE||'/tmp/rally-token-recency';await fs.mkdir(out,{recursive:true});
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{env:{...process.env,RALLY_TESTING:'1',RALLY_TOKEN_MARKET_FIXTURE:'1',RALLY_PREVIEW_PORT:'33217',RALLY_FIXTURE_FILE:out+'/fixture.json'},stdio:'ignore'});
let browser;const results=[];
try {
 for(let i=0;i<150;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({args:['--no-sandbox']});
 for(const width of [320,390,768,1440])for(const theme of ['light','dark']) {
  const ctx=await browser.newContext({viewport:{width,height:900},colorScheme:theme,reducedMotion:width===320?'reduce':'no-preference'});
  await ctx.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  let count=0,firstId;
  await page.route('**/api/token-markets?*',async route=>{
   const response=await route.fetch(),data=await response.json(),category=new URL(route.request().url()).searchParams.get('category');
   if(category==='new' && !new URL(route.request().url()).searchParams.has('cursor')) {
    count++;firstId=data.tokens[0]?.id;
    if(count>1)data.tokens.unshift({...data.tokens[0],id:'0x'+'9'.repeat(40),symbol:'NEWEST',created:Math.floor(Date.now()/1000)-2});
   }
   data.tokens=data.tokens.map((t,i)=>({...t,volume:179400+i,change:i%2?-0.88:1735.07,marketCap:i?76700:9920000,graduatedAt:category==='graduated'?Math.floor(Date.now()/1000)-1200:undefined}));
   await route.fulfill({response,json:data});
  });
  await page.goto(origin+'/?view=home&section=markets&tab=tokens&category=new');await page.locator('.rt-token-row').first().waitFor();
  for(const category of ['new','graduated','crypto']) {
   if(category!=='new')await page.locator(`[data-action=token-category][data-id=${category}]`).click();
   await page.locator('.rt-token-row').first().waitFor();
   await page.locator('.rt-token-row').first().evaluate(e=>e.scrollIntoView({block:'center'}));
   const fit=await page.locator('.rt-token-row').evaluateAll(rows=>rows.slice(0,4).map(row=>{
    const cells=[...row.children].map(c=>c.getBoundingClientRect());
    return {overlap:cells.some((c,i)=>i>0&&c.left<cells[i-1].right-1),outside:cells.some(c=>c.left<0||c.right>innerWidth+1),capClipped:row.querySelector('.rt-price').scrollWidth>row.querySelector('.rt-price').clientWidth+1,buy:cells[2].width>=44&&cells[2].height>=44,volume:getComputedStyle(row.querySelector('.rt-volume')).display!=='none',change:getComputedStyle(row.querySelector('.rt-change')).display!=='none'};
   }));
   assert(fit.every(x=>!x.overlap&&!x.outside&&!x.capClipped&&x.buy&&x.volume&&x.change),JSON.stringify({width,category,fit}));
   assert.match(await page.locator('.rt-price').first().innerText(),/\$9.92M MC/);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   if(category==='graduated')assert.equal(await page.locator('.rt-age').first().textContent(),'20m');
   await page.screenshot({animations:'disabled',path:`${out}/${category}-${width}-${theme}.png`});
   results.push({width,theme,category,compactCap:true,volume:true,change:true,touchTargets:true});
   if(category==='new'&&width===320&&theme==='light') {
    await page.waitForSelector('.rt-new',{timeout:25000});assert.equal(await page.locator('.rt-token-row').first().getAttribute('data-token-row'),firstId);
    await page.locator('.rt-new').click();assert.equal(await page.locator('.rt-token-row').first().getAttribute('data-token-row'),'0x'+'9'.repeat(40));
   }
  }
  assert.deepEqual(errors,[]);await ctx.close();
 }
 await fs.writeFile(out+'/results.json',JSON.stringify(results,null,2));console.log(JSON.stringify({cases:results.length,arrivalWithoutListJump:true,financialActions:0}));
}finally{await browser?.close();server.kill();}
