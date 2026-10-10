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
const paths=['/docs','/docs/getting-started','/docs/trading','/docs/prediction-markets','/docs/algorithms','/docs/community-tokens','/docs/agents','/docs/architecture','/docs/api','/docs/android','/docs/development','/docs/verification','/terms','/privacy'];
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
 await context.close();
 for(const width of [320,390,768,1440])for(const theme of ['light','dark']){
  const ctx=await browser.newContext({viewport:{width,height:900}});
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
   await page.goto(origin+path,{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);
   assert(await page.locator('main h1').isVisible(),path);report.checks++;
   assert.equal(await page.locator('html').getAttribute('data-theme'),theme);report.checks++;
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Overflow ${path} ${width} ${theme}`);report.checks++;
   assert(await page.locator('main').innerText().then(text=>text.length>300));report.checks++;
   assert.equal(report.errors.length,0,report.errors.join('\n'));report.checks++;
   for(const href of await page.locator('a[href^="#"]').evaluateAll(elements=>elements.map(e=>e.getAttribute('href')))){
    assert(await page.evaluate(href=>Boolean(document.getElementById(href.slice(1))),href),`Broken section ${path} ${href}`);report.checks++;
   }
   if(path==='/docs'&&width===390){
    await page.locator('.p-mobile-nav summary').click();assert(await page.locator('.p-mobile-nav').getByRole('link',{name:'Trading',exact:true}).isVisible());report.checks++;
    await page.locator('.p-mobile-nav').getByRole('link',{name:'Trading',exact:true}).click();assert.equal(new URL(page.url()).pathname,'/docs/trading');report.checks++;
   }
   if(evidence&&((width===390&&theme==='light'&&path==='/terms')||(width===1440&&theme==='dark'&&path==='/docs/architecture'))){
    await page.screenshot({path:evidence+`/document-${width}-${theme}-${path.split('/').pop()}.png`});
   }
  }
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
