// The auth SDK is loaded only after an explicit login or wallet action.
export async function walletAccounts(provider,change=false){
  if(change){
    try{await provider.request({method:'wallet_requestPermissions',params:[{eth_accounts:{}}]});}
    catch(error){if(![-32601,4200].includes(Number(error.code)))throw error;}
  }
  let accounts=await provider.request({method:'eth_accounts'});
  if(!accounts?.length)accounts=await provider.request({method:'eth_requestAccounts'});
  if(!/^0x[0-9a-fA-F]{40}$/.test(accounts?.[0]||'')||/^0x0{40}$/i.test(accounts[0]))throw new Error('Choose a wallet account.');
  return accounts;
}

export async function ensureMonad(provider,current=()=>{}){
  current();
  if(Number(await provider.request({method:'eth_chainId'}))===143){current();return;}
  current();
  try{await provider.request({method:'wallet_switchEthereumChain',params:[{chainId:'0x8f'}]});}
  catch(error){
    if(Number(error.code)!==4902)throw error;
    current();
    await provider.request({method:'wallet_addEthereumChain',params:[{chainId:'0x8f',chainName:'Monad',nativeCurrency:{name:'MON',symbol:'MON',decimals:18},rpcUrls:['https://rpc.monad.xyz'],blockExplorerUrls:['https://monadvision.com']}]});
    current();
    if(Number(await provider.request({method:'eth_chainId'}))!==143)await provider.request({method:'wallet_switchEthereumChain',params:[{chainId:'0x8f'}]});
  }
  current();
  if(Number(await provider.request({method:'eth_chainId'}))!==143)throw new Error('Switch your wallet to Monad to continue.');
  current();
}

export function agentSignature(value){
  const raw=String(value||'').trim(),valid=/^0x[0-9a-fA-F]{130}$/;
  if(valid.test(raw))return raw;
  if(raw.length>16384)return null;
  const found=new Set();
  function visit(data,depth=0){
    if(!data||typeof data!=='object'||depth>6)return;
    if(typeof data.signature==='string'&&valid.test(data.signature))found.add(data.signature);
    for(const child of Object.values(data).slice(0,64))visit(child,depth+1);
  }
  try{visit(JSON.parse(raw));}catch{
    for(const line of raw.split('\n')){try{visit(JSON.parse(line));}catch{}}
    for(const match of [...raw.matchAll(/(?:^|\n)(?=\{)/g)].slice(-64)){try{visit(JSON.parse(raw.slice(match.index).trim()));}catch{}}
  }
  return found.size===1?[...found][0]:null;
}

export function authUI({S,$,api,esc,icon,modal,closeModal,boot,render,notify,afterLogin,connectWallet}) {
  let sdkPromise,loginBusy=false;
  const mark='<img class="r-auth-mark" src="/assets/agent-metamask.svg" width="28" height="28" alt="MetaMask">';
  const cfg=()=>S.boot?.auth?.privy;
  async function sdk(){
    if(!cfg()?.enabled)throw new Error('Email and social login are not available yet.');
    if(!sdkPromise)sdkPromise=import('/assets/auth/privy-bridge.js').then(async module=>{await module.initialize(cfg());return module;}).catch(error=>{sdkPromise=null;throw error;});
    return sdkPromise;
  }
  function buttons(){return `<div class="r-auth-methods"><button class="r-btn primary full" id="wallet-signin" type="button">${icon('wallet')}Connect wallet</button>${cfg()?.enabled?'<button class="r-btn full" id="privy-signin" type="button">Continue with email or Google</button>':''}<details class="r-auth-advanced"><summary>Agent wallet</summary><button class="r-btn full" id="agent-wallet-signin" type="button">${mark}MetaMask Agent Wallet</button><small>Connect through your external agent.</small></details></div>`;}
  function bind(next){
    const button=$('#privy-signin');if(button)button.onclick=()=>signIn(false,next,button);
    const agent=$('#agent-wallet-signin');if(agent)agent.onclick=()=>agentWallet(next);
  }
  async function signIn(link=false,next,button){
    if(loginBusy)return;loginBusy=true;
    const account=S.boot.me?.id,route=location.href;
    if(button){button.disabled=true;button.setAttribute('aria-busy','true');}
    try{
      const bridge=await sdk();
      if(sessionStorage.getItem('rally:privy-signout-pending')){await bridge.logout();sessionStorage.removeItem('rally:privy-signout-pending');}
      sessionStorage.setItem('rally:privy-intent',JSON.stringify({link,owner:account||null,path:location.pathname,created:Date.now()}));
      closeModal();
      const tokens=await bridge.signIn();
      if(S.boot.me?.id!==account||location.href!==route)throw new Error('The account or page changed. Start login again.');
      await api('/api/auth/privy',{...tokens,link});
      await boot();closeModal();await render();notify(link?'Login added':'Signed in');
      await afterLogin(next);
      return true;
    }catch(error){notify(error.message||'Could not sign in. Try again.');return false;}
    finally{sessionStorage.removeItem('rally:privy-intent');loginBusy=false;if(button?.isConnected){button.disabled=false;button.removeAttribute('aria-busy');}}
  }
  function agentCard(){const c=S.boot.auth?.agentWallet;return `<section class="r-agent-wallet-card"><span>${mark}<span><b>MetaMask Agent Wallet</b><small>${c?.connected?'Connected · Monad':'Your agent’s wallet · Monad'}</small></span></span><button class="r-btn small ${c?.connected?'is-connected':''}" data-action="agent-wallet">${c?.connected?icon('check')+'Connected':'Connect'}</button></section>`;}
  let agentConnecting=false;
  async function agentWallet(next){
    if(agentConnecting)return;
    const owner=S.boot.me?.id||null;
    if(S.boot.auth?.agentWallet?.connected&&owner)return connectedAgent();
    agentConnecting=true;
    modal('Connect agent wallet',`<div class="r-auth-provider">${mark}<span><b>MetaMask Agent Wallet</b><small>Monad · No transaction</small></span></div><p class="r-agent-connect-status" role="status">Opening your agent wallet…</p>`,'r-agent-login r-agent-connect');
    const opening=S.modal;
    try{
      const proof=await api('/api/agent-wallet/prepare',{});
      if(S.modal!==opening||(S.boot.me?.id||null)!==owner)return;
      agentConnection(proof,owner,next);
    }catch(error){
      if(S.modal===opening){
        $('.r-agent-connect-status').textContent=error.message;
        if(error.code==='agent_pairing_required')$('.r-agent-connect-status').insertAdjacentHTML('afterend','<button class="r-btn primary full" id="agent-primary-login" type="button">Sign in</button>');
        if($('#agent-primary-login'))$('#agent-primary-login').onclick=()=>{closeModal();document.querySelector('[data-action=account]')?.click();};
        if(error.code==='agent_bridge_unpaired')$('.r-agent-connect-status').insertAdjacentHTML('afterend','<button class="r-btn full" id="agent-manual-fallback" type="button">Connect from another agent</button>');
        if($('#agent-manual-fallback'))$('#agent-manual-fallback').onclick=()=>manualAgentWallet(next);
      }
    }finally{agentConnecting=false;}
  }
  function connectedAgent(){
    const c=S.boot.auth.agentWallet;
    modal('Agent wallet',`<div class="r-auth-provider">${mark}<span><b>Connected</b><small>MetaMask · Monad · Guard</small></span></div><div class="r-agent-connected-address">${esc(c.address)}</div><button class="r-btn full" id="disconnect-agent-wallet" type="button">Disconnect</button>`,'r-agent-login');
    $('#disconnect-agent-wallet').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{await api('/api/agent-wallet/disconnect',{});await boot();closeModal();await render();notify('Agent wallet disconnected');}catch(error){notify(error.message);if(b.isConnected)b.disabled=false;}};
  }
  function agentConnection(proof,owner,next){
    modal('Connect agent wallet',`<div class="r-auth-provider">${mark}<span><b>${esc(proof.address.slice(0,6)+'…'+proof.address.slice(-4))}</b><small>Monad · Chain 143 · No transaction</small></span></div><p class="r-agent-connect-status" role="status">Preparing your signature…</p><p class="r-agent-connect-notice" id="agent-approval-notice" aria-live="polite"></p><pre class="r-code r-agent-connect-message" aria-label="Exact message to sign">${esc(proof.message)}</pre><small class="r-agent-connect-expiry" id="agent-connect-expiry"></small><div class="r-form-error" role="alert"></div><button class="r-btn full" id="agent-connect-check" type="button">Check approval</button>`,'r-agent-login r-agent-connect');
    const instance=S.modal;let busy=false,finished=false,timer,request=proof;
    const current=()=>S.modal===instance&&(S.boot.me?.id||null)===owner;
    const wake=()=>{if(!document.hidden)poll();};
    instance.cleanup=()=>{clearTimeout(timer);document.removeEventListener('visibilitychange',wake);window.removeEventListener('focus',wake);};
    document.addEventListener('visibilitychange',wake);window.addEventListener('focus',wake);
    const status=$('.r-agent-connect-status'),notice=$('#agent-approval-notice'),expiry=$('#agent-connect-expiry'),error=$('.r-form-error'),check=$('#agent-connect-check');
    function paint(){
      const left=Math.max(0,Math.ceil(Math.min(request.expires,request.approvalExpires||request.expires)-Date.now()/1000));
      expiry.textContent=left?`Request expires in ${Math.floor(left/60)}:${String(left%60).padStart(2,'0')}`:'Request expired. The existing MetaMask request will be checked before another can start.';
      notice.textContent=request.notice||'';
      status.textContent=request.state==='waiting'?'Approve in MetaMask':request.state==='verified'?'Connecting…':request.state==='uncertain'?'Checking the existing request…':request.state==='failed'?'Couldn’t connect':request.state==='expired'?'Request expired':request.state==='revoked'?'Connection removed':'Waiting for your signature…';
    }
    async function finish(){
      if(!current()||finished)return;finished=true;
      await api('/api/agent-wallet/complete',{id:request.id});
      if(!current())return;
      await boot();if(S.modal!==instance)return;
      closeModal();await render();notify(owner?'Agent wallet connected':'Signed in');await afterLogin(next);
    }
    async function poll(){
      clearTimeout(timer);if(!current()||busy||finished)return;busy=true;check.disabled=true;
      try{
        request=await api('/api/agent-wallet/request?id='+encodeURIComponent(proof.id));if(!current())return;paint();
        if(['verified','completed'].includes(request.state)){await finish();return;}
        if(['failed','expired','revoked'].includes(request.state)){
          if(!$('#agent-connect-new'))check.insertAdjacentHTML('afterend','<button class="r-btn primary full" id="agent-connect-new" type="button">Connect again</button>');
          $('#agent-connect-new').onclick=()=>agentWallet(next);return;
        }
      }catch(e){if(current()){finished=false;error.textContent=e.message;}}
      finally{busy=false;if(current()){check.disabled=false;if(!finished&&!['failed','expired','revoked'].includes(request.state))timer=setTimeout(poll,document.hidden?8000:2500);}}
    }
    check.onclick=poll;paint();
    // Paint the exact message and chain before asking the paired Guard runtime.
    (async()=>{
      try{
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));if(!current())return;
        if(proof.state==='prepared'){request=await api('/api/agent-wallet/start',{id:proof.id,messageHash:proof.messageHash});if(!current())return;paint();}
        await poll();
      }catch(e){if(current()){error.textContent=e.message;check.disabled=false;}}
    })();
  }
  const proofKey='rally:agent-wallet-proof',addressKey='rally:agent-wallet-address';
  function saved(key){try{return JSON.parse(sessionStorage.getItem(key)||'null');}catch{return null;}}
  function remember(key,value){try{value?sessionStorage.setItem(key,JSON.stringify(value)):sessionStorage.removeItem(key);}catch{}}
  function manualAgentWallet(next){
    const linking=Boolean(S.boot.me),owner=S.boot.me?.id||null,pending=saved(proofKey),last=saved(addressKey);
    if(pending?.owner===owner&&pending.origin===location.origin&&pending.linking===linking&&typeof pending.proof?.message==='string'&&typeof pending.proof?.id==='string'&&Number.isFinite(pending.proof?.expires)&&pending.proof.expires>Date.now()/1000&&/^0x[0-9a-fA-F]{40}$/.test(pending.address||''))return agentProof(pending,next);
    remember(proofKey,null);
    const address=last?.owner===owner&&/^0x[0-9a-fA-F]{40}$/.test(last.address||'')?last.address:'';
    modal('MetaMask Agent Wallet',`<div class="r-auth-provider">${mark}<span><b>${linking?'Connect your agent wallet':'Sign in with your agent wallet'}</b><small>Monad · No transaction</small></span></div><form id="agent-wallet-form"><label class="r-field">Agent wallet address<input name="address" autocomplete="off" value="${esc(address)}" placeholder="0x…" pattern="0x[0-9a-fA-F]{40}" required></label><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Continue</button></form><details class="r-agent-wallet-setup"><summary>First time here?</summary><p class="r-note">Use the wallet from your existing MetaMask Agent Wallet login.</p><pre class="r-code">mm wallet address</pre><a href="https://docs.metamask.io/agent-wallet/quickstart/" target="_blank" rel="noopener noreferrer">MetaMask setup ${icon('external')}</a></details>`,'r-agent-login');
    const instance=S.modal,form=$('#agent-wallet-form');
    form.onsubmit=async event=>{
      event.preventDefault();const button=$('[type=submit]',form);button.disabled=true;
      try{
        const address=form.elements.address.value.trim();
        const proof=await api(linking?'/api/wallet/challenge':'/api/auth/wallet/challenge',{address});
        if(S.modal!==instance||(S.boot.me?.id||null)!==owner)return;
        if(!Number.isFinite(proof.expires)||proof.expires<=Date.now()/1000)throw new Error('Login request expired. Try again.');
        const pending={owner,origin:location.origin,address,linking,proof};
        remember(addressKey,{owner,address});remember(proofKey,pending);agentProof(pending,next);
      }catch(error){if(form.isConnected){$('.r-form-error',form).textContent=error.message;button.disabled=false;}}
    };
  }
  function agentProof(pending,next){
    const {owner,address,linking,proof}=pending;
    const command="mm wallet sign-message --chain-id 143 --message '"+proof.message.replaceAll("'","'\\''")+"' --wait --json";
    const prompt=`Connect my MetaMask Agent Wallet ${address} to Rally on Monad (chain 143). This is ${linking?'a wallet link':'a sign-in'}, with no transaction or spending permission. Show the exact message below before requesting its signature. Keep my current MetaMask login method and Guard policy. Check for an existing request for this message before signing; if it is pending, watch it rather than signing again. If AWAITING_MFA appears, tell me MetaMask's actual approval instructions. After completion, give me only the signing result JSON, never CLI login tokens or wallet secrets.\n\nExact message:\n${proof.message}\n\nCommand:\n${command}`;
    modal('Connect agent wallet',`<div class="r-auth-provider">${mark}<span><b>${esc(address.slice(0,6)+'…'+address.slice(-4))}</b><small>Monad · No transaction</small></span></div><button class="r-btn primary full" type="button" id="copy-wallet-request">${icon('copy')}Copy request for your agent</button><p class="r-note">Paste it into Codex or your agent. Complete MetaMask’s approval, then paste the result below.</p><form id="agent-wallet-proof"><label class="r-field">Signing result<textarea name="signature" rows="3" maxlength="16384" autocomplete="off" spellcheck="false" placeholder="Paste the result JSON or signature" required></textarea></label><div class="r-form-error" role="alert"></div><button class="r-btn full" type="submit">${linking?'Connect wallet':'Sign in'}</button></form><div class="r-agent-request-meta"><small id="agent-proof-time" role="status"></small><button class="r-text-button" id="agent-wallet-change" type="button">Change wallet</button></div><details class="r-agent-wallet-proof"><summary>Message and command</summary><pre class="r-code">${esc(proof.message)}</pre><button class="r-btn full" type="button" id="copy-wallet-command">${icon('copy')}Copy command</button></details><details class="r-agent-wallet-setup"><summary>Approval not arriving?</summary><p class="r-note">Google or email login: MetaMask sends an email approval link. Mobile QR login: check the MetaMask notifications menu. Keep your original login method; a different method opens a different wallet.</p><a href="https://docs.metamask.io/agent-wallet/troubleshooting/" target="_blank" rel="noopener noreferrer">MetaMask help ${icon('external')}</a></details>`,'r-agent-login');
    const instance=S.modal,form=$('#agent-wallet-proof'),input=form.elements.signature,button=$('[type=submit]',form),status=$('#agent-proof-time');let busy=false,timer;
    function tick(){
      if(S.modal!==instance)return;
      const left=Math.max(0,Math.ceil(proof.expires-Date.now()/1000));
      status.textContent=left?`Request expires in ${Math.floor(left/60)}:${String(left%60).padStart(2,'0')}`:'Request expired. Start a new request after the old MetaMask request has ended.';
      if(!left){button.disabled=true;$('#copy-wallet-request').disabled=true;$('#copy-wallet-command').disabled=true;$('#agent-wallet-change').textContent='New request';remember(proofKey,null);}
      else timer=setTimeout(tick,1000);
    }
    instance.cleanup=()=>clearTimeout(timer);tick();
    const copy=async(text,label)=>{try{await navigator.clipboard.writeText(text);notify(label);}catch{notify('Could not copy. Open the message and command below.');}};
    $('#copy-wallet-request').onclick=()=>copy(prompt,'Agent request copied');
    $('#copy-wallet-command').onclick=()=>copy(command,'Signing command copied');
    $('#agent-wallet-change').onclick=()=>{remember(proofKey,null);manualAgentWallet(next);};
    async function complete(){
      if(busy||S.modal!==instance)return;
      const signature=agentSignature(input.value),error=$('.r-form-error',form);
      if(!signature){error.textContent=input.value.includes('AWAITING_MFA')?'MetaMask approval is still pending. Watch the existing request in your agent.':'Paste the completed signing result or signature. Login tokens are not accepted.';return;}
      if((S.boot.me?.id||null)!==owner){error.textContent='The account changed. Start again.';return;}
      if(proof.expires<=Date.now()/1000){tick();return;}
      busy=true;button.disabled=true;input.value=signature;error.textContent='';button.textContent='Connecting…';
      try{
        await api(linking?'/api/wallet/verify':'/api/auth/wallet/verify',{id:proof.id,signature});
        remember(proofKey,null);S.provider=null;await boot();
        if(S.modal!==instance)return;
        closeModal();await render();notify(linking?'Wallet connected':'Signed in');await afterLogin(next);
      }catch(e){if(form.isConnected){error.textContent=e.message;button.textContent=linking?'Connect wallet':'Sign in';button.disabled=proof.expires<=Date.now()/1000;}}
      finally{busy=false;}
    }
    form.onsubmit=e=>{e.preventDefault();complete();};
    input.onpaste=()=>setTimeout(()=>{if(S.modal===instance&&agentSignature(input.value))complete();},0);
  }
  async function provider(address){if(!cfg()?.linked)return null;try{return await(await sdk()).walletProvider(address);}catch{return null;}}
  function chooseWallet(change=false){
    if(!cfg()?.linked)return false;
    modal('Connect wallet',`<div class="r-auth-methods"><button class="r-btn primary full" type="button" id="privy-wallet">Use Privy wallet</button><button class="r-btn full" type="button" id="external-wallet">${mark}Connect external wallet</button></div><p class="r-note">You approve transactions in your wallet.</p>`);
    $('#external-wallet').onclick=()=>connectWallet(null,true,change);
    $('#privy-wallet').onclick=async event=>{const button=event.currentTarget;button.disabled=true;try{
      const bridge=await sdk();
      if(!bridge.authenticated()){await signIn(true,()=>chooseWallet());return;}
      const provider=await bridge.walletProvider();
      if(provider){await connectWallet(provider,true);return;}
      modal('Create your wallet',`<p class="r-note">Create a Privy wallet for your Rally account on Monad.</p><button class="r-btn primary full" type="button" id="create-privy-wallet">Create wallet</button>`);
      $('#create-privy-wallet').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{const p=await bridge.walletProvider(null,true);if(!p)throw new Error('Wallet unavailable');await connectWallet(p,true);}catch(error){notify(error.message);if(b.isConnected)b.disabled=false;}};
    }catch(error){notify(error.message);if(button.isConnected)button.disabled=false;}};
    return true;
  }
  async function logout(){
    remember(proofKey,null);remember(addressKey,null);
    sessionStorage.removeItem('rally:privy-intent');S.provider=null;
    if(!sdkPromise&&!cfg()?.linked)return;
    loginBusy=true;sessionStorage.setItem('rally:privy-signout-pending','1');
    try{await(await sdk()).logout();sessionStorage.removeItem('rally:privy-signout-pending');}
    catch{notify('Signed out of Rally. Privy sign-out will finish before your next login.');}
    finally{loginBusy=false;}
  }
  async function resume(){
    let intent;try{intent=JSON.parse(sessionStorage.getItem('rally:privy-intent')||'null');}catch{}
    if(!intent)return false;
    sessionStorage.removeItem('rally:privy-intent');
    if(!cfg()?.enabled||intent.path!==location.pathname||intent.owner!==(S.boot.me?.id||null)||Date.now()-intent.created>600000)return false;
    try{const bridge=await sdk();if(!bridge.authenticated())return false;return await signIn(intent.link);}catch(error){notify(error.message);return false;}
  }
  async function handle(action){if(action==='agent-wallet'){agentWallet();return true;}if(action==='privy-link'){await signIn(true);return true;}return false;}
  return {buttons,bind,agentCard,agentWallet,provider,chooseWallet,logout,handle,resume};
}
