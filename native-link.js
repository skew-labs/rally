/** Only invoked on the explicit first-party Android account / wallet bridge. */
let stopPairing;
export async function nativeLink(c) {
 const {S,api,$,esc,notify,trade,finance,nad,launch,needAccount,boot,auth}=c;
 const p=new URLSearchParams(location.search),id=p.get('nativeRequest');
 if(location.pathname==='/connect-native'&&/^[a-f0-9]{32}$/.test(id||'')){
  stopPairing?.();document.body.classList.add('r-native-auth');
  const panel=document.createElement('section');panel.className='r-native-pair';$('#page').replaceChildren(panel);
  let finished=false,timer;
  stopPairing=()=>{finished=true;clearTimeout(timer);};
  const paint=async()=>{
   if(finished||!panel.isConnected)return;
   try{
    const request=await api('/api/native/request?id='+id);
    if(!panel.isConnected)return;
    if(request.state!=='pending'){finished=true;panel.innerHTML='<h2>'+(['approved','consumed'].includes(request.state)?'Connected':'Cancelled')+'</h2><a class="r-btn primary full" href="/native-return">Return to Rally</a>';return;}
    panel.innerHTML='<div class="r-native-brand">rally<span>.</span></div><h2>'+(S.boot.me?'Continue to your app':'Connect your account')+'</h2>'+(S.boot.me?'<p class="r-note">Approve only if this code matches your Rally app.</p><button class="r-btn primary full" data-native-approve>Continue as @'+esc(S.boot.me.handle)+'</button><button class="r-btn full" data-native-deny>Cancel</button>':auth.buttons())+'<div class="r-native-code"><span>Rally for Android · Device code</span><b>'+esc(request.code)+'</b></div>';
    if(!S.boot.me)auth.bind();
    panel.querySelector('[data-native-approve]')?.addEventListener('click',()=>approve(true));
    panel.querySelector('[data-native-deny]')?.addEventListener('click',()=>approve(false));
   }catch(e){finished=true;panel.textContent=e.message;}
  };
  const approve=async allow=>{
   const buttons=[...panel.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
   try{await api('/api/native/approve',{id,allow});finished=true;clearTimeout(timer);panel.innerHTML='<div class="r-native-brand">rally<span>.</span></div><h2>'+ (allow?'You’re connected':'Cancelled')+'</h2><a class="r-btn primary full" href="/native-return">Return to Rally</a>';}
   catch(e){notify(e.message);buttons.forEach(b=>b.disabled=false);}
  };
  await paint();timer=setTimeout(()=>{if(!finished&&panel.isConnected){finished=true;panel.innerHTML='<h2>Connection expired</h2><p class="r-note">Start again in your Rally app.</p><a class="r-btn primary full" href="/native-return">Return to Rally</a>';}},600000);
  return;
 }
 if(location.pathname!=='/native-wallet')return;
 const back=document.createElement('a');back.href='/native-return';back.className='r-btn';back.textContent='Return to Rally';back.style.cssText='position:fixed;right:16px;top:12px;z-index:101;background:var(--surface);';document.body.append(back);
 const expected=p.get('account');if(expected&&!S.boot.me){await needAccount(()=>nativeLink(c));return;}if(expected&&S.boot.me?.id!==expected){notify('Sign in with the account connected to your Android app.');return;}
 const action=p.get('nativeAction');
 if(action==='launch'){await needAccount(()=>launch.create());return;}
 if(action==='subscribe'){const feed=p.get('feed');if(feed&&S.boot.feeds.some(f=>f.id===feed))await needAccount(()=>finance.handle('subscribe-feed',feed,document.createElement('button')));return;}
 if(action!=='trade')return;
 const asset=p.get('asset'),kind=p.get('kind'),side=p.get('side')==='sell'?'sell':'buy',amount=p.get('amount')||'';
 if(!asset||asset.length>100||!/^\d+(?:\.\d{1,18})?$/.test(amount)||Number(amount)<=0){notify('Return to the app and choose an amount.');return;}
 if(kind==='perps'){
  const data=await finance.perpData();const market=data.markets.find(m=>String(m.id)===asset);
  if(!market||market.execution!=='wallet_transactions'){notify('This venue is not available for this order.');return;}
  await finance.openPerpl(asset,null,side==='sell'?'short':'long');
 }else if(kind==='prediction'){
  S.predictions=await api('/api/predictions');finance.openPrediction(asset,amount);
 }else{
  if(!S.tokens.some(t=>t.id===asset)){try{const token=await api('/api/market-asset?address='+encodeURIComponent(asset));if(!S.tokens.some(t=>t.id===token.id))S.tokens.push(token);}catch{}}
  if(p.get('venue')==='nadfun')await nad.open(asset,null,side);else await trade(asset,null,side,{amount});
 }
 const fill=()=>{const form=$('#nad-order-form')||$('#perpl-order-form')||$('#leverup-order-form')||$('#venue-order-form')||$('#prediction-form');const input=form?.elements.amount||form?.elements.quantity||form?.elements.margin||form?.elements.price||$('#swap-amount');if(input&&!input.value){input.value=amount;input.dispatchEvent(new Event('input',{bubbles:true}));} };
 fill();setTimeout(fill,700);
}
