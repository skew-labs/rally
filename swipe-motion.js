// One paging owner for touch, trackpad, buttons and keys. Selection and media
// change only at rest; adjacent cards stay mounted during the movement.
// This module never signs, quotes, submits, or touches account authority.
export function swipePaging({deck,index,count,select,available}){
  const reduced=matchMedia('(prefers-reduced-motion: reduce)'),events=new AbortController();
  let frame=0,tween=null,drag=null,externalTimer=0,wheelAt=0,wheelDirection=0,wheelDistance=0,wheelCommitted=false,disposed=false;
  const limit=i=>Math.max(0,Math.min(count()-1,i)),height=()=>deck.clientHeight;
  const controlled=()=>Boolean(tween||drag);
  function stop(){cancelAnimationFrame(frame);frame=0;tween=null;clearTimeout(externalTimer);externalTimer=0;}
  function own(){deck.style.scrollSnapType='none';deck.classList.add('is-paging');deck.querySelectorAll('[data-swipe-index]').forEach(el=>{el.inert=false;});}
  function rest(target){
    if(disposed)return;
    target=limit(target);select(target);deck.scrollTop=target*height();
    deck.querySelectorAll('[data-swipe-index]').forEach(el=>{el.inert=Number(el.dataset.swipeIndex)!==target;});
    tween=null;drag=null;deck.classList.remove('is-paging');deck.style.removeProperty('scroll-snap-type');
  }
  function to(target,velocity=null){
    target=limit(target);const from=deck.scrollTop,end=target*height();stop();drag=null;own();
    if(reduced.matches||Math.abs(end-from)<.5){rest(target);return;}
    const duration=Math.max(160,Math.min(280,160+Math.abs(end-from)/height()*120));
    // Preserve release speed while decelerating to rest, with no overshoot.
    const tangent=velocity===null?3:Math.max(0,Math.min(3,velocity*duration/(end-from)));
    tween={target,from,end,start:performance.now(),duration,tangent};
    const tick=now=>{
      if(!tween||disposed)return;
      const t=tween,p=Math.min(1,(now-t.start)/t.duration),eased=p*p*(3-2*p)+t.tangent*p*(1-p)*(1-p);
      deck.scrollTop=t.from+(t.end-t.from)*eased;
      if(p<1)frame=requestAnimationFrame(tick);else{frame=0;rest(t.target);}
    };frame=requestAnimationFrame(tick);
  }
  function step(direction){
    if(disposed||!available()||drag)return;
    const target=limit(index()+Math.sign(direction));if(tween?.target===target)return;to(target);
  }
  function begin(){
    if(disposed||!available())return false;
    const origin=deck.scrollTop;stop();own();drag={origin,index:index()};return true;
  }
  function move(dy){
    if(!drag)return;
    const h=height(),lo=Math.max(0,(drag.index-1)*h),hi=Math.min((count()-1)*h,(drag.index+1)*h);
    deck.scrollTop=Math.max(lo,Math.min(hi,drag.origin-dy));
  }
  function end(dy,velocity,cancelled=false){
    if(!drag)return;
    const h=height(),i=drag.index,distance=deck.scrollTop-i*h;
    const flick=Math.abs(dy)>28&&Math.abs(velocity)>.38&&Math.sign(-velocity)===Math.sign(distance);
    const accepted=!cancelled&&(Math.abs(distance)>Math.max(48,h*.18)||flick);
    to(accepted?i+Math.sign(distance):i,-velocity);
  }
  function cancel(){stop();drag=null;rest(index());}
  function observe(){
    if(controlled()||disposed)return;
    clearTimeout(externalTimer);externalTimer=setTimeout(()=>{
      externalTimer=0;if(!available()){cancel();return;}to(Math.round(deck.scrollTop/height()));
    },100);
  }
  function wheel(e){
    if(!available()||drag||e.ctrlKey||e.metaKey||Math.abs(e.deltaY)<=Math.abs(e.deltaX)*1.15)return;
    const control=e.target.closest('input,textarea,select,[contenteditable="true"],video');
    if(control){if(control.matches('input')&&e.cancelable)e.preventDefault();return;}
    const direction=Math.sign(e.deltaY);if(!direction)return;
    const inner=e.target.closest('.r-swipe-content.is-scrollable,.r-quick-error,[data-swipe-ticket]');
    if(inner&&inner.scrollHeight>inner.clientHeight+1&&(direction>0?inner.scrollTop+inner.clientHeight<inner.scrollHeight-1:inner.scrollTop>1))return;
    if(e.cancelable)e.preventDefault();
    const now=performance.now();
    // The decaying trackpad tail is one gesture. Reversal is interruptible.
    if(direction!==wheelDirection||now-wheelAt>220&&!tween){wheelDistance=0;wheelCommitted=false;}
    wheelAt=now;wheelDirection=direction;if(wheelCommitted)return;
    const scale=e.deltaMode===1?16:e.deltaMode===2?height():1;wheelDistance+=Math.abs(e.deltaY)*scale;
    if(wheelDistance<24)return;wheelCommitted=true;step(direction);
  }
  document.addEventListener('wheel',wheel,{capture:true,passive:false,signal:events.signal});
  deck.addEventListener('scroll',observe,{passive:true,signal:events.signal});
  reduced.addEventListener('change',cancel,{signal:events.signal});
  return {step,begin,move,end,cancel,moving:controlled,dispose:()=>{disposed=true;stop();drag=null;events.abort();deck.classList.remove('is-paging');deck.style.removeProperty('scroll-snap-type');}};
}

export function swipeMotion({deck,choice,commit,available,paging}){
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const events=new AbortController();
  let drag=null,frame=0,animation=null,settling=false,suppress=null;
  const clear=card=>{if(!card)return;card.style.removeProperty('transform');card.style.removeProperty('--drag-progress');card.classList.remove('is-dragging','is-settling','drag-left','drag-right');card.querySelector('.r-swipe-intent')?.replaceChildren();};
  function cancel(){
    cancelAnimationFrame(frame);frame=0;animation?.cancel();animation=null;
    const current=drag;drag=null;settling=false;
    if(current?.card.hasPointerCapture?.(current.id))current.card.releasePointerCapture(current.id);
    if(current?.axis==='y')paging?.end(current.dy,0,true);
    clear(current?.card);
  }
  function paint(){
    frame=0;if(!drag||drag.axis!=='x')return;
    const {card,dx,width}=drag,side=dx<0?'left':'right',intent=choice(drag.index,side);
    const resistance=intent?1:.28,distance=Math.abs(dx)*resistance,bound=width*.35,x=Math.sign(dx)*(distance<=bound?distance:bound+(distance-bound)*.25);
    drag.visualX=x;
    if(!reduced.matches)card.style.transform=`translate3d(${x}px,0,0)`;
    card.style.setProperty('--drag-progress',String(Math.min(1,Math.abs(dx)/(width*.22))));
    card.classList.toggle('drag-left',side==='left');card.classList.toggle('drag-right',side==='right');
    const badge=card.querySelector('.r-swipe-intent');
    if(badge&&badge.textContent!==(intent?.label||'Unavailable'))badge.textContent=intent?.label||'Unavailable';
  }
  function down(e){
    if(!e.isPrimary){cancel();return;}
    if(settling||!available()||e.button!==0||e.target.closest('input,textarea,select,video,[contenteditable="true"],.r-quick-error,[data-swipe-ticket]'))return;
    const card=e.target.closest('[data-swipe-index]');if(!card)return;
    suppress=null;drag={card,id:e.pointerId,index:Number(card.dataset.swipeIndex),x:e.clientX,y:e.clientY,dx:0,dy:0,width:deck.clientWidth,axis:null,nativeScroll:e.target.closest('.r-swipe-content.is-scrollable'),horizontal:!e.target.closest('button,a,summary'),samples:[{x:e.clientX,y:e.clientY,t:performance.now()}]};
  }
  function move(e){
    if(!drag||drag.id!==e.pointerId)return;
    const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
    if(!drag.axis){
      if(Math.max(Math.abs(dx),Math.abs(dy))<10)return;
      if(Math.abs(dy)>Math.abs(dx)*1.15){
        const inner=drag.nativeScroll,canRead=inner&&(dy<0?inner.scrollTop+inner.clientHeight<inner.scrollHeight-1:inner.scrollTop>1);
        if(canRead||!paging?.begin()){cancel();return;}drag.axis='y';
      }
      else if(Math.abs(dx)>Math.abs(dy)*1.15&&drag.horizontal){drag.axis='x';drag.card.classList.add('is-dragging');}
      else if(Math.max(Math.abs(dx),Math.abs(dy))<24)return;
      else{cancel();return;}
      drag.card.setPointerCapture(e.pointerId);
    }
    if(e.cancelable)e.preventDefault();
    drag.dx=dx;drag.dy=dy;const t=performance.now();drag.samples.push({x:e.clientX,y:e.clientY,t});
    drag.samples=drag.samples.filter(s=>t-s.t<=100).slice(-8);
    if(drag.axis==='y'){paging.move(dy);return;}
    if(!frame)frame=requestAnimationFrame(paint);
  }
  async function up(e){
    if(!drag||drag.id!==e.pointerId)return;
    const current=drag;
    if(!current.axis){cancel();return;}
    if(e.cancelable)e.preventDefault();cancelAnimationFrame(frame);frame=0;
    const last=current.samples.at(-1),first=current.samples[0],t=performance.now();
    const axis=current.axis==='y'?'y':'x',velocity=t-last.t>100?0:(last[axis]-first[axis])/Math.max(1,last.t-first.t);
    suppress={id:e.pointerId,until:t+400};settling=true;
    if(current.card.hasPointerCapture(e.pointerId))current.card.releasePointerCapture(e.pointerId);
    if(current.axis==='y'){drag=null;settling=false;paging.end(current.dy,velocity);return;}
    paint();
    const intent=choice(current.index,current.dx<0?'left':'right');
    const flick=Math.abs(current.dx)>=44&&Math.abs(velocity)>.65&&Math.sign(velocity)===Math.sign(current.dx);
    const accepted=Boolean(intent&&(Math.abs(current.dx)>=Math.max(68,current.width*.22)||flick));
    current.card.classList.add('is-settling');current.card.style.setProperty('--drag-progress','0');
    if(!reduced.matches){
      const duration=accepted?180:240,omega=accepted?42:36,damping=.9,frequency=omega*Math.sqrt(1-damping*damping),x=current.visualX||0,v=Math.max(-1400,Math.min(1400,velocity*1000));
      // Sample the damped spring once at release, never in a pointer move.
      const frames=Array.from({length:24},(_,i)=>{const offset=i/23,t=duration*offset/1000,position=i===23?0:Math.exp(-damping*omega*t)*(x*Math.cos(frequency*t)+(v+damping*omega*x)/frequency*Math.sin(frequency*t));return {offset,transform:`translate3d(${position}px,0,0)`};});
      animation=current.card.animate(frames,{duration,easing:'linear'});
      try{await animation.finished;}catch{return;}
    }
    if(drag!==current||!current.card.isConnected)return;
    animation=null;clear(current.card);drag=null;settling=false;
    if(accepted&&available())await commit(current.index,intent.side);
  }
  deck.addEventListener('pointerdown',down,{signal:events.signal});
  deck.addEventListener('pointermove',move,{passive:false,signal:events.signal});
  deck.addEventListener('pointerup',e=>{up(e).catch(()=>cancel());},{signal:events.signal});
  deck.addEventListener('pointercancel',cancel,{signal:events.signal});
  // Touch starts with implicit capture on the image/text target. Its release
  // during transfer to the card is expected; only losing our card cancels.
  deck.addEventListener('lostpointercapture',e=>{if(!settling&&drag?.id===e.pointerId&&e.target===drag.card)cancel();},{signal:events.signal});
  deck.addEventListener('click',e=>{if(suppress&&e.detail!==0&&performance.now()<suppress.until&&e.pointerId===suppress.id){suppress=null;e.preventDefault();e.stopImmediatePropagation();}},{capture:true,signal:events.signal});
  return {cancel,isDragging:()=>Boolean(drag?.axis==='x'),dispose:()=>{cancel();events.abort();}};
}
