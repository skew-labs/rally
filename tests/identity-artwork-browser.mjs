// Public-read preview checks: genuine token artwork, bounded fallback, stable frames.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
const origin=process.env.RALLY_PREVIEW_ORIGIN||'http://127.0.0.1:33313',out=process.env.RALLY_EVIDENCE||'/tmp/rally-identity-artwork';
await fs.mkdir(out,{recursive:true});const browser=await chromium.launch();let writes=0;
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.route('**/api/**',async route=>{if(route.request().method()!=='GET'){writes++;return route.abort();}const url=new URL(route.request().url());try{const response=await route.fetch({url:'https://rallydot.com'+url.pathname+url.search});await route.fulfill({response});}catch{await route.abort().catch(()=>{});}});
 await page.route('**/assets/token-art-*.webp',async route=>{try{const response=await route.fetch({url:'https://rallydot.com'+new URL(route.request().url()).pathname});await route.fulfill({response});}catch{await route.abort().catch(()=>{});}});
 await page.goto(origin+'/?view=home&section=markets&tab=memes');
 const token=page.locator('.nad-table .r-token-art').first();await token.waitFor();
 await page.waitForFunction(()=>{const i=document.querySelector('.nad-table .r-token');return i?.complete&&i.naturalWidth>0&&i.classList.contains('is-loaded');});
 const bounds=await token.evaluate(e=>{const a=e.getBoundingClientRect(),b=e.querySelector('img').getBoundingClientRect();return {width:a.width,height:a.height,image:b.width,imageHeight:b.height};});
 assert.equal(bounds.width,bounds.height);assert.equal(bounds.width,bounds.image);assert.equal(bounds.height,bounds.imageHeight);
 const original=await token.locator('img').getAttribute('data-art-fallback');assert(original);
 await token.locator('img').evaluate(e=>{e.classList.remove('is-loaded');e.src='/assets/intentional-missing-thumbnail.webp';});
 await page.waitForFunction(original=>{const i=document.querySelector('.nad-table .r-token');return i?.src===original&&i.complete&&i.naturalWidth>0&&i.classList.contains('is-loaded')&&!i.hasAttribute('data-art-fallback');},original);
 const avatar=page.locator('#side-account-profile .r-character-avatar img');await avatar.waitFor();
 assert(await avatar.evaluate(i=>i.complete&&i.naturalWidth===192));
 const faces=await page.locator('.r-people-rail .r-character-avatar img').evaluateAll(images=>images.map(i=>i.getAttribute('src')));
 assert(new Set(faces).size>=3,'public accounts must not all use one face');
 const facesBefore=[...faces];await page.reload();await page.locator('.r-people-rail .r-character-avatar img').first().waitFor({state:'attached'});
 assert.deepEqual(await page.locator('.r-people-rail .r-character-avatar img').evaluateAll(images=>images.map(i=>i.getAttribute('src'))),facesBefore);
 for(const file of ['v1','mint-v1','coral-v1','blue-v1','gold-v1','rose-v1'])assert(await page.evaluate(async file=>{const i=new Image();i.src='/assets/rally-character-'+file+'.webp';await i.decode();return i.naturalWidth===192&&i.naturalHeight===192;},file));
 await page.screenshot({path:out+'/home.png'});
 await page.goto(origin+'/?view=agents');await page.locator('.r-agent-directory .r-character-avatar img').first().waitFor();
 assert(new Set(await page.locator('.r-agent-directory .r-character-avatar img').evaluateAll(images=>images.map(i=>i.getAttribute('src')))).size>=3);
 await page.locator('.r-agent-directory').evaluate(async host=>{await Promise.all([...host.querySelectorAll('img')].map(i=>i.decode().catch(()=>{})));});
 await page.waitForFunction(()=>{const i=document.querySelector('.r-agent-card [data-agent-brand=codex]>img');return i?.complete&&i.naturalWidth>0&&i.nextElementSibling.hidden;});
 await page.evaluate(async()=>{await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));});
 await page.screenshot({path:out+'/agents.png'});
 await page.goto(origin+'/?view=communities');await page.locator('.cx-grid').waitFor();
 assert(await page.locator('.cx-letter-art.r-character-avatar img').first().evaluate(i=>i.complete&&i.naturalWidth===192));
 const community=page.locator('.cx-card:has(.cx-letter-art.r-character-avatar)').first(),id=await community.getAttribute('data-community');
 assert.equal(await community.locator('.r-character-avatar img').getAttribute('src'),await page.locator('#side-communities [data-id="'+id+'"] .r-character-avatar img').getAttribute('src'));
 await page.screenshot({path:out+'/communities.png'});
 assert.equal(writes,0);await fs.writeFile(out+'/results.json',JSON.stringify({checks:8,writes,tokenFrame:bounds,originalImageRecovery:true,bundledCharacter:true,distinctFaces:new Set(faces).size,stableOnReload:true,communityIdentityMatches:true},null,2));console.log('Identity artwork: 8 checks, zero writes');
}finally{await browser.close();}
