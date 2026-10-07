// Inline order presentation. Calldata, exact allowance and expiry stay server-validated.
export function swipeTrade(c){
  const {S,$,api,esc,token,finance,needAccount,walletReady}=c;
  let ticket=null,timer,clock,poll,routePoll,controller;
  const drafts=S.swipeDrafts ||= new Map(),budgets=S.swipeBudgets ||= new Map();
  const positive=v=>/^(?:\d+\.?\d*|\.\d+)$/.test(v||'')&&Number.isFinite(Number(v))&&Number(v)>0;
  const owner=()=>JSON.stringify([S.boot.me?.id,S.boot.wallet]);
  const label=side=>({buy:'Buy',sell:'Sell',long:'Long',short:'Short',predict:'Predict price'}[side]||side);
  function values(s){return Object.fromEntries([...s.fields.querySelectorAll('[name]')].map(el=>[el.name,el.value]));}
  function remember(s){
    if(!s?.fields)return;
    drafts.delete(s.key);drafts.set(s.key,{side:s.side,values:values(s),hash:s.hash,approval:s.approval,lastPlanId:s.lastPlanId,status:s.statusMessage,phase:s.phase,completed:s.completed});
    if(drafts.size>48)drafts.delete(drafts.keys().next().value);
  }
  function dispose(){clearTimeout(timer);clearInterval(clock);clearTimeout(poll);clearTimeout(routePoll);controller?.abort();if(ticket){remember(ticket);ticket.version++;ticket.inputEvents?.abort();}ticket=null;}
  function mount(item,card,isActive){
    if(ticket?.card===card)return;
    dispose();const root=$('[data-swipe-ticket]',card);
    if(!root||!(item.asset||item.pool||item.market)||item.kind==='prediction'&&(item.pool.close<=Date.now()/1000||!item.pool.stakeReviewed||!item.pool.predictionReviewed))return;
    const s=ticket={item,card,root,isActive,side:item.kind==='spot'?'buy':item.kind==='perps'?'long':'predict',version:0,plan:null,busy:false,loading:false,hash:null};
    s.ownerScope=owner();s.key=JSON.stringify([s.ownerScope,item.kind,item.post?.id,item.market?.id,item.pool?.id,item.asset?.id]);
    s.current=()=>ticket===s&&root.isConnected&&S.view==='swipe'&&!S.modal&&!S.trade&&isActive()&&s.ownerScope===owner();
    const market=item.market,leverage=market?.venue==='Pingu'?Math.min(10,market.maxLeverage||1):5;
    root.innerHTML=`<div class="r-quick-fields"></div><div class="r-quick-summary" role="status" aria-live="polite"></div><div class="r-quick-error" role="alert"></div><div class="r-quick-status" role="status" aria-live="polite"></div>`;
    s.inputEvents=new AbortController();const listener={signal:s.inputEvents.signal};
    s.fields=$('.r-quick-fields',root);s.summary=$('.r-quick-summary',root);s.error=$('.r-quick-error',root);s.status=$('.r-quick-status',root);
    s.fields.innerHTML=item.kind==='spot'?`<label class="r-quick-amount"><span>Amount</span><input name="amount" inputmode="decimal" autocomplete="off" placeholder="0.00" aria-label="Swipe order amount"><b data-quick-unit>MON</b></label><div class="r-quick-presets" role="group" aria-label="Swipe amounts"></div>`:item.kind==='prediction'?`<label class="r-quick-amount"><span>Your price</span><input name="price" inputmode="decimal" autocomplete="off" placeholder="0.00" aria-label="Prediction price"><b>USD</b></label><small class="r-quick-stake">Stake ${esc(item.pool.stake)} ${esc(item.pool.stakeAsset)} · ${item.pool.feeBps/100}% fee</small>`:`<div class="r-quick-perp"><label class="r-quick-amount"><span>${market.venue==='Pingu'?'Margin':'Quantity'}</span><input name="${market.venue==='Pingu'?'amount':'quantity'}" inputmode="decimal" autocomplete="off" placeholder="0.00" aria-label="${market.venue==='Pingu'?'Margin amount':'Order quantity'}"><b>${esc(market.venue==='Pingu'?'MON':market.baseSymbol||market.symbol)}</b></label>${market.venue==='LeverUp'?'<label class="r-quick-amount"><span>Margin</span><input name="amount" inputmode="decimal" placeholder="0.00" aria-label="Margin amount"><b>USDC</b></label>':market.venue==='Drake'?'<label class="r-quick-option">Margin<select name="portfolioType"><option value="imp">Isolated</option><option value="cmp">Cross</option></select></label>':`<label class="r-quick-option">Leverage<select name="leverage">${Array.from({length:leverage},(_,i)=>'<option value="'+(i+1)+'">'+(i+1)+'×</option>').join('')}</select></label>`}</div>${market.venue==='LeverUp'?'<small class="r-quick-stake">0.5% slippage · Margin settles in LVUSD</small>':'<details class="r-quick-options"><summary>Protection price</summary><label class="r-quick-amount"><span>Limit</span><input name="limit" inputmode="decimal" aria-label="Protection price"><b>USD</b></label></details>'}`;
    root.addEventListener('input',changed,listener);root.addEventListener('change',changed,listener);
    root.addEventListener('click',e=>{const b=e.target.closest('[data-quick-amount],[data-quick-retry],[data-quick-collateral],[data-quick-recover],[data-quick-new]');if(!b||s.busy)return;
      if(b.hasAttribute('data-quick-new')){if(!s.completed)return;s.hash=null;s.completed=false;s.plan=null;s.version++;clearTimeout(poll);presentStatus(s,'');s.error.textContent='';sync(s);load(s);return;}
      if(s.hash&&s.hash!=='unknown')return;
      if(b.hasAttribute('data-quick-amount')){const input=$('[name=amount]',root);input.value=b.dataset.quickAmount;changed();if(document.activeElement===input)input.blur();if(!s.plan&&!s.loading)load(s);}
      else if(b.hasAttribute('data-quick-recover'))recover(s,b);else if(b.hasAttribute('data-quick-collateral'))finance.handle('perpl-account');else load(s);
    },listener);
    root.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.isComposing&&e.target.matches('input')){e.preventDefault();if(e.target.name==='recovery-hash')recover(s,$('[data-quick-recover]',root));else act(s.side,false);}},listener);
    const draft=drafts.get(s.key);if(draft)s.side=draft.side;
    defaults(s,true);if(draft){for(const [name,value] of Object.entries(draft.values||{})){const input=$('[name="'+name+'"]',s.fields);if(input)input.value=value;}Object.assign(s,{hash:draft.hash,approval:draft.approval,lastPlanId:draft.lastPlanId,completed:draft.completed});}
    s.intent=JSON.stringify([owner(),args(s)]);idle(s);
    if(finance.uncertainInline?.()){s.hash='unknown';presentStatus(s,'Earlier wallet result unknown','unknown');recoveryForm(s);}
    else if(s.hash==='unknown'){s.hash=null;}
    else if(s.hash){presentStatus(s,draft.status||'Submitted',draft.phase||'pending');if(!s.completed&&!s.approval)pollState(s);}
    sync(s);if(!s.hash&&valid(s))timer=setTimeout(()=>load(s),250);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden){tick(s);if(s.hash&&!s.approval&&!s.completed)pollState(s);}},listener);
    clock=setInterval(()=>tick(s),1000);
  }
  function tick(s){
    if(document.hidden||!s.root.isConnected||S.view!=='swipe'||!s.isActive())return;
    if(s.ownerScope!==owner()&&!s.busy){const {item,card,isActive}=s;dispose();mount(item,card,isActive);return;}
    if(!s.current()||s.busy||s.hash||s.loading)return;
    const expires=s.plan?.expires||s.referenceExpires;if(!Number.isFinite(expires))return;
    if(expires-Date.now()/1000<=3&&valid(s)){
      if((s.refreshes||0)<2){s.refreshes=(s.refreshes||0)+1;load(s,true);}
      else if(expires<=Date.now()/1000){s.plan=null;s.referenceExpires=null;idle(s);s.summary.dataset.state='expired';s.summary.innerHTML='<div><span>Quote expired</span><button data-quick-retry>Refresh</button></div>';sync(s);}
    }
  }
  function defaults(s,restore=false){
    const unit=s.item.kind==='spot'?(s.item.asset.nadfun?(s.side==='sell'?s.item.asset.symbol:s.item.asset.quoteSymbol||'MON'):token(args(s).input)?.symbol||s.item.asset.symbol):null;
    if(unit){s.payUnit=unit;$('[data-quick-unit]',s.root).textContent=unit;const amounts=s.side==='buy'?(unit==='MON'?[1,5,10]:['USDC','AUSD'].includes(unit)?[5,10,25]:[]):[];$('.r-quick-presets',s.root).innerHTML=amounts.map(n=>`<button type="button" data-quick-amount="${n}" aria-label="${n} ${esc(unit)}" aria-pressed="false">${n}</button>`).join('');if(restore&&s.side==='buy')$('[name=amount]',s.fields).value=budgets.get(s.ownerScope+':'+unit)||'';}
    const input=$('[name=limit]',s.root),m=s.item.market;
    if(input)input.value=m.mark?Number(m.mark*(s.side==='short' ? 0.995 : 1.005)).toFixed(Number.isInteger(m.priceDecimals)?m.priceDecimals:6):'';
  }
  function args(s){
    const item=s.item,fields=values(s),context=item.post?{post:item.post.id,feed:S.boot.activeFeed}:null;
    if(item.kind==='spot'){
      if(item.asset.nadfun)return {venue:'nadfun',kind:s.side,token:item.asset.id,amount:fields.amount,slippage:50,context};
      const other=item.asset.id==='MON'?'0x754704bc059f8c67012fed69bc8a327a5aafb603':'MON';
      return {input:s.side==='sell'?item.asset.id:other,output:s.side==='sell'?other:item.asset.id,amount:fields.amount,slippage:50,context};
    }
    if(item.kind==='prediction')return {venue:'castora',kind:'predict',pool:item.pool.id,price:fields.price};
    const venue=item.market.venue.toLowerCase();return {venue,kind:'order',market:item.market.id,direction:s.side,...fields,...(venue==='leverup'?{collateral:'USDC',slippage:50}:venue==='perpl'?{reduceOnly:false}:{}),context};
  }
  function available(s){return s.item.kind==='prediction'?s.item.pool.close>Date.now()/1000&&s.item.pool.stakeReviewed&&s.item.pool.predictionReviewed:s.item.kind==='perps'?s.item.market.open&&!s.item.market.stale:true;}
  function valid(s){return [...s.fields.querySelectorAll('input')].every(el=>positive(el.value));}
  function idle(s){const unit=s.item.kind==='spot'?(s.item.asset.nadfun?(s.side==='buy'?s.item.asset.symbol:s.item.asset.quoteSymbol||'MON'):token(args(s).output)?.symbol):s.item.kind==='prediction'?'USD':s.item.market.baseSymbol||s.item.market.symbol;s.summary.dataset.state='idle';s.summary.removeAttribute('aria-busy');s.summary.innerHTML=`<div><span>${s.item.kind==='spot'?'Receive':s.item.kind==='prediction'?'Prediction':'Size'}</span><b>— ${esc(unit||'')}</b></div><small>&nbsp;</small>`;}
  function changed(){const s=ticket;if(!s||s.busy||s.hash)return;const intent=JSON.stringify([owner(),args(s)]);if(intent===s.intent)return;s.intent=intent;clearTimeout(timer);controller?.abort();s.version++;s.plan=null;s.referenceExpires=null;s.loading=false;s.refreshes=0;idle(s);s.error.textContent='';presentStatus(s,'');if(s.item.kind==='spot'&&s.side==='buy'&&positive(values(s).amount)){budgets.set(s.ownerScope+':'+s.payUnit,values(s).amount);if(budgets.size>24)budgets.delete(budgets.keys().next().value);}remember(s);sync(s);if(valid(s))timer=setTimeout(()=>load(s),300);}
  function sync(s){if(!s.current())return;s.root.dataset.side=s.side;s.root.dataset.kind=s.item.kind;s.card.classList.toggle('has-quick-ticket',true);for(const b of s.card.querySelectorAll('[data-action=swipe-order]')){const selected=b.dataset.side===s.side;b.classList.toggle('quick-selected',selected);b.setAttribute('aria-pressed',String(selected));b.setAttribute('aria-busy',String(selected&&(s.loading||s.busy)));b.classList.toggle('is-quoting',selected&&s.loading);b.disabled=!available(s)||s.busy||Boolean(s.hash)||selected&&s.loading;b.setAttribute('aria-label',label(b.dataset.side)+' in this card. Wallet approval required.');}s.fields.querySelectorAll('input').forEach(el=>el.readOnly=s.busy||Boolean(s.hash));s.fields.querySelectorAll('button,select').forEach(el=>el.disabled=s.busy||Boolean(s.hash));s.root.querySelectorAll('[data-quick-amount]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.quickAmount)===Number(values(s).amount))));}
  async function load(s,automatic=false){
    if(!s.current()||s.busy||s.hash||!valid(s))return;
    if(!available(s)){s.error.textContent='This market is no longer available';return;}
    clearTimeout(timer);clearTimeout(routePoll);controller?.abort();controller=new AbortController();const signal=controller.signal,version=++s.version,data=args(s),fingerprint=JSON.stringify(data),scope=owner();
    s.plan=null;s.referenceExpires=null;s.loadScope=scope;s.loading=true;if(!automatic){s.refreshes=0;idle(s);}s.error.textContent='';s.summary.dataset.state='loading';s.summary.setAttribute('aria-busy','true');$('span',s.summary).textContent=automatic?'Updating quote':'Getting quote';sync(s);
    const current=()=>s.current()&&version===s.version&&scope===owner()&&JSON.stringify(args(s))===fingerprint;
    try{
      let plan;
      if(s.item.kind==='spot'&&!data.venue){
        let reference=await api('/api/routes',{...data,progressive:true},{signal});if(!current())return;
        const deadline=performance.now()+12500;
        // A partial comparison can have no route yet. Keep waiting for its first
        // usable result instead of incorrectly declaring failure or forcing Kuru.
        while(!reference.best&&!reference.complete&&current()&&performance.now()<deadline){
          $('span',s.summary).textContent='Finding route';
          await new Promise(resolve=>setTimeout(resolve,500));if(!current()||signal.aborted)return;
          reference=await api('/api/routes/status?id='+encodeURIComponent(reference.id),undefined,{signal});
        }
        if(!current())return;
        const route=reference.routes.find(r=>r.provider===reference.best&&r.state==='quoted');
        if(!route){s.summary.dataset.state='unavailable';s.summary.innerHTML=`<div><span>${reference.complete?'No route for this amount':'Routes still updating'}</span><button data-quick-retry>Retry</button></div>`;return;}
        if(!S.boot.wallet){
          const paintReference=d=>{const best=d.routes.find(r=>r.provider===d.best&&r.state==='quoted');if(!current()||!best)return;s.referenceExpires=d.expires;s.summary.dataset.state='reference';s.summary.innerHTML=`<div><span>Estimated</span><b>${esc(best.output)} ${esc(token(data.output)?.symbol||s.item.asset.symbol)}</b></div><small>${esc(best.provider)} · Before network fee</small>`;};
          paintReference(reference);
          const improve=async()=>{if(!current()||signal.aborted||performance.now()>=deadline)return;try{const d=await api('/api/routes/status?id='+encodeURIComponent(reference.id),undefined,{signal});paintReference(d);if(current()&&!d.complete)routePoll=setTimeout(improve,750);}catch{}};
          if(!reference.complete)routePoll=setTimeout(improve,750);return;
        }
        plan=await api('/api/quotes',{...data,provider:route.provider,comparisonQuote:reference.id},{signal});
      }else if(!S.boot.wallet){
        if(data.venue==='nadfun'){const q=await api('/api/nadfun/quote',data,{signal});if(current()){s.referenceExpires=q.expires;s.summary.dataset.state='reference';s.summary.innerHTML=`<div><span>Estimated</span><b>${esc(q.receive)} ${esc(q.outputAsset)}</b></div><small>nad.fun · Before network fee</small>`;}}
        else{s.summary.dataset.state='connect';s.summary.innerHTML='<div><span>Connect wallet to get a quote</span></div>';}return;
      }else plan=await api('/api/execution/plan',data,{signal});
      if(!current())return;
      if(!Number.isFinite(plan.expires)||plan.expires<=Date.now()/1000)throw new Error('Quote expired. Refresh it.');
      s.plan=plan;s.lastPlanId=plan.id;s.scope=scope;s.fingerprint=fingerprint;paint(s);remember(s);
    }catch(e){if(current()&&e.name!=='AbortError'){s.plan=null;idle(s);s.error.textContent=e.message;if(e.code==='perpl_account_required')s.error.insertAdjacentHTML('beforeend','<button data-quick-collateral>Add AUSD collateral</button>');else s.error.insertAdjacentHTML('beforeend','<button data-quick-retry>Retry quote</button>');}}
    finally{if(current()){s.loading=false;s.summary.removeAttribute('aria-busy');sync(s);}}
  }
  function paint(s){
    s.summary.dataset.state='ready';
    const p=s.plan.summary||s.plan,spot=s.item.kind==='spot',fee=p.feeBps??p.protocolFeeBps??s.plan.fees?.totalBps;
    s.summary.innerHTML=spot?`<div><span>Receive</span><b>${esc(p.receive)} ${esc(p.outputAsset||token(args(s).output)?.symbol||'')}</b></div><small>Min ${esc(p.minimum)} · 0.5% slippage${fee!=null?' · '+fee/100+'% fee':''}</small>`:s.item.kind==='prediction'?`<div><span>Prediction</span><b>${esc(p.predictionPrice)} USD</b></div><small>Stake ${esc(p.stake)} ${esc(p.asset)} · ${p.feeBps/100}% fee</small>`:`<div><span>${esc(label(s.side))}</span><b>${esc(p.quantity||p.amount)} ${esc(p.quantity?s.item.market.baseSymbol||s.item.market.symbol:p.asset)}</b></div><small>${p.limit?'Protection $'+esc(p.limit)+' · ':''}${p.fee?'Fee '+esc(p.fee)+' '+esc(p.asset):fee!=null?fee/100+'% fee':'Fees at execution'}</small>`;
    const keeper=p.executionModel==='keeper'||['Pingu','LeverUp'].includes(s.item.market?.venue);if(keeper)s.summary.insertAdjacentHTML('beforeend','<small>Request awaits keeper execution</small>');
  }
  function recoveryForm(s,message='Verify the transaction hash from your wallet'){
    const value=$('[name=recovery-hash]',s.error)?.value||'';
    s.error.innerHTML=`<span>${esc(message)}</span><label class="r-quick-recovery"><input name="recovery-hash" aria-label="Submitted transaction hash" autocomplete="off" placeholder="0x…" value="${esc(value)}"><button type="button" data-quick-recover>Verify</button></label>`;
  }
  function presentStatus(s,message,phase='pending'){
    s.statusMessage=message;s.phase=message?phase:'';s.status.dataset.phase=s.phase;
    s.status.innerHTML=message?`<span>${esc(message)}</span><div>${s.hash&&s.hash!=='unknown'?`<a href="https://monadvision.com/tx/${esc(s.hash)}" target="_blank" rel="noopener noreferrer">Transaction</a>`:''}${s.completed?'<button type="button" data-quick-new>New order</button>':s.hash?'<button data-nav="activity">Activity</button>':''}</div>`:'';
    remember(s);
  }
  async function recover(s,button){
    if(!s.current()||s.busy)return;const scope=owner(),original=finance.uncertainInline?.();s.busy=true;button.disabled=true;sync(s);
    try{const result=await finance.recoverInline($('[name=recovery-hash]',s.root).value.trim());if(!result||!s.current()||scope!==owner())return;s.error.textContent='';
      const sameOrder=original?.id===s.lastPlanId;
      if(!sameOrder){
        // A wallet result belongs to its original order, never the newly visible asset.
        for(const [key,draft] of drafts){if(JSON.parse(key)[0]===scope&&draft.lastPlanId===original?.id){draft.hash=result.approval?null:result.tx;draft.approval=false;draft.status=result.approval?(result.state==='failed'?'Approval failed · Try again':'Approved · Ready to trade'):'Submitted · Awaiting confirmation';draft.phase='pending';}}
        s.hash=null;s.busy=false;s.plan=null;presentStatus(s,result.approval&&result.state==='failed'?'Earlier approval failed · Check Activity':'Earlier transaction verified · Check Activity');s.status.insertAdjacentHTML('beforeend','<button data-nav="activity">Activity</button>');await load(s);
      }else if(result.approval){s.hash=null;s.approval=false;s.busy=false;s.plan=null;presentStatus(s,result.state==='failed'?'Approval failed · Try again':'Approved · Ready to trade');await load(s);}
      else{s.hash=result.tx;s.approval=false;presentStatus(s,'Submitted · Awaiting confirmation');pollState(s);}
    }catch(e){if(s.current())recoveryForm(s,e.message);}finally{s.busy=false;sync(s);}
  }
  async function act(side,gesture=false){
    const s=ticket;if(!s?.current()||s.busy||s.hash)return;
    if(!available(s)){s.plan=null;s.error.textContent='This market is no longer available';sync(s);return;}
    if(side!==s.side){s.side=side;$('[name=amount]',s.root)&&(s.fields.querySelector('[name=amount]').value='');defaults(s);changed();if(!gesture)$('[name=amount],[name=quantity],[name=price]',s.root)?.focus({preventScroll:true});return;}
    if(gesture)return;
    if(!valid(s)){$('[name=amount],[name=quantity],[name=price]',s.root)?.focus({preventScroll:true});return;}
    if(S.financialBusy){s.error.textContent='Another wallet request is still pending';return;}
    if(!S.boot.me||!S.boot.wallet){needAccount(async()=>{if(!s.current())return;if(await walletReady()&&s.current())await load(s);});return;}
    if(!s.plan||s.scope!==owner()||s.fingerprint!==JSON.stringify(args(s))||s.plan.expires<=Date.now()/1000){await load(s);if(!s.current()||!s.plan||s.loading||s.hash)return;}
    const plan=s.plan,version=s.version;s.busy=true;sync(s);
    const current=()=>s.current()&&s.version===version&&s.scope===owner()&&s.fingerprint===JSON.stringify(args(s));
    await finance.submitInline(plan,{kind:s.item.kind==='spot'&&!args(s).venue?'spot':'execution',current,
      refresh:()=>api(s.item.kind==='spot'&&!args(s).venue?'/api/quotes':'/api/execution/plan',s.item.kind==='spot'&&!args(s).venue?{...args(s),provider:s.plan.provider}:args(s)),
      refreshed:p=>{s.plan=p;s.lastPlanId=p.id;paint(s);remember(s);},
      status:message=>{if(s.current())presentStatus(s,message,s.hash?'pending':'wallet');},
      uncertain:()=>{s.hash='unknown';if(s.current())presentStatus(s,'Wallet result unknown · Check wallet before retrying','unknown');},
      submitted:(hash,approval)=>{s.hash=hash;s.approval=approval;presentStatus(s,approval?'Approval pending':'Submitted');if(!approval){s.busy=false;sync(s);c.releaseInteraction?.();}},
      approved:()=>{s.hash=null;s.approval=false;presentStatus(s,'Opening wallet…');},
      recorded:()=>{if(s.current()){presentStatus(s,'Submitted · Awaiting confirmation');pollState(s);}},
      error:(message,hash)=>{if(s.current()){if(s.hash==='unknown')recoveryForm(s,message);else{s.error.textContent=message;if(hash)s.error.insertAdjacentHTML('beforeend','<button data-nav="activity">Check Activity</button>');else presentStatus(s,'');}}},
      done:()=>{s.busy=false;sync(s);}
    });
  }
  async function pollState(s){
    clearTimeout(poll);
    if(document.hidden||!s.current()||s.polling||s.approval||s.completed||!/^0x[0-9a-fA-F]{64}$/.test(s.hash||''))return;
    s.polling=true;
    try{const d=await api('/api/activity');if(!s.current())return;const entry=d.entries.find(e=>e.tx?.toLowerCase()===s.hash.toLowerCase());
      if(entry){
        const business=entry.outcome?.businessState,final=entry.state==='finalized';
        const terminal={filled:'Filled',partial_fill:'Partially filled',swap_delivered:'Delivered',prediction_entered:'Prediction entered',unfilled:'Unfilled',refunded:'Refunded',cancelled:'Cancelled',reverted:'Reverted'};
        s.completed=['failed','invalid'].includes(entry.state)||Boolean(final&&terminal[business]);
        const text=final&&terminal[business]?terminal[business]:entry.state==='failed'?'Transaction failed':entry.state==='invalid'?'Verification failed':business==='keeper_pending'?'Awaiting keeper execution':final?'Finalized · Fill unverified':'Submitted · Awaiting confirmation';
        const phase=['failed','invalid'].includes(entry.state)||business==='reverted'?'failed':s.completed?'complete':'pending';
        presentStatus(s,text,phase);sync(s);
      }
    }catch{}finally{s.polling=false;}
    if(s.current()&&!s.completed&&!document.hidden)poll=setTimeout(()=>pollState(s),5000);
  }
  return {mount,act,dispose,get locked(){return Boolean(ticket?.busy);}};
}
