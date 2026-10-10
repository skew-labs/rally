import {predictionUI} from './prediction-ui.js';

export function financeUI(c) {
  const {S,$,api,esc,icon,usd,age,modal,closeModal,needAccount,walletReady,receipt,notify,boot,navigate,pageHeader,empty,loading}=c;
  const address=a=>a?.slice(0,6)+'…'+a?.slice(-4);
  const txLink=tx=>`<a href="https://monadvision.com/tx/${esc(tx)}" target="_blank" rel="noopener noreferrer">${esc(address(tx))} ${icon('external')}</a>`;
  const dateFormat=new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric'});
  const timeFormat=new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit'});
  const date=t=>dateFormat.format(new Date(t*1000));
  const pendingKey='rally:financial-pending';
  const paymentRequestKey=()=>`rally:payment-request:${S.boot.me?.id}`;
  const paymentRequest=()=>{try{return JSON.parse(localStorage.getItem(paymentRequestKey())||'null');}catch{return null;}};
  const pending=()=>{try{const items=JSON.parse(localStorage.getItem(pendingKey)||'[]');return Array.isArray(items)?items.filter(x=>x&&['payment','execution','approval'].includes(x.type)&&/^0x[0-9a-fA-F]{64}$/.test(x.tx)):[];}catch{return [];}};
  const save=item=>{const list=pending().filter(p=>p.tx!==item.tx);list.push(item);localStorage.setItem(pendingKey,JSON.stringify(list));};
  const remove=tx=>localStorage.setItem(pendingKey,JSON.stringify(pending().filter(p=>p.tx!==tx)));
  const fields=items=>`<dl class="r-review-fields">${items.filter(x=>x[1]!=null).map(([name,value])=>`<div><dt>${esc(name)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>`;
  async function record(item){
    for(let attempt=0;attempt<8;attempt++){
      try{const response=await api(item.type==='payment'?'/api/payments/record':'/api/execution/record',{[item.type==='payment'?'invoice':'plan']:item.id,tx:item.tx});remove(item.tx);return response;}
      catch(e){if(e.code!=='transaction_pending')throw e;await new Promise(resolve=>setTimeout(resolve,1500));}
    }
    throw new Error('Transaction submitted. Open Activity to record the same hash.');
  }
  async function resume(){
    await c.resumeSpot();
    const list=pending().filter(x=>x.user===S.boot.me?.id);
    for(const item of list){try{if(item.type==='approval'){const payment=item.for==='payment';const result=await api(payment?'/api/payments/approval/check':'/api/execution/approval/check',{[payment?'invoice':'plan']:item.id,tx:item.tx});if(result.state!=='pending'){remove(item.tx);notify('Allowance '+result.state+'. Ready to trade.');}}else{await record(item);notify('Transaction restored. Check Activity.');}}catch(e){notify(e.message);}}
  }
  function feeds(){
    $('#page').innerHTML=pageHeader('Feeds','<button class="r-btn" data-action="create-feed">'+icon('plus')+'Create</button>')+`<div class="r-feed-directory">${S.boot.feeds.map(f=>`<article class="r-feed-card"><div class="r-feed-icon">${icon('algorithm')}</div><div><h2>${esc(f.name)}</h2><p>@${esc(f.creator?.handle||'rally')}</p><small>${Number(f.priceRaw)?esc(f.price)+' USDC / 30 days':'Free'}${f.accessExpires?' · Until '+date(f.accessExpires):''}</small>${f.weights?`<div class="r-weight-bar">${f.weights.map((w,i)=>`<span style="flex:${w||.01}" class="w${i}" title="${['Recency','Watchlist','Engagement'][i]} ${w}"></span>`).join('')}</div>`:''}</div><button class="r-btn ${S.boot.activeFeed===f.id?'subtle':'primary'}" data-action="${f.access?'use-feed':'subscribe-feed'}" data-id="${esc(f.id)}">${S.boot.activeFeed===f.id?icon('check')+'Selected':f.access?'Use feed':'Subscribe'}</button>${f.accessExpires?`<button class="r-text-button" data-action="subscribe-feed" data-id="${esc(f.id)}">Renew</button>`:''}</article>`).join('')}</div>`;
  }
  function createFeed(){needAccount(()=>{
    modal('Create a feed',`<form id="feed-form"><label class="r-field">Name<input name="name" maxlength="32" placeholder="Your feed" required></label>${[['Recency','Newest posts'],['Watchlist','Assets you watch'],['Engagement','Likes from people']].map(([l,d],i)=>`<label class="r-weight-field"><span><b>${l}</b><output id="weight-${i}">${i?25:50}</output></span><small>${d}</small><input name="w${i}" type="range" min="0" max="100" value="${i?25:50}" data-weight="${i}"></label>`).join('')}<label class="r-field">Price · USDC / 30 days<input name="price" type="number" min="0" max="10000" step="0.000001" value="0" required><small>0 for free. Community tokens use your revenue allocation.</small></label><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Publish feed</button></form>`);
    document.querySelectorAll('[data-weight]').forEach(x=>x.oninput=()=>$('#weight-'+x.dataset.weight).textContent=x.value);
    $('#feed-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget,button=$('[type=submit]',form);button.disabled=true;const data=new FormData(form);try{if(Number(data.get('price'))&&!S.boot.wallet){if(!await walletReady())return;}const r=await api('/api/feeds/create',{name:data.get('name'),weights:[0,1,2].map(i=>Number(data.get('w'+i))),price:data.get('price')});await api('/api/feeds/use',{id:r.id});await boot();closeModal();S.feed=r.id;S.mode='for-you';await navigate('feed');notify('Feed published');}catch(e){$('.r-form-error',form).textContent=e.message;}finally{button.disabled=false;}};
  });}
  function subscribe(id,trigger=null){return needAccount(async()=>{
    if(!S.boot.wallet){if(!await walletReady())return;}
    const invoice=await api('/api/payments/checkout',{feed:id});if(invoice.tx){await activity();return;}if(paymentRequest()){paymentReview(invoice);return;}await review({...invoice,summary:{action:'pay',amount:invoice.amount,asset:'USDC'}},trigger,'payment');
  });}
  function paymentReview(invoice){
    modal('Subscribe to '+esc(invoice.feedName),fields([['Access','30 days'],['Total',invoice.amount+' USDC'],['Creator receives',(invoice.creatorAmount||invoice.amount)+' USDC'],['Community buyback',invoice.communityTerms?invoice.buybackAmount+' USDC':null],['Burn',invoice.communityTerms?invoice.communityTerms.burnBps/100+'% of tokens bought':null],['Network','Monad'],['Renewal','Manual']])+`<p class="r-note">Access opens after finality.${invoice.communityTerms?' Buybacks wait for liquidity and price protection.':''}</p><div id="payment-readiness" class="r-payment-readiness" role="status">Checking wallet balance…</div><div class="r-form-error" role="alert"></div><button class="r-btn primary full" id="financial-submit">Pay in wallet</button>`);
    const readiness=$('#payment-readiness');
    const submit=$('#financial-submit');submit.disabled=true;
    const unresolved=paymentRequest();
    if(unresolved){
      readiness.textContent='Check your existing wallet request before paying again.';
      submit.hidden=true;readiness.insertAdjacentHTML('afterend',`<form id="payment-recovery"><label class="r-field">Transaction hash<input name="hash" pattern="0x[0-9a-fA-F]{64}" placeholder="0x…" required></label><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Check transaction</button></form>`);
      const f=$('#payment-recovery');f.onsubmit=async e=>{e.preventDefault();const b=$('[type=submit]',f);b.disabled=true;try{if(unresolved.wallet!==S.boot.wallet)throw new Error('Connect the original wallet');const result=await api(unresolved.approval?'/api/payments/approval/check':'/api/payments/record',{invoice:unresolved.id,tx:f.elements.hash.value});if(unresolved.approval&&result.state==='pending')throw new Error('Approval still pending');localStorage.removeItem(paymentRequestKey());if(unresolved.approval)paymentReview(await api('/api/payment?id='+encodeURIComponent(unresolved.id)));else{await boot();await activity();}}catch(e){if(f.isConnected){$('.r-form-error',f).textContent=e.message;b.disabled=false;}}};return;
    }
    api('/api/payments/prepare',{invoice:invoice.id}).then(p=>{if(readiness.isConnected){readiness.textContent='Estimated network fee: '+p.estimatedGasCostMON+' MON';submit.disabled=false;}}).catch(e=>{if(!readiness.isConnected)return;readiness.innerHTML=esc(e.message)+(e.code==='insufficient_balance'?`<button class="r-btn small subtle" data-action="fund-subscription" data-id="${esc(invoice.token)}" data-invoice="${esc(invoice.id)}">Get USDC</button>`:e.code==='insufficient_gas'?`<button class="r-btn small subtle" data-action="receive-mon" data-id="${esc(invoice.id)}">Receive MON</button>`:'')+`<button class="r-text-button" data-action="resume-payment" data-id="${esc(invoice.id)}">Refresh balance</button>`;});
    $('#financial-submit').onclick=()=>send('payment',invoice.id);
  }
  const actionLabel=p=>p.direction?(p.direction==='short'?'Sell / Short':'Buy / Long'):({buy:'Buy',sell:'Sell',predict:'Predict price',close:'Close position',claim:'Claim',deposit:'Deposit',withdraw:'Withdraw',cancel:'Cancel order',create:'Launch'}[p.action]||'Continue');
  async function review(plan,trigger=null,kind='execution'){
    if(S.financialBusy)return;
    S.financialPlan=plan;
    const dialog=$('.r-modal'),form=kind==='payment'?null:trigger?trigger.closest('form'):dialog?dialog.querySelector('#perpl-order-form,#leverup-order-form,#venue-order-form,#prediction-form,#collateral-form,#venue-account-form,#nad-launch-form'):$('#nad-order-form');
    const root=form||trigger?.closest('.r-modal')||dialog||$('#page'),button=trigger||form?.querySelector('[type=submit]');
    if(!root)return;
    let error=root.querySelector('.r-form-error');if(!error){error=document.createElement('div');error.className='r-form-error';error.setAttribute('role','alert');root.append(error);}
    let status=root.querySelector('.r-direct-status');if(!status){status=document.createElement('div');status.className='r-direct-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');(button||error).before(status);}
    let sent=false,unknown=false;const actor=S.boot.me?.id,wallet=S.boot.wallet,original=button?.textContent,fingerprint=()=>form?JSON.stringify([...form.elements].filter(el=>el.name).map(el=>[el.name,el.value,el.checked])):'';
    const initial=fingerprint(),current=()=>root.isConnected&&actor===S.boot.me?.id&&wallet===S.boot.wallet&&initial===fingerprint();
    const paintEstimate=p=>{if(form?.id==='nad-order-form'&&p.summary?.receive){const v=p.summary;$('#nad-quote').innerHTML='<div class="nad-receive"><small>Estimated receive</small><b>'+esc(v.receive)+' '+esc(v.outputAsset)+'</b></div><small class="r-note">Minimum '+esc(v.minimum)+' '+esc(v.outputAsset)+'</small>';const penalty=$('#nad-penalty');if(penalty){penalty.hidden=!(v.snipingPenaltyBps>0);penalty.textContent=v.snipingPenaltyBps>0?'Early-trade penalty: '+v.snipingPenaltyBps/100+'%':'';}}};paintEstimate(plan);
    error.textContent='';status.textContent='';if(form)c.checkout.formBusy(form,true);if(button)button.disabled=true;
    await submitInline(plan,{kind,current,
      refresh:()=>kind==='payment'?api('/api/payment?id='+encodeURIComponent(plan.id)):api('/api/execution/plan',plan.args),
      refreshed:p=>{S.financialPlan=p;paintEstimate(p);},
      status:message=>{if(current()){status.textContent=message;if(button)button.textContent=message;}},
      approved:()=>{status.textContent='Opening wallet…';},
      submitted:(hash,approval)=>{if(!approval){sent=true;if(form)form.dataset.orderState='submitted';}status.innerHTML=(approval?'Approval pending':'Submitted')+' · '+txLink(hash);},
      uncertain:()=>{unknown=true;if(form)form.dataset.orderState='unknown';if(current()&&!root.querySelector('.r-direct-recovery')){error.textContent='Check the transaction in your wallet before trying again.';const recover=document.createElement('div');recover.className='r-direct-recovery';recover.innerHTML='<label class="r-field">Transaction hash<input name="hash" pattern="0x[0-9a-fA-F]{64}" placeholder="0x…" required></label><div class="r-form-error" role="alert"></div><button class="r-btn" type="button">Check transaction</button>';status.after(recover);recover.querySelector('button').onclick=async()=>{const input=recover.querySelector('[name=hash]');if(!input.reportValidity())return;const b=recover.querySelector('button');b.disabled=true;try{await recoverInline(input.value.trim());await boot();await activity();}catch(e){recover.querySelector('.r-form-error').textContent=e.message;b.disabled=false;}};}},
      recorded:()=>{if(form?.closest('.r-modal'))closeModal();notify(kind==='payment'?'Payment submitted. Access opens after confirmation.':'Submitted. Activity updates after confirmation.');},
      error:(message,hash)=>{if(current()){error.textContent=message;if(hash)status.innerHTML='Submitted · '+txLink(hash);}},
      done:()=>{if(form)c.checkout.formBusy(form,false);if(button?.isConnected){button.textContent=sent?'Submitted':original||actionLabel(plan.summary);button.disabled=sent||unknown;}status.removeAttribute('aria-busy');}
    });
    if(sent&&kind==='payment'){await boot();await activity();}
  }
  async function send(type,id){
    const invoice=await api('/api/payment?id='+encodeURIComponent(id));
    return review({...invoice,summary:{action:'pay',amount:invoice.amount,asset:'USDC'}},$('#financial-submit'),'payment');
  }
  async function submitInline(plan,ui){
    if(S.financialBusy)return;if(!ui.current()){ui.done();return;}
    S.financialBusy=true;let hash=null,actor=null,wallet=null,uncertainKey,requested=false;
    const spot=ui.kind==='spot',payment=ui.kind==='payment',alive=()=>ui.current()&&S.boot.me?.id===actor&&S.boot.wallet===wallet;
    const emit=(name,...args)=>{try{ui[name]?.(...args);}catch{/* Keep durable transaction recovery even if rendering fails. */}};
    const check=()=>{if(!alive())throw new Error('Order changed. Try again.');};
    const fresh=async()=>{if(!ui.refresh)throw new Error('Price changed. Try again.');check();emit('status','Updating price…');const next=await ui.refresh();check();if(!next||!Number.isFinite(next.expires)||next.expires<=Date.now()/1000)throw new Error('Price unavailable. Try again.');plan=next;emit('refreshed',plan);};
    try{
      emit('status','Opening wallet…');if(!await walletReady())return;
      actor=S.boot.me?.id;wallet=S.boot.wallet;check();
      uncertainKey='rally:uncertain-inline-order:'+actor+':'+wallet;
      if(JSON.parse(localStorage.getItem(uncertainKey)||'null')){emit('uncertain');throw new Error('Check your earlier wallet transaction first.');}
      if(pending().some(x=>x.user===actor)||c.spotPending().some(x=>x.user===actor))throw new Error('A transaction is still pending. Check Activity.');
      localStorage.setItem('rally:storage-check','1');localStorage.removeItem('rally:storage-check');
      let approvals=0,refreshes=0;
      for(;;){
        check();if(!Number.isFinite(plan.expires)||plan.expires<=Date.now()/1000){if(refreshes++>=1)throw new Error('Price unavailable. Try again.');await fresh();}
        const prep=await api(spot?'/api/orders/prepare':payment?'/api/payments/prepare':'/api/execution/prepare',spot?{quote:plan.id}:payment?{invoice:plan.id}:{plan:plan.id});check();
        if(plan.expires<=Date.now()/1000||Number.isFinite(prep.expires)&&prep.expires<=Date.now()/1000){if(refreshes++>=1)throw new Error('Price unavailable. Try again.');await fresh();continue;}
        const tx=prep.approval||prep.transaction;if(!tx)throw new Error('Trade unavailable. Try again.');
        ui.validateTransaction?.(tx,prep);
        if(prep.approval&&approvals)throw new Error('Token approval is not ready. Try again.');
        if(!await walletReady())return;check();
        if(plan.expires<=Date.now()/1000||Number.isFinite(prep.expires)&&prep.expires<=Date.now()/1000){if(refreshes++>=1)throw new Error('Price unavailable. Try again.');await fresh();continue;}
        if(tx.from?.toLowerCase()!==wallet.toLowerCase()||tx.chainId&&Number(tx.chainId)!==143)throw new Error('Wallet changed. Reconnect it.');
        emit('status',prep.approval?'Approve in wallet':'Confirm in wallet');
        localStorage.setItem(uncertainKey,JSON.stringify({user:actor,wallet,id:plan.id,kind:ui.kind,approval:Boolean(prep.approval),created:Date.now()}));requested=true;
        hash=await S.provider.request({method:'eth_sendTransaction',params:[{...tx,chainId:'0x8f'}]});
        if(!/^0x[0-9a-fA-F]{64}$/.test(hash))throw new Error('Check the transaction in your wallet.');
        if(prep.approval){
          if(spot)localStorage.setItem('rally:pending-spot-approval',JSON.stringify({quote:plan.id,tx:hash,user:actor,wallet}));else save({type:'approval',for:payment?'payment':'execution',id:plan.id,tx:hash,user:actor,wallet});
          localStorage.removeItem(uncertainKey);requested=false;emit('submitted',hash,true);emit('status','Approval pending…');await receipt(hash);
          let result;for(let i=0;i<8;i++){result=await api(spot?'/api/orders/approval/check':payment?'/api/payments/approval/check':'/api/execution/approval/check',spot?{quote:plan.id,tx:hash}:payment?{invoice:plan.id,tx:hash}:{plan:plan.id,tx:hash});if(result.state!=='pending')break;await new Promise(resolve=>setTimeout(resolve,1500));}
          if(result.state!==((spot||payment)?'confirmed':'approved'))throw new Error('Approval '+result.state+'. Check Activity.');
          if(spot)localStorage.removeItem('rally:pending-spot-approval');else remove(hash);
          hash=null;approvals++;check();emit('approved');await fresh();continue;
        }
        const item={type:payment?'payment':'execution',id:plan.id,tx:hash,user:actor,wallet,draft:plan.args?.draft};
        if(spot)localStorage.setItem('rally:pending-order',JSON.stringify({quote:plan.id,tx:hash,user:actor,wallet}));else save(item);
        localStorage.removeItem(uncertainKey);requested=false;emit('submitted',hash,false);emit('status','Submitted');
        if(spot){if(!await c.recordSpot(plan.id,hash))throw new Error('Submitted. Check Activity for updates.');}else await record(item);
        if(alive())emit('recorded',hash);return;
      }
    }catch(e){if(requested&&e.code===4001){localStorage.removeItem(uncertainKey);requested=false;}if(requested)emit('uncertain');emit('error',e.code===4001?'Wallet request canceled':e.message||'Could not submit',hash);}
    finally{S.financialBusy=false;emit('done');}
  }
  function uncertainInline(){try{return JSON.parse(localStorage.getItem('rally:uncertain-inline-order:'+S.boot.me?.id+':'+S.boot.wallet)||'null');}catch{return null;}}
  async function recoverInline(hash){
    if(!/^0x[0-9a-fA-F]{64}$/.test(hash||''))throw new Error('Enter the transaction hash from your wallet');
    const item=uncertainInline();if(!item)throw new Error('No unknown wallet request for this account');
    if(!await walletReady())return;
    if(item.user!==S.boot.me?.id||item.wallet!==S.boot.wallet)throw new Error('Wallet changed. Restore the original account.');
    const spot=item.kind==='spot',payment=item.kind==='payment',ref=spot?{quote:item.id,tx:hash}:payment?{invoice:item.id,tx:hash}:{plan:item.id,tx:hash};
    const result=await api(item.approval?(spot?'/api/orders/approval/check':payment?'/api/payments/approval/check':'/api/execution/approval/check'):(spot?'/api/orders':payment?'/api/payments/record':'/api/execution/record'),ref);
    if(item.approval&&!['confirmed','approved','failed'].includes(result.state))throw new Error('Approval not confirmed yet. Check the same hash again.');
    // Only the server's exact wallet/calldata check can resolve uncertainty.
    localStorage.removeItem('rally:uncertain-inline-order:'+item.user+':'+item.wallet);
    return {tx:hash,approval:item.approval,state:result.state};
  }
  // Perpl market IDs and base symbols, with verified underlying-asset artwork.
  // An unrecognised market must not borrow another token's identity.
  const perplAssets={
    1:['BTC','Bitcoin','BTC.png'],10:['MON','Monad','MON.png'],
    20:['ETH','Ethereum','ETH.png'],31:['SOL','Solana','SOL.png'],
    40:['HYPE','Hyperliquid','HYPE.jpg'],50:['ZEC','Zcash','ZEC.png'],
    60:['LIT','Lighter','LIT.png'],70:['VVV','Venice Token','VVV.png'],
    90:['PUMP','Pump.fun','PUMP.jpg'],100:['NEAR','NEAR Protocol','NEAR.jpg'],110:['UNI','Uniswap','UNI.png']
  };
  const perpLogos=new Set(['ADA','BNB','DOGE','XMR','TRX','LINK','XRP','AAVE','QNT','AVAX','DOT','LTC','XLM','ATOM','CRV']);
  const perplAsset=m=>{const base=m.baseSymbol||m.symbol,a=Object.values(perplAssets).find(x=>x[0]===base);return a?{id:'perp:'+base.toLowerCase(),symbol:base,name:m.name||a[1],logoURI:'/assets/'+a[2]}:{id:'perp:'+base.toLowerCase(),symbol:base,name:m.name||base,logoURI:m.logoURI||(perpLogos.has(base)?'/assets/perp-'+base+'.png':null)};};
  let perpRequest;
  async function perpData(){
    if(!perpRequest)perpRequest=api('/api/perps').then(d=>{S.perps=d;return d;}).finally(()=>{perpRequest=null;});
    return perpRequest;
  }
  async function perps(host,q){
    const data=S.perps&&Date.now()/1000-S.perps.fetchedAt<15?S.perps:await perpData();
    if(!host.isConnected||S.marketTab!=='perps'||S.filter.toLowerCase()!==q)return;
    const venue=S.perpVenue||'All',selected=data.markets.filter(m=>(venue==='All'||m.venue===venue)&&(m.symbol+' '+m.venue).toLowerCase().includes(q));
    host.innerHTML=`<div class="r-market-scope"><div>${['All',...new Set(data.markets.map(m=>m.venue))].map(v=>`<button data-action="perp-venue" data-id="${esc(v)}" aria-pressed="${v===venue}">${esc(v)}</button>`).join('')}</div><span>${selected.length} markets</span></div><div class="r-table-wrap"><table class="r-market-table r-perps-table" aria-label="Perpetual markets"><colgroup><col class="r-col-asset"><col class="r-col-price"><col class="r-col-venue"><col class="r-col-action"></colgroup><thead><tr><th>Market</th><th>Price</th><th>Venue</th><th></th></tr></thead><tbody>${selected.map(m=>`<tr data-perpl-market="${esc(m.id)}"><td><button class="r-coin-cell r-perp-coin" data-action="perp-detail" data-id="${esc(m.id)}">${c.logo(perplAsset(m),true)}<span class="r-market-identity"><b title="${esc(m.symbol)}">${esc(m.symbol)}</b><small>${m.execution==='service_paused'?'Service paused':m.priceSource==='Perpl mark'?'Perpetual':'Oracle reference'}</small></span></button></td><td class="r-number">${usd(m.mark)}${m.stale?'<small>'+(m.mark?'Last '+age(m.observationAt):'Unavailable')+'</small>':''}</td><td><small>${esc(m.venue)}</small></td><td><button class="r-btn small" data-action="${m.execution==='wallet_transactions'?'perpl-order':'perp-detail'}" data-id="${esc(m.id)}" ${m.execution==='wallet_transactions'&&(!m.open||m.stale)?'disabled':''}>${m.execution==='wallet_transactions'?(m.open&&!m.stale?'Trade':'Unavailable'):'Details'}</button></td></tr>`).join('')}</tbody></table></div><div class="r-data-foot"><span data-perpl-updated>Venue prices · Updated ${age(data.priceUpdatedAt||0)}</span><button class="r-text-button" data-action="perpl-account">Perpl collateral</button></div><details class="r-market-coverage"><summary>Venue coverage</summary>${data.sources.map(v=>`<div><b>${esc(v.venue)}</b><span>${v.total!=null?v.total+' markets · ':''}${esc(v.state.replaceAll('_',' '))}</span>${v.reason?`<small>${esc(v.reason)}</small>`:''}${v.excludedCrossChain?`<small>${v.excludedCrossChain} cross-chain markets excluded</small>`:''}</div>`).join('')}</details>`;
  }

  async function refreshPerps(){
    const data=await perpData();if(!(S.view==='explore'||S.view==='home'&&S.homeSection==='markets')||S.marketTab!=='perps')return;
    const markets=new Map(data.markets.map(m=>[String(m.id),m]));
    const q=S.filter.toLowerCase(),venue=S.perpVenue||'All',visible=data.markets.filter(m=>(venue==='All'||m.venue===venue)&&(m.symbol+' '+m.venue).toLowerCase().includes(q));
    const rows=[...document.querySelectorAll('[data-perpl-market]')],ids=new Set(visible.map(m=>String(m.id)));
    if(rows.length!==visible.length||rows.some(row=>!ids.has(row.dataset.perplMarket))){const host=$('#market-list .r-market-results');if(host)await perps(host,q);return;}
    for(const row of rows){
      const m=markets.get(row.dataset.perplMarket);if(!m)continue;
      const cells=row.querySelectorAll('td'),price=usd(m.mark)+(m.stale?'<small>'+(m.mark?'Last '+age(m.observationAt):'Unavailable')+'</small>':'');if(cells[1].innerHTML!==price)cells[1].innerHTML=price;
      const subtitle=row.querySelector('.r-coin-cell small');if(subtitle)subtitle.textContent=m.execution==='service_paused'?'Service paused':m.priceSource==='Perpl mark'?'Perpetual':'Oracle reference';
      const button=cells[3].querySelector('button');if(button){const executable=m.execution==='wallet_transactions';button.dataset.action=executable?'perpl-order':'perp-detail';button.disabled=executable&&(!m.open||m.stale);button.textContent=executable?(m.open&&!m.stale?'Trade':'Unavailable'):'Details';}
    }
    const updated=$('[data-perpl-updated]');if(updated)updated.textContent='Venue prices · Updated '+age(data.priceUpdatedAt||0);
  }
  function perplAccount(context=null,values=null){return needAccount(async()=>{
    if(!S.boot.wallet){if(!await walletReady())return;}
    const p=await api('/api/perpl/account');const intent=S.perplIntent;
    modal('Perpl collateral',c.originCard(context||intent?.context)+fields([['Available',p.available+' AUSD'],['Balance',p.balance+' AUSD'],['Locked',p.locked+' AUSD'],['Opening deposit',p.minimumDeposit+' AUSD']])+`${c.token(p.collateral)?'<button class="r-btn full subtle" data-action="trade" data-id="'+esc(p.collateral)+'">Get AUSD</button>':''}<form id="collateral-form"><label class="r-field">Action<select name="kind"><option value="deposit">Deposit AUSD</option>${p.account?'<option value="withdraw">Withdraw AUSD</option>':''}</select></label><label class="r-field">Amount · AUSD<input name="amount" type="text" inputmode="decimal" placeholder="0.00" required></label><div class="r-form-error" role="alert"></div><button type="submit" class="r-btn primary full">Continue</button></form>`);
    if(values){const form=$('#collateral-form');form.elements.amount.value=values.amount;form.elements.kind.value=values.kind;c.checkout.valid(form);}
    $('#collateral-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;if(form.dataset.pending==='true')return;const button=$('[type=submit]',form),data=Object.fromEntries(new FormData(form));c.checkout.formBusy(form,true);button.disabled=true;try{await review(await api('/api/execution/plan',{venue:'perpl',...data,context:context||intent?.context}));}catch(e){if(form.isConnected)$('.r-form-error',form).textContent=e.message;}finally{c.checkout.formBusy(form,false);}};
  });}
  async function perplOrder(id,context=null,direction='long',values=null){
    if(!S.perps||Date.now()/1000-S.perps.fetchedAt>=15)await perpData();
    if(String(id).startsWith('drake:')||String(id).startsWith('pingu:'))return venueOrder(id,context,direction);
    if(S.perps?.markets.find(m=>String(m.id)===String(id))?.venue==='LeverUp')return leverupOrder(id,context,direction,values);
    direction=direction==='short'?'short':'long';
    S.perplIntent={market:id,context,direction};
    if(context?.post&&!S.posts.some(p=>p.id===context.post))S.posts.push(await api('/api/post?id='+encodeURIComponent(context.post)));
    const market=S.perps?.markets.find(m=>String(m.id)===String(id));if(!market?.open){notify('This market is closed');return;}
    // Choosing a direction opens a form. Authentication and wallet access happen
    // only after the user taps Buy or Sell.
    modal(esc(market.symbol)+' perpetual',c.originCard(context)+`<div class="r-collateral-inline"><span>Perpl · AUSD collateral</span><button class="r-text-button" data-action="perpl-account">Collateral</button></div><form id="perpl-order-form"><div class="r-order-directions"><label><input name="direction" type="radio" value="long" ${direction==='long'?'checked':''}>Buy / Long</label><label><input name="direction" type="radio" value="short" ${direction==='short'?'checked':''}>Sell / Short</label></div><label class="r-field">Quantity · ${esc(market.symbol)}<input name="quantity" type="text" inputmode="decimal" placeholder="0.00" required><small>Up to ${market.lotDecimals} decimals</small></label><label class="r-field">Limit price · USD<input name="limit" type="text" inputmode="decimal" value="${esc(Number(market.mark).toFixed(market.priceDecimals))}" required></label><label class="r-field">Leverage<select name="leverage">${[1,2,3,4,5].map(x=>`<option value="${x}">${x}×</option>`).join('')}</select></label><label class="r-checkbox"><input name="reduceOnly" type="checkbox">Reduce only</label><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Buy / Long</button></form>`);
    if(values){const form=$('#perpl-order-form');for(const name of ['quantity','limit','leverage'])form.elements[name].value=values[name];form.elements.reduceOnly.checked=Boolean(values.reduceOnly);form.restorePerpAmount?.();c.checkout.valid(form);}
    $('#perpl-order-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;if(form.dataset.pending==='true')return;const button=$('[type=submit]',form),d=Object.fromEntries(new FormData(form));d.reduceOnly=form.elements.reduceOnly.checked;S.perplIntent.direction=d.direction;c.checkout.formBusy(form,true);button.disabled=true;try{await needAccount(async()=>{if(!await walletReady())return;const account=await api('/api/perpl/account');if(!account.account){await perplAccount(context);return;}await review(await api('/api/execution/plan',{venue:'perpl',kind:'order',market:id,...d,context}));});}catch(e){if(form.isConnected)$('.r-form-error',form).textContent=e.message;}finally{c.checkout.formBusy(form,false);}};
  }
  async function venueOrder(id,context=null,direction='long'){
    const market=S.perps?.markets.find(m=>String(m.id)===String(id));if(!market)return;
    const drake=market.venue==='Drake',venue=drake?'drake':'pingu';
    modal(esc(market.symbol),c.originCard(context)+`<div class="r-collateral-inline"><span>${esc(market.venue)} · ${drake?'AUSD':'MON'} collateral</span><button class="r-text-button" data-action="venue-account" data-id="${esc(id)}">${drake?'Portfolio':'Positions'}</button></div>${market.executionBlocker?`<p class="r-note">${esc(market.executionBlocker)}</p>`:''}<form id="venue-order-form"><div class="r-order-directions"><label><input name="direction" type="radio" value="long" ${direction!=='short'?'checked':''}>Buy / Long</label><label><input name="direction" type="radio" value="short" ${direction==='short'?'checked':''}>Sell / Short</label></div>${drake?'<label class="r-field">Margin<select name="portfolioType"><option value="imp">Isolated</option><option value="cmp">Cross</option></select></label><label class="r-field">Quantity<input name="quantity" inputmode="decimal" required></label>':'<label class="r-field">Collateral · MON<input name="amount" inputmode="decimal" required></label><label class="r-field">Leverage<select name="leverage">'+Array.from({length:Math.min(10,market.maxLeverage||1)},(_,i)=>'<option value="'+(i+1)+'">'+(i+1)+'×</option>').join('')+'</select></label>'}<label class="r-field">Protection price · USD<input name="limit" inputmode="decimal" value="${esc(market.mark?Number(market.mark).toFixed(6):'')}" required></label><div class="r-form-error" role="alert"></div><button type="submit" class="r-btn primary full" ${!market.open||market.stale?'disabled':''}>Buy / Long</button></form>`);
    if(drake)$('#venue-order-form select[name=portfolioType]').onchange=e=>{const b=$('[data-action=venue-account]');if(b)b.dataset.margin=e.target.value;};
    $('#venue-order-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;if(form.dataset.pending==='true')return;const args=Object.fromEntries(new FormData(form));if(!drake)args.leverage=Number(args.leverage);c.checkout.formBusy(form,true);try{await needAccount(async()=>{if(!await walletReady())return;await review(await api('/api/execution/plan',{venue,kind:'order',market:id,...args,context}));});}catch(error){if(form.isConnected)$('.r-form-error',form).textContent=error.message;}finally{c.checkout.formBusy(form,false);}};
  }
  function venueAccount(id,marginType='imp'){return needAccount(async()=>{
    if(!await walletReady())return;
    const drake=String(id).startsWith('drake:'),venue=drake?'drake':'pingu';
    const account=await api('/api/'+venue+'/account?'+new URLSearchParams(drake?{market:id,portfolioType:marginType}:{}));
    const positions=drake?(account.position?.state===1?[{market:id,direction:account.position.side===1?'long':'short',asset:'AUSD'}]:[]):account.positions;
    const orders=drake?(account.pendingOrderIds||[]).map(x=>({id:x,market:id})):account.orders;
    const exists=account.portfolio&&!/^0x0{40}$/.test(account.portfolio);
    modal(drake?'Drake · '+(marginType==='cmp'?'Cross':'Isolated')+' portfolio':'Pingu positions',(drake?fields([['Balance',Number(account.balanceRaw||0)/1e6+' AUSD'],['Available',Number(account.availableRaw||0)/1e6+' AUSD']]):'')+`<form id="venue-account-form">${drake?'<label class="r-field">Action<select name="kind">'+(exists?'<option value="deposit">Deposit AUSD</option><option value="withdraw">Withdraw AUSD</option>':'<option value="create">Create portfolio</option>')+'</select></label><label class="r-field">Amount · AUSD<input name="amount" inputmode="decimal"></label>':''}${positions.length?'<label class="r-field">Close position<select name="position"><option value="">Select</option>'+positions.map((p,i)=>`<option value="${i}">${esc(p.market)} · ${esc(p.direction)}</option>`).join('')+'</select></label><label class="r-field">Protection price · USD<input name="limit" inputmode="decimal"></label>':''}${orders.length?'<label class="r-field">Cancel pending order<select name="order"><option value="">Select</option>'+orders.map(o=>`<option value="${esc(o.id)}">#${esc(o.id)} · ${esc(o.market)}</option>`).join('')+'</select></label>':''}<div class="r-form-error" role="alert"></div>${drake||positions.length||orders.length?'<button type="submit" class="r-btn primary full">Continue</button>':'<p class="r-note">No positions or pending orders.</p>'}</form>`);
    $('#venue-account-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;if(form.dataset.pending==='true')return;const d=Object.fromEntries(new FormData(form));let args={venue,kind:d.kind,amount:d.amount,...(drake?{portfolioType:marginType}:{})};if(d.position!==undefined&&d.position!==''){const p=positions[Number(d.position)];args={venue,kind:'close',market:p.market,asset:p.asset,limit:d.limit,...(drake?{portfolioType:marginType}:{})};}if(d.order){const o=orders.find(o=>o.id===d.order);args={venue,kind:'cancel',order:o.id,market:o.market,...(drake?{portfolioType:marginType}:{})};}c.checkout.formBusy(form,true);try{await review(await api('/api/execution/plan',args));}catch(error){if(form.isConnected)$('.r-form-error',form).textContent=error.message;}finally{c.checkout.formBusy(form,false);}};
  });}
  async function leverupOrder(id,context=null,direction='long',values=null){
    const market=S.perps?.markets.find(m=>String(m.id)===String(id));if(!market?.open||market.stale){notify('This market is unavailable');return;}
    direction=direction==='short'?'short':'long';
    modal(esc(market.symbol)+' perpetual',c.originCard(context)+`<div class="r-collateral-inline"><span>LeverUp · USDC collateral</span><button class="r-text-button" data-action="leverup-positions" data-id="${esc(id)}">Positions</button></div><form id="leverup-order-form"><div class="r-order-directions"><label><input name="direction" type="radio" value="long" ${direction==='long'?'checked':''}>Buy / Long</label><label><input name="direction" type="radio" value="short" ${direction==='short'?'checked':''}>Sell / Short</label></div><label class="r-field">Quantity · ${esc(market.baseSymbol)}<input name="quantity" type="text" inputmode="decimal" placeholder="0.00" required><small>Up to 10 decimals</small></label><label class="r-field">Collateral · USDC<input name="amount" type="text" inputmode="decimal" placeholder="0.00" required><small>Includes the open fee. Margin settles in LVUSD.</small></label><label class="r-field">Slippage<select name="slippage"><option value="25">0.25%</option><option value="50" selected>0.5%</option><option value="100">1%</option></select></label><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Buy / Long</button></form>`);
    const form=$('#leverup-order-form');if(values){for(const name of ['quantity','amount','slippage'])if(values[name]!=null)form.elements[name].value=values[name];form.restorePerpAmount?.();c.checkout.valid(form);}
    form.onsubmit=async e=>{e.preventDefault();if(form.dataset.pending==='true')return;const data=Object.fromEntries(new FormData(form));c.checkout.formBusy(form,true);try{await needAccount(async()=>{if(!await walletReady())return;await review(await api('/api/execution/plan',{venue:'leverup',kind:'order',market:id,collateral:'USDC',...data,context}));});}catch(e){if(form.isConnected)$('.r-form-error',form).textContent=e.message;}finally{c.checkout.formBusy(form,false);}};
  }
  function leverupPositions(id){return needAccount(async()=>{
    if(!S.boot.wallet&&!await walletReady())return;
    const data=await api('/api/leverup/positions?'+new URLSearchParams({market:id}));
    modal('LeverUp positions',data.positions.length?data.positions.map(p=>`<div class="r-order-row"><span><b>${esc(p.pair)} · ${p.isLong?'Long':'Short'}</b><small>${esc(p.quantity)} · Entry ${usd(p.entry)}</small><small>${esc(p.marginAmount)} ${p.marginToken.toLowerCase()==='0xfd44b35139ae53fff7d8f2a9869c503d987f00d1'?'LVUSD':'margin tokens'}</small></span><button class="r-btn small" data-action="leverup-close" data-id="${esc(p.positionHash)}" data-market="${esc(id)}" ${p.earliestCloseTime>Date.now()/1000||p.marginToken.toLowerCase()!=='0xfd44b35139ae53fff7d8f2a9869c503d987f00d1'?'disabled':''}>Close</button></div>`).join(''):'<p class="r-note">No open positions in this market.</p>');
  });}
  const Prediction=predictionUI(c,perpData);
  const predictionTime=t=>timeFormat.format(new Date(t*1000));
  const predictionState=Prediction.state;
  const predictions=Prediction.read;
  const refreshPredictions=Prediction.refresh;
  function predict(id,price=null){
    const pool=S.predictions?.pools.find(p=>String(p.id)===String(id));if(!pool)return;
    if(predictionState(pool)!=='open'||!pool.predictionReviewed||!pool.stakeReviewed){notify('This pool is not open for entries');return;}
    const reference=Prediction.reference(pool),fresh=Prediction.fresh(reference);
    modal('Predict '+esc(pool.asset),`<form id="prediction-form"><div class="r-predict-asset">${c.logo(pool.assetInfo||c.token(pool.assetId),true)}<span><b>${esc(pool.asset)} / USD</b><small>${esc(predictionTime(pool.snapshot))}</small></span></div><div class="r-predict-reference"><span>Current reference</span><b>${fresh?usd(reference.mark):'—'}</b><small>Perpl mark · Not the settlement price</small></div><label class="r-field r-predict-price">Your price · USD<input name="price" type="text" inputmode="decimal" placeholder="0.00" required autocomplete="off"></label>${fresh?'<button type="button" class="r-text-button" data-predict-reference>Use current price</button>':''}<dl class="r-predict-terms"><div><dt>Entry</dt><dd>${esc(pool.stake+' '+pool.stakeAsset)}</dd></div><div><dt>Pool fee</dt><dd>${pool.feeBps/100}%</dd></div><div><dt>Closes</dt><dd>${esc(predictionTime(pool.close))}</dd></div></dl><p class="r-predict-note">Entry stays in the pool until settlement.</p><div class="r-form-error" role="alert"></div><button class="r-btn primary full" type="submit">Predict</button></form>`,'r-prediction-order');
    const useReference=$('[data-predict-reference]');if(useReference)useReference.onclick=()=>{const value=Prediction.reference(pool);if(!Prediction.fresh(value))return;const form=$('#prediction-form');form.elements.price.value=Number(value.mark).toFixed(8).replace(/0+$/,'').replace(/\.$/,'');c.checkout.valid(form);form.elements.price.focus({preventScroll:true});};
    if(price!=null){$('#prediction-form').elements.price.value=price;c.checkout.valid($('#prediction-form'));}
    const form=$('#prediction-form'),dialog=S.modal;let deadline;
    const checkDeadline=()=>{clearTimeout(deadline);if(!form.isConnected)return;if(predictionState(pool)!=='open'){form.querySelector('[type=submit]').disabled=true;form.querySelector('.r-predict-note').textContent='This pool has closed';return;}deadline=setTimeout(checkDeadline,Math.max(1,Math.min(2147483647,pool.close*1000-Date.now()+1)));};
    const cleanup=dialog.cleanup;dialog.cleanup=()=>{clearTimeout(deadline);cleanup?.();};form.addEventListener('input',()=>queueMicrotask(checkDeadline));checkDeadline();
    $('#prediction-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;if(form.dataset.pending==='true')return;const button=$('[type=submit]',form),price=form.elements.price.value;c.checkout.formBusy(form,true);button.disabled=true;try{if(predictionState(pool)!=='open')throw new Error('This pool has closed');await needAccount(async()=>{if(!await walletReady())return;await review(await api('/api/execution/plan',{venue:'castora',kind:'predict',pool:id,price}));});}catch(e){if(form.isConnected)$('.r-form-error',form).textContent=e.message;}finally{c.checkout.formBusy(form,false);}};
  }
  function myPredictions(){needAccount(async()=>{
    if(!S.boot.wallet){if(!await walletReady())return;}
    const d=await api('/api/predictions/mine');
    modal('My predictions',d.predictions.length?d.predictions.map(p=>`<div class="r-order-row"><span><b>Pool #${p.poolId} · $${esc(p.price)}</b><small>Prediction #${p.predictionId}</small></span>${p.winner&&!p.claimed?`<button class="r-btn small" data-action="claim-prediction" data-id="${p.poolId}:${p.predictionId}">Claim</button>`:`<span class="r-pill">${p.claimed?'Claimed':p.winner?'Winner':'Entered'}</span>`}</div>`).join(''):`<p class="r-note">No predictions for this wallet.</p>`);
  });}
  function claim(id,trigger){return needAccount(async()=>{const [pool,prediction]=id.split(':').map(Number);await review(await api('/api/execution/plan',{venue:'castora',kind:'claim',pool,prediction}),trigger);});}
  async function stocks(host,q){
    const d=await api('/api/stocks');if(!host.isConnected||S.marketTab!=='stocks'||S.filter.toLowerCase()!==q)return;S.stocks=d;
    if(d.status==='partner_required'){host.innerHTML=empty('Stocks are opening soon','Anchored trading is awaiting partner activation.','<a class="r-btn" href="https://docs.anchored.finance/trading-api/getting-started/product-and-contracts" target="_blank" rel="noopener noreferrer">Issuer details '+icon('external')+'</a>');return;}
    host.innerHTML=`<div class="r-data-label">Anchored · Monad <span class="r-pill">${d.orderStatus==='contract_review_required'?'Market data':'Trading'}</span></div><div class="r-table-wrap"><table class="r-market-table"><thead><tr><th>Stock</th><th>Price</th><th>24h</th><th></th></tr></thead><tbody>${d.symbols.filter(x=>(x.symbol+' '+x.name).toLowerCase().includes(q)).map(x=>`<tr><td><div class="r-coin-cell">${x.logoUrl?`<img class="r-token" src="${esc(c.safeURL(x.logoUrl))}" alt="${esc(x.symbol)}">`:''}<span><b>${esc(x.symbol)}</b><small>${esc(x.name)}</small></span></div></td><td class="r-number">${usd(x.price)}</td><td class="r-number">${x.change24HPercent==null?'—':Number(x.change24HPercent).toFixed(2)+'%'}</td><td><span class="r-pill">${x.tradable?'Listed':'Unavailable'}</span></td></tr>`).join('')}</tbody></table></div><p class="r-note">Orders open after the issuer contract interface is verified.</p>`;
  }
  async function activity(){return c.activity();}
  async function handle(action,id,el){
    if(action==='prediction-status'){if(!['open','recent','settled'].includes(id))return true;S.predictionStatus=id;await predictions($('#market-list'),S.filter.toLowerCase());return true;}
    if(action==='refresh-predictions'){
      el.disabled=true;
      try{await predictions($('#market-list'),S.filter.toLowerCase(),true);}catch(e){notify(e.message);}finally{el.disabled=false;}
      return true;
    }
    if(action==='receive-mon'){
      const invoice=await api('/api/payment?id='+encodeURIComponent(id));
      modal('Receive MON',fields([['Network','Monad'],['Your wallet',invoice.wallet]])+`<p class="r-note">Send MON to this address on Monad to cover network fees.</p><button class="r-btn full" data-action="copy-contract" data-id="${esc(invoice.wallet)}">${icon('copy')}Copy address</button><button class="r-btn primary full" data-action="resume-payment" data-id="${esc(invoice.id)}">Back to subscription</button>`);
      return true;
    }
    if(action==='fund-subscription'){
      const invoice=await api('/api/payment?id='+encodeURIComponent(el.dataset.invoice));
      c.trade(id,{feed:invoice.feed});
      $('.r-swap-box').insertAdjacentHTML('afterbegin',`<button class="r-funding-return" data-action="resume-payment" data-id="${esc(invoice.id)}">${icon('algorithm')}${esc(invoice.feedName)} subscription${icon('chevron')}</button>`);
      return true;
    }
    if(action==='subscribe-feed'){await subscribe(id,el);return true;}
    if(action==='perp-venue'){S.perpVenue=id;await perps($('#market-list'),S.filter.toLowerCase());return true;}
    if(action==='perpl-order'||action==='perpl-short'){await perplOrder(id,null,action==='perpl-short'?'short':'long');return true;}
    if(action==='perpl-account'){await perplAccount(S.perplIntent?.context);return true;}
    if(action==='venue-account'){await venueAccount(id,el.dataset.margin||'imp');return true;}
    if(action==='venue-order'){await venueOrder(id);return true;}
    if(action==='leverup-positions'){await leverupPositions(id);return true;}
    if(action==='leverup-close'){await needAccount(async()=>{if(!await walletReady())return;await review(await api('/api/execution/plan',{venue:'leverup',kind:'close',market:el.dataset.market,position:id}),el);});return true;}
    if(action==='predict'){predict(id);return true;}
    if(action==='my-predictions'){myPredictions();return true;}
    if(action==='claim-prediction'){await claim(id,el);return true;}
    if(action==='activity'){await activity();return true;}
    if(action==='check-payment'||action==='resume-payment'){
      const invoice=await api('/api/payment?id='+encodeURIComponent(id));
      if(action==='resume-payment'){if(invoice.tx)await activity();else if(invoice.state==='expired')await subscribe(invoice.feed,el);else if(paymentRequest())paymentReview(invoice);else await review({...invoice,summary:{action:'pay',amount:invoice.amount,asset:'USDC'}},el,'payment');}else{await boot();notify(invoice.state==='paid'?'Payment finalized. Your feed is ready.':'Payment '+invoice.state);await activity();}
      return true;
    }
    return false;
  }
  return {feeds,createFeed,perpData,perps,refreshPerps,predictions,refreshPredictions,stocks,handle,resume,review,submitInline,uncertainInline,recoverInline,pending:()=>[...pending(),...c.spotPending()],openPerpl:perplOrder,perplAsset,openPrediction:predict};
}
