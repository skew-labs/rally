/** Only invoked on the explicit first-party Android account / wallet bridge. */
export async function nativeLink(c) {
 const {S,api,$,esc,notify,trade,finance,nad,launch,needAccount,boot}=c;
 const p=new URLSearchParams(location.search),id=p.get('nativeRequest');
 if(location.pathname==='/connect-native'&&/^[a-f0-9]{32}$/.test(id||'')){
  const panel=document.createElement('section');panel.className='r-native-pair';
  panel.style.cssText='margin:20px;padding:24px;background:var(--surface);border:1px solid var(--line);border-radius:20px;display:grid;gap:14px';
  $('#page').prepend(panel);
  let finished=false;
  const paint=async()=>{
   if(finished||!panel.isConnected)return;
   try{
    const request=await api('/api/native/request?id='+id);
    if(!panel.isConnected)return;
    panel.innerHTML='<h2>Connect Rally for Android</h2><p>Match code <b>'+esc(request.code)+'</b> with your app.</p><p class="r-note">Connect only if you started this request. Wallet signing stays with your wallet.</p>'+(S.boot.me?'<p>@'+esc(S.boot.me.handle)+'</p><button class="r-btn primary" data-native-approve>Connect account</button><button class="r-btn" data-native-deny>Cancel</button>':'<button class="r-btn primary" data-action="account">Sign in</button>');
    panel.querySelector('[data-native-approve]')?.addEventListener('click',()=>approve(true));
    panel.querySelector('[data-native-deny]')?.addEventListener('click',()=>approve(false));
   }catch(e){finished=true;panel.textContent=e.message;}
  };
  const approve=async allow=>{
   const buttons=[...panel.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
   try{await api('/api/native/approve',{id,allow});finished=true;clearInterval(timer);panel.innerHTML='<h2>'+ (allow?'Connected':'Cancelled')+'</h2><a class="r-btn primary" href="/native-return">Return to Rally</a>';}
   catch(e){notify(e.message);buttons.forEach(b=>b.disabled=false);}
  };
  await paint();const timer=setInterval(async()=>{if(document.hidden||finished)return;await boot(true);await paint();},3000);
  setTimeout(()=>clearInterval(timer),180000);
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
