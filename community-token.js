export function communityTokenUI(c){
  const {S,$,api,esc,icon,modal:drawModal,closeModal,boot,render,notify,walletReady,receipt,navigate,trade,creator}=c;
  let planning=false,opening=false,shown=null,onboarding=false,continuation=null,replacing=false,watchTimer,watchVersion=0;
  function stopWatch(){clearTimeout(watchTimer);watchVersion++;}
  function modal(...args){
    stopWatch();
    replacing=true;try{drawModal(...args);}finally{replacing=false;}
    if(onboarding)S.modal.ctOnboarding=true;
    S.modal.cleanup=()=>{stopWatch();if(replacing||!onboarding)return;onboarding=false;const next=continuation;continuation=null;if(next)setTimeout(()=>Promise.resolve(next()).catch(e=>notify(e.message)),0);};
  }
  async function ready(){replacing=true;try{return await walletReady();}finally{replacing=false;}}
  const key=()=>`rally:community-request:${S.boot.me?.id}`;
  const pending=()=>{try{return JSON.parse(localStorage.getItem(key())||'null');}catch{return null;}};
  const remember=item=>localStorage.setItem(key(),JSON.stringify(item));
  const forget=()=>localStorage.removeItem(key());
  const deployKey=()=>key()+':factory';
  const deploymentPending=()=>{try{return JSON.parse(localStorage.getItem(deployKey())||'null');}catch{return null;}};
  const rememberDeployment=p=>localStorage.setItem(deployKey(),JSON.stringify(p));
  const forgetDeployment=()=>localStorage.removeItem(deployKey());
  const pct=b=>Number(b||0)/100;
  const amount=(raw,decimals=6)=>{const value=BigInt(raw||0),base=10n**BigInt(decimals);return (Number(value/base)+Number(value%base)/Number(base)).toLocaleString('en-US',{maximumFractionDigits:decimals===6?2:0});};
  const price=raw=>{
    const value=Number(raw);if(!raw||!Number.isFinite(value))return '—';
    const display=value>0&&value<.000001?value.toLocaleString('en-US',{notation:'scientific',maximumSignificantDigits:5}):value.toLocaleString('en-US',{maximumSignificantDigits:5});
    return `<span class="ct-price" title="${esc(raw)} USDC" aria-label="${esc(raw)} USDC"><span aria-hidden="true">${esc(display)}</span></span>`;
  };
  const status=()=>S.boot.communityToken;
  const imageContent=v=>(v.logoURI||v.imageURI)?`<img src="${esc(v.logoURI||v.imageURI)}" alt="${esc(v.name||'Token')} logo" width="52" height="52">`:esc(v.symbol?.slice(0,3)||'+');
  const mark=v=>`<span class="ct-token-mark">${imageContent(v)}</span>`;
  const txLink=hash=>`<a href="https://monadvision.com/tx/${esc(hash)}" target="_blank" rel="noopener noreferrer">View transaction ${icon('external')}</a>`;
  const split=bb=>`<div class="ct-split" aria-hidden="true"><i style="width:${100-pct(bb)}%"></i><i style="width:${pct(bb)}%"></i></div><div class="ct-split-legend"><span>Creator <b data-ct-creator>${100-pct(bb)}%</b></span><span>Buyback <b data-ct-buyback>${pct(bb)}%</b></span></div>`;
  function card(){
    const t=status()?.token,d=status()?.draft;
    return `${creator.account(t,d)}${status()?.deployment?.allowed&&!status().deployment.active?`<button class="ct-account-card" data-action="ct-activate"><span class="ct-token-mark">143</span><span><b>Activate launchpad</b><small>Monad mainnet · Owner wallet</small></span>${icon('chevron')}</button>`:''}`;
  }
  async function current(){const d=await api('/api/community-tokens/me');S.boot.communityToken=d;if(d.token?.asset){const a=S.tokens.find(t=>t.id===d.token.asset.id);if(a)Object.assign(a,d.token.asset);else S.tokens.push(d.token.asset);}return d;}
  async function onboard(next=null){
    if(new URLSearchParams(location.search).get('setup')==='mainnet'&&status()?.deployment?.allowed&&!opening&&!S.modal&&shown!==S.boot.me?.id){shown=S.boot.me.id;await openDeployment();return true;}
    if(location.pathname==='/authorize'||opening||S.modal||S.financialBusy||!status()?.onboarding||shown===S.boot.me?.id)return;
    shown=S.boot.me.id;
    onboarding=true;continuation=next;
    await api('/api/community-tokens/dismiss',{});
    S.boot.communityToken.onboarding=false;
    await open();return true;
  }
  async function open(){
    if(!S.boot.me){notify('Sign in to set up your community');return;}
    if(opening)return;opening=true;
    try{const d=await current();const request=pending();const resolved=request&&d.plans.find(p=>p.id===request.plan&&p.tx===request.hash&&['finalized','failed'].includes(p.state));if(resolved)forget();if(pending())recover();else if(d.token)live(d.token);else form(d);}
    catch(e){notify(e.message);}finally{opening=false;}
  }
  function form(d){
    const inFlight=d.plans.find(p=>['submitted','confirmed'].includes(p.state));
    if(inFlight)return progress(inFlight);
    const owner=S.boot.me.id,official=d.deployment?.allowed;
    const v={...(S.ctDraft?.owner===owner?S.ctDraft.value:d.draft)||{name:official?'Rally':(S.boot.me.name||'').slice(0,32),symbol:official?'RALLY':'',seedUSDC:official?'1':'10',imagePreset:official?'rally':null,imageURI:official?location.origin+'/assets/community-rally.png':null,buybackBps:2000,burnBps:10000,slippageBps:100}};
    let uploading=false,saving=false,uploadVersion=0,previewURL;
    modal('Create community',`<form id="community-token-form"><div class="cr-setup-path" aria-label="Community setup"><span aria-current="step">${icon('launch')}Token</span>${icon('chevron')}<span>${icon('nav-agents')}Agents</span>${icon('chevron')}<span>${icon('feeds')}Algorithms</span></div><div class="ct-create-scroll"><div class="ct-create-main"><div class="ct-network"><span><img src="/assets/MON.png" alt="" width="18" height="18">Monad</span><span>PancakeSwap V2</span></div><div class="ct-create-identity"><button class="ct-image-tile" id="ct-image-pick" type="button" aria-label="${v.imageURI?'Change token image':'Add token image'}"><span data-ct-symbol>${v.imageURI?imageContent(v):icon('image')}</span><span class="ct-image-label">${v.imageURI?'Change':'Add image'}</span></button><input type="file" id="ct-image-file" accept="image/png,image/jpeg,image/webp" aria-label="Upload token image" hidden><div class="ct-create-fields"><label class="r-field">Name<input name="name" value="${esc(v.name)}" maxlength="32" autocomplete="off" placeholder="Your token" required></label><label class="r-field">Ticker<input name="symbol" value="${esc(v.symbol)}" maxlength="10" pattern="[A-Za-z0-9]{2,10}" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="TOKEN" required></label></div></div><p class="ct-image-hint" id="ct-image-status" role="status" data-ready="${Boolean(v.imageURI)}">PNG, JPG or WebP · Up to 5 MB</p><section class="ct-pool-section"><label for="ct-seed-input">Initial pool</label><div class="ct-pool-input"><input id="ct-seed-input" name="seedUSDC" inputmode="decimal" value="${esc(v.seedUSDC)}" autocomplete="off" aria-label="Initial pool in USDC" aria-describedby="ct-seed-error" required><span><img src="/assets/USDC.png" alt="" width="24" height="24">USDC</span></div><div class="ct-seed-presets" aria-label="Initial pool presets">${['1','10','100'].map(n=>`<button type="button" data-ct-seed="${n}" aria-pressed="${Number(v.seedUSDC)===Number(n)}">${n} USDC</button>`).join('')}</div><small id="ct-seed-error" class="ct-field-error" role="status" hidden></small><small>1B tokens · LP tokens go to your wallet</small></section><section class="ct-revenue-section"><label class="ct-slider"><span><b>Algorithm sales</b><output id="ct-buyback-output">${pct(v.buybackBps)}% buyback</output></span><input name="buyback" aria-label="Buyback share of algorithm sales" type="range" min="0" max="100" value="${pct(v.buybackBps)}" step="1"></label>${split(v.buybackBps)}<details class="ct-burn-options"><summary><span>Tokens bought</span><b id="ct-burn-summary">${pct(v.burnBps)}% burn</b>${icon('down')}</summary><label class="ct-slider"><span><b>Burn</b><output id="ct-burn-output">${pct(v.burnBps)}%</output></span><small>The rest goes to your wallet.</small><input name="burn" aria-label="Share of bought tokens to burn" type="range" min="0" max="100" value="${pct(v.burnBps)}" step="1"></label></details></section></div>${creator.preview(v)}</div><div class="ct-create-footer"><div class="r-form-error" role="alert"></div><div class="ct-direct-status" role="status" aria-live="polite"></div><small class="ct-create-terms">Name, ticker and supply are permanent.</small><div class="ct-footer-actions"><button class="r-text-button ct-save-later" id="ct-save-draft" type="button">Save draft</button><button class="r-btn primary full" type="submit">Launch token</button></div></div></form>`,'ct-modal ct-create-modal');
    const f=$('#community-token-form'),button=$('[type=submit]',f),pick=$('#ct-image-pick'),file=$('#ct-image-file'),later=$('#ct-save-draft'),error=$('.r-form-error',f),hint=$('#ct-image-status');
    const attached=()=>f.isConnected&&S.boot.me?.id===owner;
    const values=()=>({...v,name:f.elements.name.value,symbol:f.elements.symbol.value,seedUSDC:f.elements.seedUSDC.value,buybackBps:Number(f.elements.buyback.value)*100,burnBps:Number(f.elements.burn.value)*100});
    const retain=()=>{if(S.boot.me?.id===owner)S.ctDraft={owner,value:values()};};
    const validate=()=>{
      const seed=f.elements.seedUSDC.value.trim();
      f.elements.seedUSDC.setCustomValidity(/^(?:\d+)(?:\.\d{1,6})?$/.test(seed)&&Number(seed)>=1&&Number(seed)<=1000000?'':'Use 1–1,000,000 USDC, with up to 6 decimals');
      f.elements.name.setCustomValidity(f.elements.name.value.trim()?'':'Enter a token name');
      const seedError=$('#ct-seed-error',f),badSeed=Boolean(seed)&&!f.elements.seedUSDC.validity.valid;seedError.hidden=!badSeed;seedError.textContent=badSeed?Number(seed)<1?'Minimum 1 USDC':Number(seed)>1000000?'Maximum 1,000,000 USDC':'Use up to 6 decimals':'';f.elements.seedUSDC.setAttribute('aria-invalid',String(badSeed));
      button.disabled=uploading||saving||!v.imageURI||!f.checkValidity()||!d.config.enabled;
      later.disabled=uploading||saving;
      f.querySelectorAll('[data-ct-seed]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.ctSeed)===Number(seed))));
    };
    f.oninput=()=>{if(f.dataset.pending==='true')return;f.elements.symbol.value=f.elements.symbol.value.toUpperCase();error.textContent='';retain();validate();creator.updatePreview(f,values(),previewURL);};
    f.elements.buyback.oninput=()=>{const n=Number(f.elements.buyback.value);$('#ct-buyback-output').textContent=n+'% buyback';$('[data-ct-buyback]').textContent=n+'%';$('[data-ct-creator]').textContent=100-n+'%';const bars=f.querySelectorAll('.ct-split i');bars[0].style.width=100-n+'%';bars[1].style.width=n+'%';};
    f.elements.burn.oninput=()=>{const n=f.elements.burn.value;$('#ct-burn-output').textContent=n+'%';$('#ct-burn-summary').textContent=n+'% burn';};
    f.querySelectorAll('[data-ct-seed]').forEach(b=>b.onclick=()=>{f.elements.seedUSDC.value=b.dataset.ctSeed;f.dispatchEvent(new Event('input',{bubbles:true}));});
    pick.onclick=()=>file.click();file.onchange=async()=>{
      const chosen=file.files[0];if(!chosen)return;
      const version=++uploadVersion,previous={imageId:v.imageId,imagePreset:v.imagePreset,imageURI:v.imageURI};
      try{
        if(!['image/png','image/jpeg','image/webp'].includes(chosen.type)||!chosen.size||chosen.size>5*1024*1024)throw Error('Choose a PNG, JPG or WebP under 5 MB');
        uploading=true;pick.disabled=true;validate();hint.dataset.ready='false';hint.textContent='Uploading image…';error.textContent='';
        if(previewURL)URL.revokeObjectURL(previewURL);previewURL=URL.createObjectURL(chosen);$('[data-ct-symbol]',f).innerHTML=`<img src="${previewURL}" alt="Token image preview">`;$('.ct-image-label',f).textContent='Uploading…';creator.updatePreview(f,values(),previewURL);
        const response=await fetch('/api/media',{method:'POST',credentials:'same-origin',headers:{'Content-Type':chosen.type,'X-Rally-Request':'1'},body:chosen});
        const media=await response.json();if(!response.ok)throw Error(media.message||'Image upload failed');
        if(owner!==S.boot.me?.id)throw Error('Account changed. Choose your image again');
        if(!/^[0-9a-f]{32}$/.test(media.id)||!['image/png','image/jpeg','image/webp'].includes(media.mime))throw Error('Invalid image upload');
        if(version!==uploadVersion)return;
        v.imageId=media.id;v.imagePreset=null;v.imageURI=location.origin+'/media/'+media.id;
        if(attached()){$('[data-ct-symbol]',f).innerHTML=imageContent(v);$('.ct-image-label',f).textContent='Change';pick.setAttribute('aria-label','Change token image');hint.dataset.ready='true';hint.textContent='Image ready';retain();creator.updatePreview(f,values());}
      }catch(e){if(attached()&&version===uploadVersion){Object.assign(v,previous);$('[data-ct-symbol]',f).innerHTML=v.imageURI?imageContent(v):icon('image');$('.ct-image-label',f).textContent=v.imageURI?'Change':'Add image';hint.dataset.ready=String(Boolean(v.imageURI));hint.textContent='PNG, JPG or WebP · Up to 5 MB';error.textContent=e.message;creator.updatePreview(f,values());}}
      finally{if(version===uploadVersion){uploading=false;if(attached()){pick.disabled=false;validate();}if(previewURL){URL.revokeObjectURL(previewURL);previewURL=null;}}file.value='';}
    };
    const clean=S.modal.cleanup;S.modal.cleanup=()=>{retain();if(previewURL)URL.revokeObjectURL(previewURL);clean?.();};
    async function save(launch){
      if(uploading||saving||S.financialBusy)return;
      validate();if(!f.reportValidity())return;if(launch&&(!v.imageURI||!d.config.enabled))return;
      saving=true;retain();const original=button.textContent;button.textContent=launch?'Preparing launch…':'Saving…';validate();
      const controls=[...f.elements].filter(el=>el!==button&&el!==later),disabled=controls.map(el=>el.disabled);controls.forEach(el=>el.disabled=true);
      try{
        const next=await api('/api/community-tokens/save',values());if(!attached())return;S.boot.communityToken=next;S.ctDraft={owner,value:next.draft};
        if(launch)await makePlan('launch');else{await handle('ct-later');notify('Draft saved');}
      }catch(e){if(attached())error.textContent=e.message;}
      finally{saving=false;if(attached()){controls.forEach((el,i)=>el.disabled=disabled[i]);button.textContent=original;validate();}}
    }
    f.onsubmit=e=>{e.preventDefault();save(true);};later.onclick=()=>save(false);
    if(!d.config.enabled)$('.ct-direct-status',f).textContent='Drafts are available. Mainnet launch is temporarily unavailable.';
    retain();validate();creator.updatePreview(f,values());
  }
  async function makePlan(kind,data={}){
    if(S.financialBusy||planning)return;planning=true;
    const root=$('.ct-modal'),button=root?.querySelector('#community-token-form [type=submit],#ct-policy-submit'),actor=S.boot.me?.id;
    const controls=[...button?.closest('form')?.elements||[]].filter(el=>el!==button),disabled=controls.map(el=>el.disabled);controls.forEach(el=>el.disabled=true);
    if(button)button.disabled=true;
    try{
      if(!await ready()||!root?.isConnected||actor!==S.boot.me?.id)return;
      const p=await api('/api/community-tokens/plan',{kind,...data});
      if(root.isConnected&&actor===S.boot.me?.id)await send(p,button);
    }catch(e){const error=root?.querySelector('.r-form-error');if(error?.isConnected)error.textContent=e.message;else notify(e.message);}
    finally{planning=false;if(button?.isConnected){controls.forEach((el,i)=>el.disabled=disabled[i]);button.disabled=false;}}
  }
  async function send(p,b){
    if(S.financialBusy||!b?.isConnected)return;
    S.financialBusy=true;
    const root=b.closest('.ct-modal'),f=b.closest('form'),actor=S.boot.me?.id,wallet=S.boot.wallet,storageKey=key(),original=b.textContent,error=root.querySelector('.r-form-error');
    let text=root.querySelector('.ct-direct-status');if(!text){text=document.createElement('div');text.className='ct-direct-status';text.setAttribute('role','status');text.setAttribute('aria-live','polite');b.before(text);}
    const fingerprint=()=>JSON.stringify(f?[...f.elements].filter(e=>e.name).map(e=>[e.name,e.value]):[]),initial=fingerprint();
    const alive=()=>root.isConnected&&actor===S.boot.me?.id&&wallet===S.boot.wallet&&fingerprint()===initial;
    const check=()=>{if(!alive())throw Error('Token settings or wallet changed. Try again.');};
    const frozen=[...f?.elements||[]].filter(e=>e!==b),disabled=frozen.map(e=>e.disabled);frozen.forEach(e=>e.disabled=true);if(f)f.dataset.pending='true';b.disabled=true;text.setAttribute('aria-busy','true');
    const terms=v=>JSON.stringify(['name','symbol','seedRaw','imageId','imagePreset','buybackBps','burnBps','slippageBps'].map(k=>v[k]??null)),originalTerms=terms(p.summary);
    const paint=(message,label=message)=>{if(alive()){text.textContent=message;b.textContent=label;}};
    const refresh=async()=>{check();const next=await api('/api/community-tokens/plan',{kind:p.kind,...vForPolicy(p)});check();if(terms(next.summary)!==originalTerms||!Number.isFinite(next.expires)||next.expires<=Date.now()/1000)throw Error('Token settings changed. Open your draft again.');p=next;};
    let requested=false,approvals=0,refreshes=0;
    try{
      if(pending())throw Error('A wallet request is unresolved. Check its transaction first.');
      localStorage.setItem(storageKey,'null');
      for(;;){
        check();if(!Number.isFinite(p.expires)||p.expires<=Date.now()/1000){if(refreshes++>=1)throw Error('Launch expired. Try again.');await refresh();}
        paint(p.kind==='launch'?'Preparing launch…':'Updating allocation…','Preparing…');const r=await api('/api/community-tokens/prepare',{plan:p.id});check();
        if(p.expires<=Date.now()/1000){if(refreshes++>=1)throw Error('Launch expired. Try again.');await refresh();continue;}
        if(r.approval&&approvals)throw Error('USDC approval is not ready. Try again.');
        const tx=r.approval||r.transaction,target=r.approval?status().config.quoteToken:p.kind==='launch'?status().config.factory:status().token?.vault;
        if(target&&tx?.to?.toLowerCase()!==target.toLowerCase())throw Error('Wallet transaction target does not match this token.');
        if(!tx||tx.from?.toLowerCase()!==wallet.toLowerCase()||Number(tx.chainId)!==143||!/^0x[0-9a-f]{40}$/i.test(tx.to)||!/^0x(?:[0-9a-f]{2})+$/i.test(tx.data)||BigInt(tx.value||'0x0')!==0n)throw Error('Wallet transaction does not match this launch.');
        const accounts=await S.provider.request({method:'eth_accounts'}),chain=await S.provider.request({method:'eth_chainId'});check();
        if(accounts[0]?.toLowerCase()!==wallet.toLowerCase()||Number(chain)!==143)throw Error('Connect the original wallet on Monad.');
        if(p.expires<=Date.now()/1000){if(refreshes++>=1)throw Error('Launch expired. Try again.');await refresh();continue;}
        const item={plan:p.id,wallet,approval:Boolean(r.approval),created:Date.now()};
        localStorage.setItem(storageKey,JSON.stringify(item));requested=true;
        paint((item.approval?'Approve USDC':p.kind==='launch'?'Launch token':'Save allocation')+' · '+r.estimatedGasCostMON+' MON fee',item.approval?'Approve USDC':'Confirm in wallet');
        const hash=await S.provider.request({method:'eth_sendTransaction',params:[tx]});
        if(!/^0x[0-9a-fA-F]{64}$/.test(hash))throw Error('Check the transaction in your wallet.');
        localStorage.setItem(storageKey,JSON.stringify({...item,hash}));
        if(item.approval){
          paint('USDC approval pending…','Approving…');await receipt(hash);
          let checked;for(let i=0;i<8;i++){checked=await api('/api/community-tokens/approval/check',{plan:p.id,tx:hash});if(checked.state!=='pending')break;await new Promise(resolve=>setTimeout(resolve,1500));}
          if(checked.state!=='confirmed')throw Error('Approval '+checked.state+'. Check the same hash.');
          localStorage.removeItem(storageKey);requested=false;approvals++;check();paint('Opening launch in wallet…','Confirm in wallet');await refresh();continue;
        }
        paint('Confirming on Monad…','Confirming…');const result=await api('/api/community-tokens/record',{plan:p.id,tx:hash});
        if(alive())await progress(result);return;
      }
    }catch(e){
      if(e.code===4001){localStorage.removeItem(storageKey);requested=false;if(error?.isConnected)error.textContent='Wallet request canceled';}
      else if(requested){if(actor===S.boot.me?.id&&root.isConnected)recover();else notify('Transaction needs checking. Reopen your community token.');}
      else if(error?.isConnected)error.textContent=e.message;else notify(e.message);
    }finally{
      S.financialBusy=false;if(f)delete f.dataset.pending;if(b.isConnected){frozen.forEach((e,i)=>e.disabled=disabled[i]);b.disabled=false;b.textContent=original;text.removeAttribute('aria-busy');if(!requested)text.textContent='';}
    }
  }
  const vForPolicy=p=>p.kind==='policy'?{buybackBps:p.summary.buybackBps,burnBps:p.summary.burnBps,slippageBps:p.summary.slippageBps}:{};
  function recover(){
    const p=pending();if(!p)return open();
    modal('Check your wallet request',`<p class="ct-caption">Verify the existing transaction before trying again.</p>${p.hash?txLink(p.hash):''}<form id="ct-recovery"><label class="r-field">Transaction hash<input name="hash" value="${esc(p.hash||'')}" placeholder="0x…" pattern="0x[0-9a-fA-F]{64}" required></label><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Check transaction</button></form>`,'ct-modal');
    const f=$('#ct-recovery');f.onsubmit=async e=>{e.preventDefault();const b=$('[type=submit]',f);b.disabled=true;try{if(S.boot.wallet!==p.wallet)throw new Error('Connect the original wallet');const r=await api(p.approval?'/api/community-tokens/approval/check':'/api/community-tokens/record',{plan:p.plan,tx:f.elements.hash.value});if(p.approval&&r.state==='pending')throw new Error('Still pending. Check the same hash later.');forget();await boot();if(p.approval){notify(r.state==='confirmed'?'USDC approved. Your draft is ready.':'Allowance '+r.state);await open();}else await progress(r);}catch(e){if(f.isConnected){$('.r-form-error',f).textContent=e.message;b.disabled=false;}}};
  }
  async function progress(p){
    stopWatch();
    if(['finalized','failed'].includes(p.state)){
      if(pending()?.plan===p.id)forget();
      const d=await current();await render();
      if(p.state==='finalized'&&d.token){live(d.token);S.ctDraft=null;notify(p.kind==='policy'?'Allocation updated':'RALLY token active'.replace('RALLY',d.token.symbol));return;}
    }
    modal(p.state==='failed'?'Transaction failed':'Transaction submitted',`<div class="ct-status" role="status">${p.state==='failed'?'Transaction did not succeed':'Confirming on Monad…'}</div>${p.tx?txLink(p.tx):''}<p class="ct-caption">${p.state==='failed'?'Your wallet can show the failure details.':'This view updates automatically. You can close it safely.'}</p><div class="r-form-error" role="alert"></div><button class="r-text-button ct-later" data-action="ct-activity">View activity</button>`,'ct-modal');
    if(p.state==='failed'||!p.tx)return;
    const version=watchVersion,owner=S.boot.me?.id,host=$('.ct-modal');let attempts=0;
    const check=async()=>{
      if(version!==watchVersion||!host.isConnected||owner!==S.boot.me?.id)return;
      try{const next=await api('/api/community-tokens/record',{plan:p.id,tx:p.tx});if(version!==watchVersion)return;if(['finalized','failed'].includes(next.state)){await progress(next);return;}$('.r-form-error',host).textContent='';}
      catch(e){if(version===watchVersion&&host.isConnected)$('.r-form-error',host).textContent=e.message;}
      if(version===watchVersion)watchTimer=setTimeout(check,Math.min(8000,1500+attempts++*500));
    };
    watchTimer=setTimeout(check,1500);
  }
  function live(t){
    const v=t.stats;
    modal(esc(t.name),`<div class="ct-intro">${mark(t)}<span><b>${esc(t.symbol)}</b><small>Monad · PancakeSwap V2</small><span class="ct-active" role="status">Active</span></span></div>${split(t.buybackBps)}<div class="ct-metrics"><span><small>Price · USDC</small><b>${price(v.referencePriceUSDC)}</b></span><span><small>Market cap · USDC</small><b>${v.referenceMarketCapUSDC?esc(Number(v.referenceMarketCapUSDC).toLocaleString('en-US',{maximumFractionDigits:2})):'—'}</b></span><span><small>Sales</small><b>${amount(v.grossRevenue)} USDC</b></span><span><small>Buybacks spent</small><b>${amount(v.quoteSpent)} USDC</b></span><span><small>Tokens burned</small><b>${amount(v.tokensBurned,18)}</b></span><span><small>Queued buybacks</small><b>${amount(v.pendingBuyback)} USDC</b></span></div><p class="ct-status" data-buyback-state="${creator.buybackStatus(t).state}">${esc(creator.buybackStatus(t).text)} · ${pct(t.burnBps)}% burn</p><div class="ct-secondary"><button class="r-btn primary" data-action="cr-community-open" data-id="posts">Open community</button><button class="r-btn" data-action="trade" data-id="${esc(t.address)}">Trade</button></div><div class="ct-secondary"><button class="r-btn ct-buy" data-action="ct-test-buy">Buy · 0.01 USDC</button><button class="r-btn ct-sell" data-action="ct-sell">Sell</button></div><div class="cr-token-tools"><button class="r-text-button" data-action="cr-community-open" data-id="agents">Agents</button><button class="r-text-button" data-action="cr-community-open" data-id="algorithms">Algorithms</button><button class="r-text-button" data-nav="earnings">Earnings</button><button class="r-text-button" data-action="cr-share" data-id="profile">Share profile</button><button class="r-text-button" data-action="ct-policy">Edit allocation</button></div><a class="ct-contract" href="https://monadvision.com/token/${esc(t.address)}" target="_blank" rel="noopener noreferrer">Token contract ${icon('external')}</a>`,'ct-modal');
  }
  function policy(){
    const t=status().token;
    modal('Revenue allocation',`<form id="ct-policy-form">${[['buybackBps','Buyback',t.buybackBps],['burnBps','Burn',t.burnBps]].map(([name,label,value])=>`<label class="r-field">${label} · %<input name="${name}" type="number" min="0" max="100" step="1" value="${pct(value)}" required></label>`).join('')}<p class="ct-caption">Buyback is a share of sales. Burn is a share of tokens bought.</p><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit" id="ct-policy-submit">Save allocation</button></form>`,'ct-modal');
    $('#ct-policy-form').onsubmit=e=>{e.preventDefault();const f=e.currentTarget;makePlan('policy',{buybackBps:Number(f.elements.buybackBps.value)*100,burnBps:Number(f.elements.burnBps.value)*100,slippageBps:Number(status().token.stats.slippageBps)});};
  }
  async function openDeployment(){
    if(!S.boot.me){notify('Connect the launchpad owner wallet');return;}
    try{
      const d=await current();
      if(!d.deployment?.allowed)throw Error('Connect the authorized launchpad wallet');
      const request=deploymentPending();if(request)return recoverDeployment(request);
      const inFlight=d.deployment.plans.find(p=>['submitted','confirmed'].includes(p.state));
      if(inFlight)return deploymentProgress(inFlight);
      if(d.deployment.active)return deploymentProgress(d.deployment.plans.find(p=>p.state==='finalized')||{state:'finalized',factory:d.deployment.factory});
      modal('Activate launchpad',`<div class="ct-intro"><span class="ct-token-mark">143</span><span><b>Monad mainnet</b><small>Community tokens · USDC pools</small></span></div><dl class="ct-facts"><div><dt>Contract</dt><dd>RallyCommunityFactory</dd></div><div><dt>Pool venue</dt><dd>PancakeSwap V2</dd></div><div><dt>Wallet</dt><dd>${esc(S.boot.wallet)}</dd></div></dl><p class="ct-caption">Deploy the shared launchpad. This step creates no community tokens and transfers no USDC.</p><form id="ct-deployment-form"><label class="r-field">Maximum network fee · MON<input name="cap" value="0.5" inputmode="decimal" required></label><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Review deployment</button></form>`,'ct-modal');
      const f=$('#ct-deployment-form');f.onsubmit=async e=>{e.preventDefault();const b=$('[type=submit]',f);b.disabled=true;try{if(!await ready())return;const p=await api('/api/community-deployment/plan',{maxGasCostMON:f.elements.cap.value});reviewDeployment(p);}catch(e){if(f.isConnected)$('.r-form-error',f).textContent=e.message;else notify(e.message);}finally{if(b.isConnected)b.disabled=false;}};
    }catch(e){notify(e.message);}
  }
  function reviewDeployment(p){
    const v=p.summary;
    modal('Review mainnet deployment',`<div class="ct-intro"><span class="ct-token-mark">143</span><span><b>Rally launchpad</b><small>One contract · Monad</small></span></div><dl class="ct-facts"><div><dt>Network fee estimate</dt><dd>${esc(v.estimatedGasCostMON)} MON</dd></div><div><dt>Your fee limit</dt><dd>${esc(v.maxGasCostMON)} MON</dd></div><div><dt>USDC transferred</dt><dd>0</dd></div><div><dt>Wallet</dt><dd>${esc(v.wallet)}</dd></div><div><dt>Source</dt><dd>${esc(v.sourceHash.slice(0,12))}</dd></div></dl><p class="ct-caption">Token launches unlock after finality and contract verification. Community liquidity and keeper funding are separate.</p><div class="r-form-error" role="alert"></div><button class="r-btn primary full" id="ct-deploy-confirm">Deploy in wallet</button>`,'ct-modal');
    $('#ct-deploy-confirm').onclick=()=>sendDeployment(p);
  }
  async function sendDeployment(p){
    if(Number.isFinite(p.expires)&&p.expires<=Date.now()/1000&&!deploymentPending()){
      try{reviewDeployment(await api('/api/community-deployment/plan',{maxGasCostMON:p.summary.maxGasCostMON}));}catch(e){notify(e.message);}return;
    }
    if(S.financialBusy)return;S.financialBusy=true;const b=$('#ct-deploy-confirm'),error=$('.ct-modal .r-form-error');b.disabled=true;let requested=false;
    try{
      if(deploymentPending())throw Error('Check the unresolved deployment before trying again');
      if(!await ready()||!b.isConnected)return;
      const actor=S.boot.me.id,wallet=S.boot.wallet,r=await api('/api/community-deployment/prepare',{plan:p.id});
      const accounts=await S.provider.request({method:'eth_accounts'}),chain=await S.provider.request({method:'eth_chainId'});
      if(actor!==S.boot.me?.id||wallet!==S.boot.wallet||accounts[0]?.toLowerCase()!==wallet||r.transaction.from!==wallet||Number(chain)!==143)throw Error('Wallet changed. Review again.');
      const item={plan:p.id,wallet,created:Date.now()};rememberDeployment(item);requested=true;b.textContent='Confirm in wallet';
      const hash=await S.provider.request({method:'eth_sendTransaction',params:[r.transaction]});rememberDeployment({...item,hash});
      const result=await api('/api/community-deployment/record',{plan:p.id,tx:hash});forgetDeployment();await boot();deploymentProgress(result);
    }catch(e){if(e.code===4001){forgetDeployment();if(error?.isConnected)error.textContent='Wallet request canceled';}else if(requested)recoverDeployment(deploymentPending());else if(error?.isConnected)error.textContent=e.message;else notify(e.message);}
    finally{S.financialBusy=false;if(b?.isConnected){b.disabled=false;b.textContent='Deploy in wallet';}}
  }
  function recoverDeployment(p){
    modal('Check deployment request',`<p class="ct-caption">Check the existing wallet transaction. No new deployment will be sent.</p>${p.hash?txLink(p.hash):''}<form id="ct-deployment-recovery"><label class="r-field">Transaction hash<input name="hash" value="${esc(p.hash||'')}" pattern="0x[0-9a-fA-F]{64}" required></label><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Check transaction</button></form>`,'ct-modal');
    const f=$('#ct-deployment-recovery');f.onsubmit=async e=>{e.preventDefault();const b=$('[type=submit]',f);b.disabled=true;try{if(S.boot.wallet!==p.wallet)throw Error('Connect the original wallet');const result=await api('/api/community-deployment/record',{plan:p.plan,tx:f.elements.hash.value});forgetDeployment();await boot();deploymentProgress(result);}catch(e){if(f.isConnected){$('.r-form-error',f).textContent=e.message;b.disabled=false;}}};
  }
  function deploymentProgress(p){
    const active=p.state==='finalized';
    modal(active?'Launchpad active':p.state==='failed'?'Deployment failed':'Deployment submitted',`<div class="ct-status" role="status">${active?'Contract verified on Monad':p.state==='failed'?'Transaction did not succeed':'Waiting for finality. The launchpad stays locked until verified.'}</div>${p.tx?txLink(p.tx):''}${active?`<button class="r-btn primary full" data-action="community-token">Set up your community token</button>`:'<button class="r-btn primary full" id="ct-deploy-refresh">Check status</button>'}`,'ct-modal');
    if(!active)$('#ct-deploy-refresh').onclick=async()=>{try{const result=await api('/api/community-deployment/record',{plan:p.id,tx:p.tx});await boot();deploymentProgress(result);}catch(e){notify(e.message);}};
  }
  async function handle(action,id){
    if(action==='ct-activity'){closeModal();await navigate('activity');return true;}
    if(action==='ct-activate'){await openDeployment();return true;}
    if(action==='community-token'){await open();return true;}
    if(action==='ct-edit'){form(status());return true;}
    if(action==='ct-policy'){policy();return true;}
    if(action==='ct-test-buy'||action==='ct-sell'){const t=status()?.token;if(!t)return true;closeModal();trade(t.address,null,action==='ct-sell'?'sell':'buy',action==='ct-test-buy'?{amount:'0.01'}:null);return true;}
    if(action==='ct-later'||action==='ct-done'){await api('/api/community-tokens/dismiss',{});replacing=true;try{closeModal();}finally{replacing=false;}onboarding=false;const next=continuation;continuation=null;await boot();await render();if(next)await next();return true;}
    if(action==='ct-community'){closeModal();S.community=id;await navigate('community');return true;}
    return false;
  }
  return {onboard,open,card,handle,defer:next=>{if(S.modal?.ctOnboarding){continuation=next;return true;}return false;}};
}
