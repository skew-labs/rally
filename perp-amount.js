// Exact decimal conversion. USD is position value, not venue collateral or a fill.
function decimal(value){
 const text=String(value??'').trim();if(text.length>96||! /^(?:\d+\.?\d*|\.\d+)$/.test(text))throw Error('Enter an amount');
 const [whole,fraction='']=text.split('.');if(fraction.length>36)throw Error('Amount has too many decimals');
 return {n:BigInt((whole||'0')+fraction),scale:fraction.length};
}
const power=n=>10n**BigInt(n);
function plain(n,scale){const text=n.toString().padStart(scale+1,'0');return scale?(((text.slice(0,-scale)||'0')+'.'+text.slice(-scale)).replace(/\.?0+$/,'')||'0'):text;}
function multiply(a,b){return plain(a.n*b.n,a.scale+b.scale);}
function divide(a,b,scale,up=false){const n=a.n*power(b.scale+scale),d=b.n*power(a.scale);if(d===0n)throw Error('Enter a price');return plain(n/d+(up&&n%d?1n:0n),scale);}
export function perpAmount(value,mode,price,precision=8,leverage=1){
 try{
  if(!['quantity','usd'].includes(mode)||!Number.isInteger(precision)||precision<0||precision>18||!Number.isInteger(Number(leverage))||Number(leverage)<1||Number(leverage)>10000)throw Error('Invalid order settings');
  const input=decimal(value),mark=decimal(price);if(input.n<=0n||mark.n<=0n)throw Error('Enter an amount and price');
  const quantity=mode==='usd'?divide(input,mark,precision):plain(input.n,input.scale),q=decimal(quantity);
  if(q.n<=0n)throw Error('Amount is below the minimum quantity');
  if(q.scale>precision)throw Error('Use up to '+precision+' decimals');
  const notional=multiply(q,mark),margin=divide(decimal(notional),decimal(leverage),6,true);
  return {valid:true,quantity,notional,margin,rounded:mode==='usd'&&decimal(notional).n*power(input.scale)!==input.n*power(decimal(notional).scale)};
 }catch(e){return {valid:false,quantity:'',notional:'',margin:'',error:e.message};}
}
export function moneyAmount(value){const n=Number(value);return Number.isFinite(n)?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:n>0&&n<.01?6:2}).format(n):'—';}

export function bindPerpAmount(form,market,{collateral='AUSD',margin=true}={}){
 const quantity=form.elements.quantity;if(!quantity)return;
 const field=quantity.closest('.r-field'),precision=Number(market.lotDecimals??10),symbol=market.baseSymbol||market.symbol;
 const label=document.createElement('label');label.className='r-perp-input-label';label.textContent='Position size';label.htmlFor=form.id+'-size';
 const modes=document.createElement('div');modes.className='r-perp-unit-switch';modes.setAttribute('role','group');modes.setAttribute('aria-label','Position amount unit');
 const input=document.createElement('input');input.id=label.htmlFor;input.type='text';input.inputMode='decimal';input.placeholder='0';input.autocomplete='off';input.spellcheck=false;input.required=true;
 const head=document.createElement('div');head.className='r-perp-input-head';head.append(label,modes);
 const equivalent=document.createElement('output');equivalent.className='r-perp-equivalent';equivalent.setAttribute('aria-live','off');
 const meta=document.createElement('dl');meta.className='r-perp-estimate';meta.innerHTML='<div><dt>Position value</dt><dd data-notional>—</dd></div>'+(margin?'<div><dt>Est. margin · '+collateral+'</dt><dd data-margin>—</dd></div>':'');
 const foot=document.createElement('small');foot.className='r-perp-estimate-note';foot.textContent=margin?'Margin excludes fees.':'Collateral is entered separately.';
 const shortcuts=document.createElement('div');shortcuts.className='r-perp-shortcuts';shortcuts.setAttribute('role','group');shortcuts.setAttribute('aria-label','USD position shortcuts');
 field.replaceChildren(head,input,equivalent);field.classList.add('r-perp-amount');field.after(shortcuts,meta,foot);quantity.type='hidden';quantity.required=false;form.append(quantity);
 let mode='quantity';form.perpAmountInput=input;
 const buttons=['quantity','usd'].map(unit=>{const b=document.createElement('button');b.type='button';b.textContent=unit==='quantity'?symbol:'USD';b.dataset.amountMode=unit;
  b.onclick=()=>{if(input.readOnly||form.dataset.pending==='true'||mode===unit)return;const r=read();if(r.valid)input.value=unit==='usd'?r.notional:r.quantity;mode=unit;update();input.dispatchEvent(new Event('input',{bubbles:true}));b.focus({preventScroll:true});};modes.append(b);return b;});
 const presets=['10','25','50'].map(value=>{const b=document.createElement('button');b.type='button';b.textContent='$'+value;b.dataset.positionPreset=value;b.onclick=()=>{if(input.readOnly||form.dataset.pending==='true')return;mode='usd';input.value=value;update();input.dispatchEvent(new Event('input',{bubbles:true}));b.focus({preventScroll:true});};shortcuts.append(b);return b;});
 function read(){return perpAmount(input.value,mode,form.elements.limit?.value||market.mark,precision,form.elements.leverage?.value||1);}
 function update(){
  const r=read();quantity.value=r.valid?r.quantity:'';form.dataset.amountValid=String(r.valid);form.dataset.amountMode=mode;
  buttons.forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.amountMode===mode));b.disabled=input.readOnly;});
  presets.forEach(b=>{b.disabled=input.readOnly;b.setAttribute('aria-pressed',String(mode==='usd'&&input.value===b.dataset.positionPreset));});
  input.setAttribute('aria-invalid',String(Boolean(input.value)&&!r.valid));equivalent.textContent=r.valid?(mode==='quantity'?'≈ '+moneyAmount(r.notional):'≈ '+r.quantity+' '+symbol)+(r.rounded?' · Rounded down':''):input.value?r.error:'Enter '+(mode==='quantity'?symbol:'USD')+' amount';
  meta.querySelector('[data-notional]').textContent=r.valid?moneyAmount(r.notional):'—';if(margin)meta.querySelector('[data-margin]').textContent=r.valid?r.margin+' '+collateral:'—';
 }
 input.addEventListener('input',update);form.addEventListener('change',update);form.elements.limit?.addEventListener('input',update);
 // Existing recovery restores the concrete quantity before the UI is refreshed.
 const observer=new MutationObserver(()=>{input.readOnly=quantity.readOnly||form.dataset.pending==='true';update();});observer.observe(form,{attributes:true,attributeFilter:['data-pending']});
 form.restorePerpAmount=()=>{input.value=quantity.value;mode='quantity';update();};form.refreshPerpAmount=update;
 update();return ()=>observer.disconnect();
}
