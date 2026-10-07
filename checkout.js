// Presentation and input state only. Wallet and settlement handlers stay with their venues.
export function checkoutUI(c){
 const {S,$,token,trade,closeModal,invalidateQuote}=c,clocks=new Map(),bindings=new WeakMap();let timer,nadCleanup;
 const positive=value=>/^(?:\d+\.?\d*|\.\d+)$/.test(value.trim())&&Number.isFinite(Number(value))&&Number(value)>0;
 const sideOf=side=>['sell','short'].includes(side)?'sell':'buy';
 function intent(root,side){if(root)root.dataset.orderSide=sideOf(side);}
 function stages(root){root?.querySelector('.r-ticket-stages')?.remove();}
 function sides(node,side){
  if(!node)return;node.classList.add('r-ticket-sides');node.dataset.orderSide=sideOf(side);
  if(!node.querySelector('.r-ticket-side-pill')){const pill=document.createElement('span');pill.className='r-ticket-side-pill';pill.setAttribute('aria-hidden','true');node.prepend(pill);}
  node.querySelectorAll('button,label').forEach((el,i)=>{el.dataset.tradeSide=i?'sell':'buy';});
 }
 function leverage(form){
  const select=form.querySelector('select[name=leverage]');if(!select)return()=>{};
  const field=select.closest('.r-field'),box=document.createElement('div');box.className='r-ticket-leverage';
  const head=document.createElement('div'),title=document.createElement('span'),value=document.createElement('b');title.textContent='Leverage';head.append(title,value);
  const range=document.createElement('input');range.type='range';range.min='0';range.max=String(select.options.length-1);range.step='1';range.setAttribute('aria-label','Leverage');
  const ends=document.createElement('div');ends.className='r-ticket-leverage-ends';ends.innerHTML='<span>'+select.options[0].textContent+'</span><span>'+select.options[select.options.length-1].textContent+'</span>';
  box.append(head,range,ends);field.after(box);field.hidden=true;
  const sync=()=>{const index=Math.max(0,select.selectedIndex);range.value=String(index);value.textContent=select.options[index].textContent;range.setAttribute('aria-valuetext',value.textContent);range.style.setProperty('--range-fill',(index/Math.max(1,select.options.length-1)*100)+'%');range.disabled=select.disabled;};
  range.addEventListener('input',()=>{if(select.disabled)return;select.selectedIndex=Number(range.value);select.dispatchEvent(new Event('change',{bubbles:true}));sync();});select.addEventListener('change',sync);sync();return sync;
 }
 function perpPresentation(root,form){
  const venue=form.id==='perpl-order-form'?'Perpl':form.id==='leverup-order-form'?'LeverUp':root.querySelector('.r-collateral-inline>span')?.textContent.split(' · ')[0];
  const symbol=root.querySelector('#modal-title').textContent.replace(/ perpetual$/,'');const market=S.perps?.markets.find(m=>m.venue===venue&&m.symbol===symbol);
  if(market){const title=root.querySelector('#modal-title');title.classList.add('r-checkout-asset-title');title.insertAdjacentHTML('afterbegin',c.logo(c.perplAsset(market),true));
   const bar=document.createElement('div');bar.className='r-ticket-market-reference';const label=document.createElement('span'),price=document.createElement('b');label.textContent='Reference price';price.textContent=market.mark==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumSignificantDigits:7}).format(Number(market.mark));bar.append(label,price);form.querySelector('.r-order-directions').after(bar);
  }
  form.querySelector('input[name=quantity],input[name=amount]')?.closest('.r-field')?.classList.add('r-ticket-amount-field');
  const direction=form.querySelector('input[name=direction]:checked')?.value;intent(root,direction);sides(form.querySelector('.r-order-directions'),direction);stages(root);
  form.addEventListener('change',e=>{if(e.target.name==='direction'){intent(root,e.target.value);sides(form.querySelector('.r-order-directions'),e.target.value);}});
  const syncLeverage=leverage(form),limit=form.querySelector('input[name=limit]');let syncOptions=()=>{};
  if(limit){const details=document.createElement('details');details.className='r-ticket-options';const summary=document.createElement('summary'),label=document.createElement('span'),value=document.createElement('b');label.textContent='Price & options';summary.append(label,value);details.append(summary);(form.querySelector('.r-ticket-leverage')||form.querySelector('.r-ticket-amount-field')).after(details);details.append(limit.closest('.r-field'));const reduce=form.querySelector('input[name=reduceOnly]')?.closest('.r-checkbox');if(reduce)details.append(reduce);
   syncOptions=()=>{value.textContent=positive(limit.value)?'$'+new Intl.NumberFormat('en-US',{maximumSignificantDigits:7}).format(Number(limit.value)):'Enter price';value.title=limit.value?'$'+limit.value:'';};limit.addEventListener('input',syncOptions);syncOptions();}
  return()=>{syncLeverage();syncOptions();};
 }
 function fold(node,title,cls=''){
  if(!node)return;const box=document.createElement('details');box.className='r-checkout-fold '+cls;const label=document.createElement('summary');label.textContent=title;node.before(box);box.append(label,node);return box;
 }
 function footer(parent,button,error){const foot=document.createElement('div');foot.className='r-checkout-footer';parent.append(foot);if(error)foot.append(error);foot.append(button);return foot;}
 function valid(root){bindings.get(root)?.();}
 function presets(root,input,unit){
  const name=unit();const previous=root.querySelector('.r-checkout-presets');if(previous?.dataset.unit===name)return;previous?.remove();const values=name==='MON'?[1,5,10]:['USDC','AUSD'].includes(name)?[5,10,25]:[];if(!values.length)return;
  const row=document.createElement('div');row.className='r-checkout-presets';row.dataset.unit=name;row.setAttribute('role','group');row.setAttribute('aria-label','Amount shortcuts');
  for(const n of values){const b=document.createElement('button');b.type='button';b.textContent=n+' '+name;b.onclick=()=>{if(input.readOnly||input.disabled)return;input.value=String(n);input.dispatchEvent(new Event('input',{bubbles:true}));input.focus({preventScroll:true});};row.append(b);}
  input.closest('.r-swap-input,.nad-amount')?.after(row);
 }
 function amount(root,input,button,{unit,label,busy=()=>false,available=()=>true}){
  input.autocomplete='off';input.spellcheck=false;
  const update=()=>{if(!root.isConnected||busy())return;if(root.dataset.orderState){button.disabled=true;button.textContent=root.dataset.orderState==='unknown'?'Check your wallet':'Submitted';return;}if(!available()){button.disabled=true;return;}const ok=positive(input.value);input.setAttribute('aria-invalid',String(Boolean(input.value)&&!ok));button.disabled=!ok;if(!ok)button.textContent=input.value?'Enter a valid amount':'Enter amount';else button.textContent=label();root.querySelectorAll('.r-checkout-presets button').forEach(b=>b.classList.toggle('selected',b.textContent===input.value+' '+unit()));};
  bindings.set(root,update);input.addEventListener('input',update);if(!input.form)input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.isComposing&&!button.disabled){e.preventDefault();button.click();}});presets(root,input,unit);update();
 }
 function watch(root,q,button,current,expire,label='Quote'){
  clocks.get(root)?.badge.remove();if(!Number.isFinite(q.expires))return;
  const badge=document.createElement('div');badge.className='r-checkout-clock';badge.setAttribute('role','status');badge.setAttribute('aria-live','off');root.append(badge);clocks.set(root,{q,button,current,expire,badge,label});tick();if(!timer&&clocks.size)timer=setInterval(tick,1000);
 }
 function tick(){
  for(const [root,x] of clocks){if(!root.isConnected||!x.current()){x.badge.remove();clocks.delete(root);continue;}const left=Math.max(0,Math.ceil(x.q.expires-Date.now()/1000));x.badge.textContent=x.label+' · '+left+'s';if(!left){clocks.delete(root);x.badge.textContent=x.label+' expired';x.expire();}}
  if(!clocks.size){clearInterval(timer);timer=null;}
 }
 function dialog(){
  const root=$('.r-modal'),form=root?.querySelector('#perpl-order-form,#leverup-order-form,#venue-order-form,#prediction-form,#collateral-form,#venue-account-form'),button=root?.querySelector('#financial-submit,#confirm-swap,#approve-token')||form?.querySelector('[type=submit]');if(!root||!button)return;
  root.classList.add('r-checkout-dialog');const head=root.querySelector('.r-modal-head'),body=document.createElement('div');body.className='r-checkout-scroll';const error=root.querySelector('.r-form-error');
  const syncLeverage=form?.querySelector('input[name=direction]')?perpPresentation(root,form):()=>{};
  if(button.id==='confirm-swap'||button.id==='approve-token'){intent(root,S.trade?.side);stages(root,'review');}
  if(form){
   const children=[...root.children].filter(x=>x!==head&&x!==form&&!x.classList.contains('r-ticket-stages'));form.prepend(body);for(const node of children)body.append(node);for(const node of [...form.children])if(node!==body&&node!==button&&node!==error)body.append(node);
   form.classList.add('r-checkout-form');footer(form,button,error);
   const unavailable=button.disabled,inputs=[...form.querySelectorAll('input[required]')];const update=()=>{syncLeverage();if(form.dataset.pending==='true')return;if(form.dataset.orderState){button.disabled=true;button.textContent=form.dataset.orderState==='unknown'?'Check your wallet':'Submitted';return;}const direction=form.querySelector('input[name=direction]:checked')?.value,kind=form.querySelector('[name=kind]')?.value;if(direction)button.textContent=direction==='short'?'Sell / Short':'Buy / Long';else if(form.querySelector('[name=order]')?.value)button.textContent='Cancel order';else if(form.querySelector('[name=position]')?.value)button.textContent='Close position';else if(kind)button.textContent=kind==='withdraw'?'Withdraw':kind==='deposit'?'Deposit':kind==='create'?'Create portfolio':kind==='cancel'?'Cancel order':'Continue';button.disabled=unavailable||!inputs.every(i=>positive(i.value));};bindings.set(form,update);inputs.forEach(i=>i.addEventListener('input',update));form.addEventListener('change',update);update();
  }else{
   for(const node of [...root.children])if(node!==head&&node!==button&&node!==error&&!node.classList.contains('r-ticket-stages'))body.append(node);root.append(body);const foot=footer(root,button,error);if(button.id==='confirm-swap')editButton(foot,'Edit amount',()=>{closeModal();syncSpot();$('#swap-amount')?.focus({preventScroll:true});});
  }
  root.querySelectorAll('.r-review-fields>div').forEach(row=>{if(['Pay','Estimated received','Total','Quantity','Stake'].includes(row.querySelector('dt')?.textContent))row.classList.add('r-checkout-review-value');});
 }
 function editButton(root,label,edit){const b=document.createElement('button');b.type='button';b.className='r-checkout-edit';b.textContent=label;b.onclick=()=>{if(S.financialBusy||S.trade?.busy||S.trade?.submittedHash)return;edit();};root.prepend(b);}
 function spot(r,subject,mount){
  const root=$('.r-trade-panel'),scroll=$('.r-trade-scroll'),box=$('.r-swap-box'),button=$('#swap-button');if(!root||!box)return;root.classList.add('r-checkout-spot');intent(root,r.side);stages(root);$('.r-trade-price').after(box);
  const title=$('.r-swap-title h3'),modes=document.createElement('div');modes.className='r-checkout-sides';modes.setAttribute('role','group');modes.setAttribute('aria-label','Order side');
  for(const side of ['buy','sell']){const b=document.createElement('button');b.type='button';b.textContent=side==='buy'?'Buy':'Sell';b.setAttribute('aria-pressed',String(r.side===side));b.onclick=()=>{if(r.busy||r.submittedHash||side===r.side)return;const f=r.returnFocus;trade(subject.id,r.context,side);if(S.trade)S.trade.returnFocus=f;const next=$('.r-trade-panel');if(next){next.style.animation='none';const pill=next.querySelector('.r-ticket-side-pill');if(pill&&!matchMedia('(prefers-reduced-motion: reduce)').matches)pill.animate([{transform:side==='sell'?'translateX(0)':'translateX(100%)'},{transform:side==='sell'?'translateX(100%)':'translateX(0)'}],{duration:220,easing:'cubic-bezier(.22,1,.36,1)'});requestAnimationFrame(()=>next.querySelector('[data-trade-side="'+side+'"]')?.focus({preventScroll:true}));}};modes.append(b);}sides(modes,r.side);title.replaceWith(modes);
  const pay=$('.r-pay-select');if(r.side==='sell'){pay.disabled=true;pay.removeAttribute('data-action');pay.classList.add('r-checkout-fixed-asset');pay.querySelector('svg:last-child')?.remove();}
  const foot=footer(root,button,$('#swap-error'));foot.append($('.r-trade-disclosure'),$('#order-status'));const input=$('#swap-amount');amount(root,input,button,{unit:()=>token(r.input)?.symbol||'',label:()=>S.boot.wallet?(r.side==='sell'?'Sell':'Buy'):'Connect wallet',busy:()=>r.busy||Boolean(r.submittedHash)});
  $('.r-swap-output>span').textContent='Estimated receive';
  const details=fold($('#quote-details'),'Fees & minimum','r-checkout-fees');details?.setAttribute('aria-label','Quote details');
  const chart=fold($('#trade-chart')||$('.r-pool-info'),'Chart','r-checkout-chart');if(chart){let mounted=false;chart.addEventListener('toggle',()=>{if(chart.open&&!mounted){mounted=true;mount();}});}
  $('.r-contract')?.classList.add('r-checkout-contract');const compare=$('[data-action=compare-routes]');const update=()=>{if(compare)compare.disabled=!positive(input.value)||r.busy;};input.addEventListener('input',update);update();
  scroll.scrollTop=0;
 }
 function syncSpot(){const r=S.trade,root=$('.r-trade-panel');if(!r||!root)return;presets(root,$('#swap-amount'),()=>token(r.input)?.symbol||'');valid(root);}
 function spotQuote(r,q){const root=$('.r-checkout-spot .r-checkout-footer');if(root)watch(root,q,$('#swap-button'),()=>S.trade===r&&r.quote===q,()=>{if(r.busy||S.modal)return;$('#swap-button').textContent=r.side==='sell'?'Sell':'Buy';});}
 function spotBusy(r,busy){const root=$('.r-trade-panel');if(!root||S.trade!==r)return;$('#swap-amount').readOnly=busy;root.querySelectorAll('.r-checkout-presets button,.r-ticket-sides button,.r-pay-select,[data-action=compare-routes]').forEach(b=>b.disabled=busy||b.classList.contains('r-checkout-fixed-asset'));if(!busy&&!r.submittedHash){valid(root);const compare=$('[data-action=compare-routes]');if(compare)compare.disabled=!positive(r.amount);}}
 function nad(t){
  nadCleanup?.();
  const root=$('#nad-order-form'),section=$('.nad-token-bottom'),chart=$('.nad-chart-section'),button=root?.querySelector('[type=submit]');if(!root)return;root.classList.add('r-checkout-nad');chart?.before(section);const facts=$('.nad-facts');if(facts){const folded=fold(facts,'Token details','r-checkout-token-facts');chart?.after(folded);}
  const foot=footer(root,button,root.querySelector('.r-form-error'));foot.classList.add('r-checkout-token-footer');const note=document.createElement('span');note.className='r-checkout-footer-label';note.textContent='nad.fun · Monad';foot.prepend(note);
  const main=$('#main');let frame;const fit=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{if(!root.isConnected)return;const rect=main.getBoundingClientRect();foot.style.left=rect.left+'px';foot.style.width=rect.width+'px';});};const observer=new ResizeObserver(fit);observer.observe(main);fit();const resize=()=>{if(!root.isConnected){observer.disconnect();window.removeEventListener('resize',resize);return;}fit();};window.addEventListener('resize',resize);nadCleanup=()=>{observer.disconnect();cancelAnimationFrame(frame);window.removeEventListener('resize',resize);};
  intent(root,S.nadSide);sides($('.nad-order .r-order-directions'),S.nadSide);
  amount(root,root.elements.amount,button,{unit:()=>S.nadSide==='sell'?t.symbol:t.quoteSymbol||'MON',label:()=>S.nadSide==='sell'?'Sell':'Buy',busy:()=>root.dataset.pending==='true',available:()=>!S.nadDetail.locked&&S.nadDetail.tradeSupported!==false});
 }
 function nadSide(){const root=$('#nad-order-form');if(root){intent(root,S.nadSide);sides($('.nad-order .r-order-directions'),S.nadSide);presets(root,root.elements.amount,()=>S.nadSide==='sell'?S.nadDetail.symbol:S.nadDetail.quoteSymbol||'MON');valid(root);}}
 function nadQuote(q){const root=$('#nad-quote'),form=$('#nad-order-form');if(root)watch(root,q,form.querySelector('[type=submit]'),()=>S.nadQuote===q,()=>{S.nadQuote=null;root.replaceChildren();form.querySelector('[type=submit]').textContent=S.nadSide==='sell'?'Sell':'Buy';});}
 function formBusy(form,busy){form.dataset.pending=String(busy);form.querySelectorAll('input').forEach(i=>{if(['radio','checkbox','range'].includes(i.type))i.disabled=busy;else i.readOnly=busy;});form.querySelectorAll('select').forEach(i=>i.disabled=busy);if(!busy)valid(form);}
 return {formBusy,disposeNad:()=>{nadCleanup?.();nadCleanup=null;},dialog,spot,syncSpot,spotQuote,spotBusy,nad,nadSide,nadQuote,valid,positive,chartVisible:()=>!!$('.r-checkout-chart')?.open};
}
