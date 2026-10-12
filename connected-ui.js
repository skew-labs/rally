// Shared discovery presentation. No execution, wallet or permission changes.
export function algorithmRow(c,f,title,roi){
 const {S,esc,avatar}=c,creator=S.boot.people?.find(p=>p.id===f.owner)||{id:f.owner,...f.creator,name:f.creator?.name||'Rally',handle:f.creator?.handle||'rally'};
 const measured=roi!=null&&Number.isFinite(roi),paid=Number(f.priceRaw)>0;
 const byline=creator.name+(f.research?.wallet?' · '+f.research.wallet.slice(-4):'');
 return `<button class="rc-algorithm-row" data-feed="${esc(f.id)}" data-wallet="${Boolean(f.research?.wallet)}" data-action="algorithm-preview" data-id="${esc(f.id)}" aria-label="Preview ${esc(title)}">${avatar(creator)}<span class="rc-row-identity"><b>${esc(title)}</b><small>${esc(byline)}</small></span><span class="rc-row-result"><b class="${measured?roi>=0?'positive':'negative':''}">${measured?(roi>0?'+':'')+roi.toLocaleString('en-US',{maximumFractionDigits:1})+'%':'—'}</b><small>${measured?'Sampled wallet ROI':'No verified return'}</small></span><span class="rc-row-price"><b>${paid?esc(f.price)+' USDC':'Free'}</b><small>${paid?(f.access?'Subscribed':(f.periodDays||30)+' days'):'Preview'}</small></span></button>`;
}

// The chart stays mounted when lower information changes. Tabs never rebuild it.
export function detailTabs(c,{host,holders,facts,asset,social}){
 if(!host||host.querySelector(':scope>.rc-detail-tabs'))return;
 const {esc,S}=c,community=(S.boot?.communities||[]).find(x=>[x.token?.address,x.token?.asset?.id].some(a=>a&&String(a).toLowerCase()===String(asset.id).toLowerCase()));
 const root=document.createElement('section');root.className='rc-detail-tabs';
 const tabs=[...(holders?[['holders','Holders']]:[]),['community','Community'],...(facts?[['details','Details']]:[])];
 root.innerHTML=`<div class="rc-info-tabs" role="tablist" aria-label="Token information">${tabs.map(([id,label],i)=>`<button role="tab" id="rc-tab-${id}" aria-controls="rc-pane-${id}" aria-selected="${i===0}" tabindex="${i===0?0:-1}" data-info-tab="${id}">${label}</button>`).join('')}</div>${tabs.map(([id],i)=>`<div class="rc-info-pane" role="tabpanel" id="rc-pane-${id}" aria-labelledby="rc-tab-${id}" ${i?'hidden':''}></div>`).join('')}`;
 if(holders)root.querySelector('#rc-pane-holders').append(holders);
 if(facts)root.querySelector('#rc-pane-details').append(facts);
 const pane=root.querySelector('#rc-pane-community');
 pane.innerHTML=community?`<button class="rc-community-link" data-action="community" data-id="${esc(community.id)}"><span><b>${esc(community.name)}</b><small>${Number(community.members)||0} members</small></span><span aria-hidden="true">↗</span></button>`:`<p class="rc-quiet">No linked community yet</p>`;
 if(social)pane.append(social);
 if(facts?.tagName==='DETAILS')facts.open=true;
 const select=button=>{root.querySelectorAll('[role=tab]').forEach(b=>{const selected=b===button;b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;root.querySelector('#'+b.getAttribute('aria-controls')).hidden=!selected;});};
 root.addEventListener('click',e=>{const button=e.target.closest('[data-info-tab]');if(button)select(button);});
 root.addEventListener('keydown',e=>{const button=e.target.closest('[data-info-tab]');if(!button||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const buttons=[...root.querySelectorAll('[role=tab]')],index=buttons.indexOf(button),next=buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:(index+(e.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length];select(next);next.focus();});
 host.append(root);return root;
}

// Existing nad.fun form and its submit handler are reused unchanged.
export function nadPresentation(c,t,host){
 if(!host?.isConnected||host.classList.contains('rc-token-detail'))return;
 const {esc}=c,chart=host.querySelector('.nad-chart-section'),order=host.querySelector('.nad-token-bottom'),facts=host.querySelector('.r-checkout-token-facts')||host.querySelector('.nad-facts'),social=host.querySelector('#nad-launch-social');
 const holders=host.querySelector('#nad-holders');
 chart?.after(order);detailTabs(c,{host:chart,holders,facts,asset:t,social});
 const checkout=document.createElement('div');checkout.className='rc-token-checkout';checkout.hidden=true;
 checkout.innerHTML='<button class="rc-back-chart" type="button">‹ Back to chart</button>';
 order.before(checkout);checkout.append(order);
 const dock=document.createElement('footer');dock.className='rc-token-dock';
 dock.innerHTML=`<button type="button" class="rc-buy" data-open-order="buy" ${t.locked||t.tradeSupported===false?'disabled':''}>Buy <span>${esc(t.symbol)}</span></button><button type="button" class="rc-sell" data-open-order="sell" ${t.locked||t.tradeSupported===false?'disabled':''}>Sell</button>`;
 host.classList.add('rc-token-detail');if(host.closest('.r-nad-panel'))host.after(dock);else host.append(dock);
 const scroll=host.closest('.r-nad-content')||document.scrollingElement;let offset=0;
 function show(side){offset=scroll.scrollTop;chart.hidden=true;checkout.hidden=false;dock.hidden=true;host.classList.add('rc-order-open');order.querySelector(`[data-action=nad-side][data-id=${side}]`)?.click();scroll.scrollTop=0;requestAnimationFrame(()=>order.querySelector('input[name=amount]')?.focus({preventScroll:true}));}
 dock.addEventListener('click',e=>{const b=e.target.closest('[data-open-order]');if(b&&!b.disabled)show(b.dataset.openOrder);});
 checkout.querySelector('.rc-back-chart').onclick=()=>{if(order.querySelector('form')?.dataset.pending==='true')return;document.activeElement?.blur();chart.hidden=false;checkout.hidden=true;dock.hidden=false;host.classList.remove('rc-order-open');scroll.scrollTop=offset;dock.querySelector('button').focus({preventScroll:true});};
 if(c.S.nadOverlay?.checkout)dock.querySelector('[data-open-order="'+c.S.nadSide+'"]')?.click();
}

export function tokenPanelMotion(panel,source,closing=false){
 if(!panel||matchMedia('(prefers-reduced-motion:reduce)').matches)return null;
 panel.getAnimations().forEach(a=>a.cancel());panel.style.animation='none';
 const rect=panel.getBoundingClientRect(),origin=source?.getBoundingClientRect();
 if(origin)panel.style.transformOrigin=`${Math.max(0,Math.min(rect.width,origin.x+origin.width/2-rect.x))}px ${Math.max(0,Math.min(rect.height,origin.y+origin.height/2-rect.y))}px`;
 const from={opacity:0,transform:innerWidth<=760?'translateY(28px)':'translateX(16px) scale(.985)'},to={opacity:1,transform:'none'};
 return panel.animate(closing?[to,from]:[from,to],{duration:closing?140:220,easing:'cubic-bezier(.22,.8,.24,1)',fill:'both'});
}
