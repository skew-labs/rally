// Actual read-only feed and modal handlers against disposable state.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('..',import.meta.url)),origin='http://127.0.0.1:33227';
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'rally-wallet-ui-')),fixture=path.join(temp,'fixture.json');
const server=spawn(process.env.RALLY_PYTHON||'python3',['scripts/social-loop-preview.py'],{cwd:root,env:{...process.env,RALLY_TESTING:'1',RALLY_PREVIEW_PORT:'33227',RALLY_FIXTURE_FILE:fixture},stdio:['ignore','ignore','pipe']});
let logs='',browser,checks=0;server.stderr.on('data',data=>logs+=data);
try{
  for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({headless:true,executablePath:process.env.RALLY_CHROME_PATH});
  for(const width of [360,1440])for(const theme of ['light','dark']){
    const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[];
    await context.addInitScript(t=>localStorage.setItem('rally-theme',t),theme);page.on('pageerror',e=>errors.push(e.message));
    await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
    await page.goto(origin+'/?view=feed&id=wallet-confluence');
    await page.getByRole('heading',{name:'Buying together',exact:true}).waitFor();checks++;
    assert.equal(await page.locator('.r-feed-price b').innerText(),'Free');checks++;
    await page.getByRole('button',{name:'Wallet research',exact:true}).click();
    await page.getByRole('heading',{name:'Public wallet research',exact:true}).waitFor();checks++;
    await page.getByText('No verified profitable round trips yet.',{exact:true}).waitFor();checks++;
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));checks++;
    assert(await page.locator('#wallet-research-body').evaluate(el=>el.getBoundingClientRect().width<=innerWidth));checks++;
    await page.getByRole('button',{name:'Close dialog',exact:true}).click();
    await page.locator('[role=dialog]').waitFor({state:'detached'});
    assert.equal(await page.locator('[role=dialog]').count(),0);assert.deepEqual(errors,[]);checks+=2;
    await context.close();
  }
  console.log(JSON.stringify({checks,views:4,scope:'Synthetic provider-blocked UI; no wallet operations'}));
}finally{await browser?.close();server.kill('SIGTERM');await fs.rm(temp,{recursive:true,force:true});}
