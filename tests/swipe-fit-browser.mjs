// Isolated layout/gesture checks; no external providers, wallets or financial writes.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33415';
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'rally-swipe-fit-')),fixture=path.join(temp,'fixture.json');
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{cwd:root,env:{...process.env,RALLY_TESTING:'1',RALLY_TOKEN_MARKET_FIXTURE:'1',RALLY_PREVIEW_PORT:'33415',RALLY_FIXTURE_FILE:fixture},stdio:['ignore','ignore','pipe']});
let browser,diagnostics='';server.stderr.on('data',d=>diagnostics+=d);const results=[];
try{
 let data;for(let i=0;i<150;i++){try{data=JSON.parse(await fs.readFile(fixture));if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}assert(data,diagnostics);
 browser=await chromium.launch({args:['--no-sandbox']});
 for(const [width,height] of [[320,640],[390,844],[844,390],[1440,900]])for(const theme of ['light','dark']){
  const ctx=await browser.newContext({viewport:{width,height},hasTouch:true,isMobile:width<900,reducedMotion:theme==='light'?'no-preference':'reduce'}),page=await ctx.newPage(),errors=[],writes=[],reads=[];
  await ctx.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==origin)return route.abort();if(!['GET','HEAD'].includes(req.method())){writes.push(u.pathname);return route.abort();}
   const now=Date.now()/1000;
   if(u.pathname==='/api/perps')return route.fulfill({json:{markets:['BTC','ETH','SOL'].map((symbol,i)=>({id:i+1,symbol,baseSymbol:symbol,venue:'Perpl',mark:12345.67,open:true,execution:'wallet_transactions',priceSource:'QA reference',assetInfo:{id:'perp:'+symbol,symbol,logoURI:'/assets/'+symbol+'.png'}}))}});
   if(u.pathname==='/api/market-chart'){reads.push(u.searchParams.get('asset'));return route.fulfill({json:{asset:u.searchParams.get('asset'),points:[{time:now-60,value:100},{time:now,value:101}]}});}
   return route.continue();
  });
  const fit=async name=>{await page.evaluate(async()=>{await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),name+' overflow');if(process.env.RALLY_EVIDENCE_DIR)await page.screenshot({path:path.join(process.env.RALLY_EVIDENCE_DIR,`${name}-${width}-${theme}.png`)});};
  await page.goto(origin+'/?view=swipe&market=perps');await page.locator('.r-swipe-card[data-active] .rs-swipe-history svg').waitFor();await fit('swipe-perps');
  const bounds=await page.locator('.r-swipe-card[data-active]').evaluate(el=>{const chart=el.querySelector('.rs-swipe-history').getBoundingClientRect(),content=el.querySelector('.r-swipe-content').getBoundingClientRect(),actions=el.querySelector('.r-swipe-directions').getBoundingClientRect();return {chart:{top:chart.top,bottom:chart.bottom,height:chart.height},contentBottom:content.bottom,actionBottom:actions.bottom}});
  assert(bounds.chart.bottom<=bounds.contentBottom+1);assert(bounds.chart.height>=40);assert(bounds.actionBottom<height);
  const chart=page.locator('.r-swipe-card[data-active] .rs-swipe-history'),box=await chart.boundingBox();
  // Real touch input must reach paging rather than chart scrubbing.
  const cdp=await ctx.newCDPSession(page);await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+box.width/2,y:box.y+box.height*.8}]});
  for(let i=1;i<=6;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:box.x+box.width/2,y:Math.max(5,box.y+box.height*.8-i*32)}]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await page.waitForFunction(()=>document.querySelector('.r-swipe-card[data-active]')?.dataset.swipeIndex==='1');
  await page.locator('.r-swipe-card[data-active] .rs-swipe-history svg').waitFor();assert.equal(reads.filter(x=>x==='2').length,1,'next card shares prefetch');
  await page.goto(origin+'/?view=swipe&market=spot');await page.locator('.r-swipe-card[data-active]').waitFor();await fit('swipe-post');assert(await page.locator('.r-swipe-card[data-active]').evaluate(el=>{const caption=el.querySelector('.r-swipe-caption'),chart=el.querySelector('.rs-swipe-history');return !caption||!chart||caption.getBoundingClientRect().bottom<=chart.getBoundingClientRect().top;}),'post text overlaps chart');
  await page.locator('[data-action=swipe-tab][data-id=algorithms]').click();await page.locator('.sa-card[data-active]').waitFor();await fit('swipe-algorithm');
  await page.goto(origin+'/?view=home&section=markets&tab=tokens');await page.locator('.rt-token-row').first().waitFor();await fit('home');
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);results.push({width,height,theme,chartFits:true,chartGesture:true,prefetchShared:true,homeFits:true,writes:0});await page.unrouteAll({behavior:'ignoreErrors'});await ctx.close();
 }
 if(process.env.RALLY_EVIDENCE_DIR)await fs.writeFile(path.join(process.env.RALLY_EVIDENCE_DIR,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser?.close();server.kill('SIGTERM');await fs.rm(temp,{recursive:true,force:true});if(!results.length)console.error(diagnostics.slice(-1000));}
