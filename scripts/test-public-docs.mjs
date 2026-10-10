// Public navigation and document layouts, without authentication or financial writes.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root=fileURLToPath(new URL('..',import.meta.url));
const port=process.env.RALLY_DOCS_PORT||'4259';
const origin=process.env.RALLY_DOCS_ORIGIN||'http://127.0.0.1:'+port;
const evidence=process.env.RALLY_DOCS_EVIDENCE;
const paths=['/docs','/docs/getting-started','/docs/wallets','/docs/android','/docs/spot','/docs/memes','/docs/perps','/docs/prediction-markets','/docs/trading','/docs/fees','/docs/social','/docs/algorithms','/docs/community-tokens','/docs/agents','/docs/faq','/docs/developers','/docs/architecture','/docs/api','/docs/agent-api','/docs/development','/docs/verification','/terms','/privacy'];
const report={origin,pages:paths.length,checks:0,layouts:[],errors:[],writes:0,documentApiRequests:0};
let server,browser,diagnostics='';
try{
 if(!process.env.RALLY_DOCS_ORIGIN){
  server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/preview.py'],{cwd:root,env:{...process.env,RALLY_PREVIEW_PORT:port},stdio:['ignore','pipe','pipe']});
  server.stderr.on('data',data=>{diagnostics+=data});
  let ready=false;
  for(let i=0;i<80;i++){
   if(server.exitCode!==null)throw new Error(diagnostics);
   try{if((await fetch(origin+'/api/health')).ok){ready=true;break;}}catch{}
   await new Promise(resolve=>setTimeout(resolve,100));
  }
  assert(ready,'Document preview did not start: '+diagnostics);
 }
 if(evidence)await fs.mkdir(evidence,{recursive:true});
 browser=await chromium.launch({headless:true,...(process.env.RALLY_CHROME_PATH?{executablePath:process.env.RALLY_CHROME_PATH}:{})});
 const context=await browser.newContext();
 for(const path of paths){
  const response=await context.request.get(origin+path);assert.equal(response.status(),200,path);report.checks++;
  assert(response.headers()['content-type']?.includes('text/html'),path);report.checks++;
  assert((await response.text()).includes('<h1'),path);report.checks++;
  const head=await context.request.head(origin+path);assert.equal(head.status(),200,path);report.checks++;
 }
 // Exact route allowlist must not expose neighboring Markdown, source or private files.
 for(const path of ['/docs/unknown','/docs/terms','/docs/privacy','/docs/architecture.md','/docs/../service.py','/public-pages/terms.html','/docs/private/.env','/docs/%2e%2e/.env']){
  const response=await context.request.get(origin+path);assert.equal(response.status(),404,path);report.checks++;
 }
 for(const path of ['/terms/','/privacy/','/docs/','/docs/architecture/']){
  const response=await context.request.get(origin+path,{maxRedirects:0});assert.equal(response.status(),302);assert.equal(response.headers().location,path.slice(0,-1));report.checks+=2;
 }
 const indexResponse=await context.request.get(origin+'/docs-search.json');assert.equal(indexResponse.status(),200);report.checks++;
 const searchIndex=await indexResponse.json();assert.equal(searchIndex.length,paths.length);assert.deepEqual(new Set(searchIndex.map(item=>item.url)),new Set(paths));report.checks+=2;
 await context.close();
 for(const width of [1440,390,320,768])for(const theme of ['light','dark']){
  const ctx=await browser.newContext({viewport:{width,height:900},permissions:['clipboard-read','clipboard-write']});
  await ctx.addInitScript(theme=>{if(!localStorage.getItem('rally-theme'))localStorage.setItem('rally-theme',theme);},theme);
  const page=await ctx.newPage();page.on('pageerror',error=>report.errors.push(error.message));
  await ctx.route('**/*',route=>{
   if(!['GET','HEAD'].includes(route.request().method())){report.writes++;return route.abort();}
   const url=new URL(route.request().url());
   if(url.origin!==origin&&!['data:','blob:'].includes(url.protocol))return route.abort();
   return route.continue();
  });
  let onDocument=false;
  page.on('request',request=>{if(onDocument&&new URL(request.url()).pathname.startsWith('/api/'))report.documentApiRequests++;});
  for(const path of paths){
   onDocument=true;
   await page.goto(origin+path,{waitUntil:'load'});await page.evaluate(()=>document.fonts.ready);
   assert(await page.locator('main h1').isVisible(),path);report.checks++;
   assert.equal(await page.locator('html').getAttribute('data-theme'),theme);report.checks++;
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Overflow ${path} ${width} ${theme}`);report.checks++;
   assert(await page.locator('main').innerText().then(text=>text.length>300));report.checks++;
   assert.equal(report.errors.length,0,report.errors.join('\n'));report.checks++;
   for(const href of await page.locator('a[href^="#"]').evaluateAll(elements=>elements.map(e=>e.getAttribute('href')))){
    assert(await page.evaluate(href=>Boolean(document.getElementById(href.slice(1))),href),`Broken section ${path} ${href}`);report.checks++;
   }
   assert((await page.locator('main').evaluate(e=>getComputedStyle(e).fontFamily)).startsWith('Inter'));report.checks++;
   if(path==='/docs'&&width===390){
    await page.getByRole('button',{name:'Browse documentation',exact:true}).click();
    const drawer=page.getByRole('dialog',{name:'Browse documentation',exact:true});assert(await drawer.isVisible());report.checks++;
    await drawer.getByRole('link',{name:'Spot',exact:true}).click();assert.equal(new URL(page.url()).pathname,'/docs/spot');report.checks++;
    assert.equal(await page.locator('body').evaluate(e=>getComputedStyle(e).overflow),'visible');report.checks++;
    await page.goto(origin+path,{waitUntil:'networkidle'});
   }
   if(path==='/docs/architecture'){assert.equal(await page.locator('.p-diagram section').count(),4);assert.equal(await page.locator('.p-diagram pre').count(),0);report.checks+=2;}
   if(evidence&&((width===390&&theme==='light'&&['/docs','/docs/community-tokens'].includes(path))||(width===1440&&['/docs','/docs/architecture'].includes(path)))){
    await page.screenshot({path:evidence+`/document-${width}-${theme}-${path.split('/').pop()}.png`});
   }
  }
  await page.goto(origin+'/docs',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'Search documentation',exact:true}).click();
  assert(await page.getByRole('dialog',{name:'Search documentation',exact:true}).isVisible());report.checks++;
  await page.locator('#p-search-input').fill('buyback');
  await page.locator('#p-search-results a').first().waitFor();
  assert(await page.locator('#p-search-results a[href="/docs/community-tokens"]').isVisible());report.checks++;
  await page.locator('#p-search-input').fill('<img src=x onerror=alert(1)>');
  await page.waitForFunction(()=>document.querySelector('.p-search-count').textContent.startsWith('No matching'));
  assert.equal(await page.locator('#p-search-results img').count(),0);report.checks++;
  await page.keyboard.press('Escape');assert.equal(await page.locator('dialog[open]').count(),0);report.checks++;
  assert.equal(await page.evaluate(()=>document.activeElement.getAttribute('aria-label')),'Search documentation');report.checks++;
  await page.keyboard.press('Control+k');assert(await page.locator('#p-search').isVisible());report.checks++;
  await page.locator('#p-search-input').fill('wallets');await page.locator('#p-search-results a[href="/docs/wallets"]').waitFor();
  await page.keyboard.press('ArrowDown');assert(await page.locator('#p-search-results a[data-selected]').evaluate(e=>e===document.activeElement));report.checks++;
  await page.keyboard.press('Escape');
  await page.keyboard.press('Control+k');await page.locator('#p-search-input').fill('feed algorithms');
  await page.waitForFunction(()=>document.querySelector('#p-search-results a[data-selected]')?.getAttribute('href')==='/docs/algorithms');
  await page.locator('#p-search-input').press('Enter');await page.waitForURL(origin+'/docs/algorithms');report.checks++;
  await page.goto(origin+'/docs',{waitUntil:'load'});
  await page.getByRole('button',{name:'Copy page link',exact:true}).click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),origin+'/docs');report.checks++;
  await page.getByRole('navigation',{name:'Documentation sections',exact:true}).getByRole('link',{name:'Developers',exact:true}).click();
  assert.equal(new URL(page.url()).pathname,'/docs/developers');report.checks++;
  assert.equal(await page.getByRole('navigation',{name:width<900?'Mobile documentation':'Documentation',exact:true}).getByRole('link',{name:'Spot',exact:true}).count(),0);report.checks++;
  await page.goto(origin+'/docs');await page.getByRole('button',{name:theme==='dark'?'Switch to light mode':'Switch to dark mode'}).click();
  assert.equal(await page.locator('html').getAttribute('data-theme'),theme==='dark'?'light':'dark');report.checks++;
  await page.reload();assert.equal(await page.locator('html').getAttribute('data-theme'),theme==='dark'?'light':'dark');report.checks++;
  onDocument=false;await page.goto(origin+'/',{waitUntil:'domcontentloaded'});
  await page.locator('.l-footer-directory').scrollIntoViewIfNeeded();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Footer overflow ${width}`);report.checks++;
  const nav=page.getByRole('navigation',{name:'Rally links',exact:true});
  for(const [label,path] of [['Docs','/docs'],['Terms of Service','/terms'],['Privacy Policy','/privacy']]){
   const link=nav.getByRole('link',{name:label,exact:true});assert(await link.isVisible());assert.equal(await link.getAttribute('href'),path);report.checks+=2;
   assert(await link.evaluate(e=>e.getBoundingClientRect().height>=40));report.checks++;
  }
  if(evidence&&width===390&&theme==='light')await page.screenshot({path:evidence+'/landing-footer-mobile.png'});
  await nav.getByRole('link',{name:'Docs',exact:true}).click();assert.equal(new URL(page.url()).pathname,'/docs');report.checks++;
  report.layouts.push({width,theme,pages:paths.length,footer:true});await ctx.close();
 }
 assert.equal(report.writes,0);assert.equal(report.documentApiRequests,0);assert.deepEqual(report.errors,[]);report.checks+=3;
 if(evidence)await fs.writeFile(evidence+'/public-docs-browser.json',JSON.stringify(report,null,2));
 console.log(JSON.stringify(report));
}finally{await browser?.close();server?.kill('SIGTERM');}
