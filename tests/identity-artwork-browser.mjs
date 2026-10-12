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
 await page.screenshot({path:out+'/home.png'});
 await page.goto(origin+'/?view=communities');await page.locator('.cx-grid').waitFor();
 assert(await page.locator('.cx-letter-art.r-character-avatar img').first().evaluate(i=>i.complete&&i.naturalWidth===192));
 await page.screenshot({path:out+'/communities.png'});
 assert.equal(writes,0);await fs.writeFile(out+'/results.json',JSON.stringify({checks:4,writes,tokenFrame:bounds,originalImageRecovery:true,bundledCharacter:true},null,2));console.log('Identity artwork: 4 checks, zero writes');
}finally{await browser.close();}
