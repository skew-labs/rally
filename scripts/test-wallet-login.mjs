// Real UI and disposable backend; an offline fixture signs identity messages only.
// Set RALLY_LOGIN_QA_URL, RALLY_PLAYWRIGHT_ROOT and RALLY_AUTH_MODULES on the remote host.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import path from 'node:path';
const base=process.env.RALLY_LOGIN_QA_URL;
assert.match(base||'',/^http:\/\/127\.0\.0\.1:\d+$/);
const {chromium}=createRequire(path.join(process.env.RALLY_PLAYWRIGHT_ROOT,'package.json'))('playwright');
const {privateKeyToAccount}=createRequire(path.join(process.env.RALLY_AUTH_MODULES,'package.json'))('viem/accounts');
const signer=privateKeyToAccount('0x'+'31'.repeat(32)); // Disposable test identity, never funded.
const browser=await chromium.launch({headless:true,executablePath:process.env.RALLY_CHROME,args:['--no-sandbox','--disable-dev-shm-usage']});
const results=[];
try {
  for(const mode of ['success','double','reject','changed','expired','mutated','cancel']) {
    const context=await browser.newContext({viewport:{width:390,height:844}});
    const page=await context.newPage();let verifies=0;const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await context.route('**/*',async route=>{
      const u=new URL(route.request().url());
      if(u.origin!==base)return route.abort();
      if(u.pathname==='/api/auth/wallet/verify')verifies++;
      if(u.pathname==='/api/auth/wallet/challenge' && ['expired','mutated'].includes(mode)) {
        const response=await route.fetch(),proof=await response.json();
        if(mode==='expired')proof.expires=Math.floor(Date.now()/1000)-1;
        else proof.message+='\nApprove spending';
        return route.fulfill({response,json:proof});
      }
      return route.continue();
    });
    await page.exposeFunction('fixtureSign',async hex=>signer.signMessage({message:{raw:hex}}));
    await page.addInitScript(({address,mode})=>{
      window.fixtureCalls=[];let changed=false;
      window.ethereum={isMetaMask:true,on(){},removeListener(){},async request({method,params}) {
        window.fixtureCalls.push(method);
        if(method==='eth_accounts'||method==='eth_requestAccounts')return [changed?'0x'+'2'.repeat(40):address];
        if(method==='eth_chainId')return '0x1';
        if(method==='personal_sign') {
          if(mode==='reject')throw Object.assign(new Error('Rejected'),{code:4001});
          if(mode==='cancel')await new Promise(resolve=>{window.releaseFixture=resolve;});
          const signature=await window.fixtureSign(params[0]);
          if(mode==='changed')changed=true;
          return signature;
        }
        throw new Error('Unexpected wallet call: '+method);
      }};
    },{address:signer.address,mode});
    await page.goto(base+'/?view=account');
    await page.locator('#page [data-action="account"]').click();
    if(mode==='double')await page.locator('[data-auth-wallet="metamask"]').evaluate(button=>{button.click();button.click();});
    else await page.locator('[data-auth-wallet="metamask"]').click();
    if(mode==='cancel') {
      await page.waitForFunction(()=>window.fixtureCalls.includes('personal_sign'));
      await page.getByRole('button',{name:'Close dialog',exact:true}).click();
      await page.evaluate(()=>window.releaseFixture());
    }
    if(['success','double'].includes(mode)) {
      await page.locator('#page [data-action="edit-profile"]').waitFor();
      const boot=await page.evaluate(()=>fetch('/api/bootstrap').then(r=>r.json()));
      assert.equal(boot.wallet.toLowerCase(),signer.address.toLowerCase());
      assert.ok(boot.me);assert.equal(verifies,1);
    } else {
      if(mode!=='cancel')await page.locator('#wallet-connect-retry').waitFor();
      await page.waitForTimeout(150);
      assert.equal(verifies,0);
      const boot=await page.evaluate(()=>fetch('/api/bootstrap').then(r=>r.json()));
      assert.equal(boot.me,null);
    }
    const calls=await page.evaluate(()=>window.fixtureCalls);
    assert.equal(calls.filter(x=>x==='personal_sign').length,['expired','mutated'].includes(mode)?0:1);
    assert.ok(calls.every(x=>!['wallet_switchEthereumChain','wallet_addEthereumChain','eth_sendTransaction'].includes(x)));
    assert.deepEqual(errors,[]);
    results.push({mode,signatures:calls.filter(x=>x==='personal_sign').length,verifies,errors:errors.length});
    await context.close();
  }
} finally { await browser.close(); }
console.log(JSON.stringify({fixtureOnly:true,results}));
