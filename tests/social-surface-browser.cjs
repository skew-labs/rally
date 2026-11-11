// Run on the authorized remote browser host. No wallet/auth writes or posts.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const stage=process.env.RALLY_STAGE_ROOT,output=process.env.RALLY_EVIDENCE||'/tmp/rally-social-check';
fs.mkdirSync(output,{recursive:true});
const manifest=stage&&JSON.parse(fs.readFileSync(path.join(stage,'app-bundle.json')));
const results=[],errors=[];
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 for(const [width,height,theme] of [[1440,1000,'light'],[390,844,'light'],[320,740,'light'],[768,1024,'light'],[390,844,'dark'],[1440,1000,'dark']]){
  const ctx=await browser.newContext({viewport:{width,height},deviceScaleFactor:1,serviceWorkers:'block',reducedMotion:'reduce'});
  await ctx.addInitScript(t=>{localStorage.setItem('rally-theme',t);},theme);
  await ctx.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());
   if(!['GET','HEAD','OPTIONS'].includes(req.method()))return route.fulfill({status:200,contentType:'application/json',body:'{}'});
   if(stage&&url.origin==='https://rallydot.com'){
    if(req.isNavigationRequest()){
     let html=fs.readFileSync(path.join(stage,'index.html'),'utf8');
     html=html.replace(/<link rel="(?:stylesheet|modulepreload)"[^>]*>/g,'').replace(/<script type="module"[^>]*><\/script>/g,'');
     html=html.replace('</head>',`<link rel="stylesheet" href="/${manifest.css}"></head>`).replace('</body>',`<script type="module" src="/${manifest.js}"></script></body>`);
     return route.fulfill({status:200,contentType:'text/html',body:html});
    }
    if([manifest.js,manifest.css].includes(url.pathname.slice(1)))return route.fulfill({status:200,contentType:url.pathname.endsWith('.css')?'text/css':'application/javascript',body:fs.readFileSync(path.join(stage,url.pathname))});
   }
   return route.continue();
  });
  const page=await ctx.newPage();page.on('pageerror',error=>errors.push({width,theme,message:error.message}));
  await page.goto('https://rallydot.com/app',{waitUntil:'domcontentloaded',timeout:40000});
  await page.locator('.sn-post').first().waitFor({timeout:40000});
  // Apply through the real theme action if the stored theme key ever changes.
  if(await page.locator('html').getAttribute('data-theme')!==theme)await page.locator('.sn-header [data-action=theme]').click();
  await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.querySelectorAll(".sn-header img,.sn-corner img,.sn-post:first-child img")].map(img=>Promise.race([img.decode().catch(()=>{}),new Promise(r=>setTimeout(r,3000))])));});
  await page.screenshot({path:path.join(output,`home-${width}-${theme}.png`),fullPage:false});
  const fit=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth-innerWidth,header:document.querySelector('.sn-header').getBoundingClientRect().height,main:document.querySelector('#main').getBoundingClientRect().width,post:document.querySelector('.sn-post').getBoundingClientRect().width,homeTabs:!!document.querySelector('.rx-home-tabs'),font:getComputedStyle(document.querySelector('.sn-post')).fontFamily}));
  assert(fit.overflow<=1,`Home overflow ${width}: ${fit.overflow}`);assert(!fit.homeTabs,'Market tabs must not decorate social home');assert(fit.main>240);if(width===768)assert(fit.main>500,"Tablet must reclaim the hidden rail width");
  const firstId=await page.locator('.sn-post').first().getAttribute('data-post');
  await page.locator('.sn-post .r-person').first().click();await page.locator('.sn-profile').waitFor({timeout:20000});
  assert((await page.locator('.sn-profile h1').innerText()).length>0);
  await page.locator('#timeline .sn-post,#timeline .r-empty').first().waitFor({timeout:30000});await page.evaluate(async()=>{const img=document.querySelector('.sn-profile .r-avatar img');if(img)await img.decode().catch(()=>{});});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Profile overflow');
  await page.screenshot({path:path.join(output,`profile-${width}-${theme}.png`)});
  await page.goBack();await page.locator(`[data-post="${firstId}"]`).waitFor({timeout:20000});
  if(width===390&&theme==='light'||width===1440&&theme==='light'){
   const nav=width<761?'.r-mobile-nav':'.r-sidebar';
   await page.locator(nav+' [data-nav=communities]').click();await page.locator('.sn-discussion-title').waitFor();
   await page.screenshot({path:path.join(output,`communities-${width}.png`)});
   await page.locator(nav+' [data-nav=explore]').click();await page.locator('.rx-home-head').waitFor({timeout:25000});
   await page.locator('.rt-token-row').first().waitFor({timeout:40000});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Market overflow');await page.screenshot({path:path.join(output,`markets-${width}.png`)});
   assert.equal(await page.locator(nav+' [data-nav=explore]').getAttribute('aria-current'),'page');
   assert.equal(await page.locator(nav+' [data-nav=home]').getAttribute('aria-current'),null);
   await page.locator(nav+' [data-nav=home]').click();await page.locator('.sn-feed-toolbar').waitFor();
   await page.locator('.sn-feed-modes [data-id=following]').click();await page.locator('.r-modal').waitFor();await page.keyboard.press('Escape');
   await page.locator('.sn-feed-modes [data-id=for-you]').click();await page.locator('.sn-post').first().waitFor({timeout:20000});
   await page.locator('.sn-composer').click();await page.locator('.r-modal').waitFor();
   assert(await page.locator('.r-modal').isVisible());await page.keyboard.press('Escape');assert.equal(await page.locator('.r-modal').count(),0);
  }
  results.push({width,height,theme,fit,profileAndBack:true});await ctx.close();
 }
 await browser.close();
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({results,errors},null,2));
 assert.equal(errors.length,0,JSON.stringify(errors));console.log(JSON.stringify({layouts:results.length,errors}));
})().catch(e=>{console.error(e);process.exit(1)});
