// Render geometry on the display frame clock. Canonical samples never interpolate.
export const tickLimit=240;
export function mergeTicks(previous,data,epoch){
  const points=new Map(data.reset||epoch!==data.epoch?[]:previous.map(p=>[p.id,p]));
  for(const p of data.points||[])if(Number.isSafeInteger(p.id)&&p.id>0&&Number.isFinite(p.time)&&p.time>0&&Number.isFinite(p.value)&&p.value>0)points.set(p.id,{id:p.id,time:p.time,value:p.value});
  return [...points.values()].sort((a,b)=>a.id-b.id).slice(-tickLimit);
}
export const easeTick=t=>1-(1-Math.min(1,Math.max(0,t)))**3;

export function livePriceChart(host,{mode='line',onObservation=()=>{}}={}){
  const canvas=document.createElement('canvas');canvas.className='r-live-price-canvas';canvas.setAttribute('role','img');host.replaceChildren(canvas);
  const ctx=canvas.getContext('2d'),motion=matchMedia('(prefers-reduced-motion: reduce)');
  let points=[],frame=0,start=0,progress=1,width=0,height=0,geometry=null,disposed=false,pointer=null,frames=0,drawMs=0;
  const price=v=>v.toLocaleString('en-US',{maximumSignificantDigits:7});
  function layout(){
    if(!width||!height||!points.length){geometry=null;return;}
    const visible=points.slice(-60),minimum=Math.min(...visible.map(p=>p.value)),high=Math.max(...visible.map(p=>p.value)),span=Math.max(high-minimum,high*.0005,1e-9),low=(minimum+high-span)/2,pad=18;
    const previous=geometry,sy=previous?span/previous.span:1,ty=previous?(height-pad)*(1-sy)-(low-previous.low)/previous.span*(height-pad*2):0;
    const last=visible.at(-1),first=visible[0],seconds=Math.max(30,last.time-first.time),count=Math.max(12,visible.length-1),plotWidth=width-18;
    const offsets=visible.map((p,i)=>({x:mode==='ticks'?plotWidth*(1-(visible.length-1-i)/count):plotWidth*(1-(last.time-p.time)/seconds),y:height-pad-(p.value-low)/span*(height-pad*2),p}));
    const path=new Path2D();offsets.slice(0,-1).forEach((p,i)=>i?path.lineTo(p.x,p.y):path.moveTo(p.x,p.y));
    const tip=offsets.at(-1),from=offsets.at(-2)||tip;
    geometry={offsets,path,tip,from,shift:Math.max(0,tip.x-from.x),low,span,sy,ty};
  }
  function draw(){
    const clock=performance.now();ctx.clearRect(0,0,width,height);if(!geometry)return;
    const {path,tip,from,shift,offsets,sy,ty}=geometry,p=easeTick(progress),x=from.x+(tip.x-from.x)*p,y=from.y+(tip.y-from.y)*p;
    ctx.save();ctx.translate((1-p)*shift,(1-p)*ty);ctx.scale(1,sy+(1-sy)*p);ctx.strokeStyle='#9178ff';ctx.lineWidth=2;ctx.lineCap='round';ctx.lineJoin='round';ctx.stroke(path);
    ctx.beginPath();ctx.moveTo(from.x,from.y);ctx.lineTo(x,y);ctx.stroke();ctx.fillStyle='#9178ff';ctx.globalAlpha=.12;ctx.beginPath();ctx.arc(x,y,7,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;ctx.beginPath();ctx.arc(x,y,3,0,Math.PI*2);ctx.fill();ctx.restore();
    if(pointer!==null){const nearest=offsets.reduce((a,b)=>Math.abs(b.x-pointer)<Math.abs(a.x-pointer)?b:a);ctx.strokeStyle='#979eac66';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(nearest.x,0);ctx.lineTo(nearest.x,height);ctx.stroke();onObservation(nearest.p);}
    frames++;drawMs+=performance.now()-clock;
  }
  function step(now){frame=0;if(disposed||document.hidden)return;progress=Math.min(1,(now-start)/220);draw();if(progress<1)frame=requestAnimationFrame(step);}
  function stop(){cancelAnimationFrame(frame);frame=0;progress=1;draw();}
  function size(){width=host.clientWidth;height=host.clientHeight;const scale=Math.min(devicePixelRatio||1,3);canvas.width=Math.round(width*scale);canvas.height=Math.round(height*scale);ctx.setTransform(scale,0,0,scale,0,0);layout();draw();}
  const resize=new ResizeObserver(size);resize.observe(host);
  function visibility(){if(document.hidden)stop();else{progress=1;size();}}
  function change(){if(motion.matches)stop();}
  document.addEventListener('visibilitychange',visibility);motion.addEventListener('change',change);
  canvas.onpointermove=e=>{pointer=e.clientX-canvas.getBoundingClientRect().left;cancelAnimationFrame(frame);frame=0;progress=1;draw();};canvas.onpointerleave=()=>{pointer=null;draw();onObservation(points.at(-1));};
  size();
  return {
    setMode(value){mode=value;progress=1;layout();canvas.setAttribute('aria-label',`${mode==='ticks'?'Price ticks':'Live price line'}, ${points.length} actual observations`);host.dataset.series=mode==='ticks'?'ticks':'live-line';draw();},
    setData(values,{reset=false}={}){const last=reset?null:points.at(-1),next=values.at(-1);if(reset)geometry=null;points=values.slice(-tickLimit);cancelAnimationFrame(frame);frame=0;layout();canvas.setAttribute('aria-label',`${mode==='ticks'?'Price ticks':'Live price line'}, ${points.length} actual observations`);host.dataset.points=String(points.length);host.dataset.series=mode==='ticks'?'ticks':'live-line';if(next)onObservation(next);progress=last&&next&&last.id!==next.id&&!document.hidden&&!motion.matches?0:1;start=performance.now();draw();if(progress<1)frame=requestAnimationFrame(step);},
    stats:()=>({frames,meanDrawMs:frames?drawMs/frames:0,samples:points.length,animating:!!frame}),
    dispose(){disposed=true;cancelAnimationFrame(frame);resize.disconnect();motion.removeEventListener('change',change);document.removeEventListener('visibilitychange',visibility);canvas.onpointermove=null;canvas.onpointerleave=null;canvas.remove();}
  };
}

export function streamPrices({host,api,asset,kind,mode='line',onStatus=()=>{}}){
  let points=[],epoch,cursor=0,timer,controller,disposed=false,generation=0;
  const chart=livePriceChart(host,{mode,onObservation:p=>{if(p)onStatus({point:p});}});
  async function poll(){
    if(disposed||document.hidden||!host.isConnected)return;
    const run=++generation;controller=new AbortController();
    try{
      const data=await api('/api/market-ticks?'+new URLSearchParams({asset,kind,after:String(cursor)}),undefined,{signal:controller.signal});
      if(disposed||run!==generation||!host.isConnected)return;
      if(String(data.asset)!==String(asset)||data.kind!==kind||data.observationType!=='price_update')throw Error('Tick identity changed');
      const reset=data.reset||epoch!==data.epoch,updated=mergeTicks(points,data,epoch),changed=updated.at(-1)?.id!==points.at(-1)?.id||reset;
      points=updated;epoch=data.epoch;cursor=data.cursor;if(changed)chart.setData(points,{reset});onStatus({data,point:points.at(-1)});
    }catch(e){if(e.name!=='AbortError'&&!disposed&&run===generation)onStatus({error:true});}
    finally{if(!disposed&&!document.hidden&&run===generation)timer=setTimeout(poll,1000);}
  }
  function visibility(){generation++;clearTimeout(timer);controller?.abort();if(!document.hidden&&!disposed)poll();}
  document.addEventListener('visibilitychange',visibility);poll();
  return {chart,setMode:chart.setMode,dispose(){disposed=true;clearTimeout(timer);controller?.abort();document.removeEventListener('visibilitychange',visibility);chart.dispose();}};
}
