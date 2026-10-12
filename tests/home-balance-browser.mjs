// Isolated delayed-account responses. No login or provider call is made.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const origin=process.env.RALLY_PREVIEW_ORIGIN||'http://127.0.0.1:33313';
const root=fileURLToPath(new URL('..',import.meta.url));
const browser=await chromium.launch();
try {
 const page=await browser.newPage();await page.route('**/balance-fixture',r=>r.fulfill({contentType:'text/html',body:'<main id="page"></main>'}));
 const modules=new Set(['experience.js','flow.js','connected-ui.js','assets/algorithm-library.js','assets/algorithm-library-data.js','assets/algorithm-discovery.js']);
 await page.route('**/*.js',async r=>{const name=new URL(r.request().url()).pathname.slice(1);if(modules.has(name))return r.fulfill({contentType:'text/javascript',body:await fs.readFile(root+'/'+name,'utf8')});return r.abort();});
 await page.goto(origin+'/balance-fixture');
 await page.evaluate(async()=>{
  const {experienceUI}=await import('/experience.js');
  const S=window.fixtureState={view:'home',homeSection:'markets',boot:{me:{id:'first'},wallet:'first-wallet',feeds:[],people:[]},posts:[]};
  const api=path=>path==='/api/portfolio'?new Promise(resolve=>window.balanceResponse=resolve):Promise.resolve({posts:[]});
  window.fixtureUI=experienceUI({S,$:s=>document.querySelector(s),api,esc:String,icon:()=>'',avatar:()=>'',usd:v=>'$'+Number(v).toFixed(2),pct:v=>v+'%',motion:{sections:()=>{}}});
  window.fixtureUI.decorateHome();
 });
 assert.equal(await page.locator('#home-balance strong').innerText(),'—');
 await page.evaluate(()=>{fixtureState.boot.me.id='second';fixtureState.boot.wallet='second-wallet';balanceResponse({wallet:'first-wallet',valuation:{valueUSD:987654}});});
 await page.evaluate(()=>new Promise(r=>requestAnimationFrame(r)));
 assert.equal(await page.locator('#home-balance strong').innerText(),'—');
 await page.evaluate(()=>{fixtureUI.dispose();document.querySelector('#page').replaceChildren();fixtureUI.decorateHome();balanceResponse({wallet:'second-wallet',valuation:{valueUSD:123.45,change24hPercent:2.1,partial:true}});});
 await page.getByText('$123.45',{exact:true}).waitFor();
 assert.equal(await page.locator('#home-balance small').innerText(),'Priced balance');
 assert.equal(await page.locator('#home-balance span').innerText(),'2.1% · 24h price change');
 console.log(JSON.stringify({checks:5,accountResponseIsolation:true,providerReads:0,walletActions:0}));
}finally {await browser.close();}
