import assert from 'node:assert/strict';
import {swipeHistory} from '../swipe-history.js';
const host=()=>({dataset:{},isConnected:true,innerHTML:'',textContent:''});
const points=[{time:Math.floor(Date.now()/1000)-60,value:1},{time:Math.floor(Date.now()/1000),value:2}];
for(const [item,expected] of [
 [{asset:{id:'MON'}},{asset:'MON',kind:'spot'}],
 [{asset:{id:'perp:btc'},market:{id:1,venue:'Perpl'}},{asset:'1',kind:'perps'}],
 [{asset:{id:'perp:btc'},market:{id:'leverup:btc',venue:'LeverUp'}},{asset:'leverup:btc',kind:'perps'}],
 [{asset:{id:'0xcurve',nadfun:true}},{token:'0xcurve',interval:'60',preview:'1'}]
]){
 const el=host();let reads=0;
 const preview=swipeHistory(async path=>{reads++;const q=new URL(path,'https://rally.invalid').searchParams;for(const [k,v]of Object.entries(expected))assert.equal(q.get(k),v);return {asset:expected.asset,token:expected.token,points};});
 await preview.mount(el,item);assert.match(el.innerHTML,/<svg/);await preview.mount(host(),item);assert.equal(reads,1);preview.dispose();
}
const wrong=host();await swipeHistory(async()=>({asset:'another-token',points})).mount(wrong,{asset:{id:'MON'}});assert.equal(wrong.innerHTML,'');assert.equal(wrong.textContent,'Open chart for details');
const invalid=host();await swipeHistory(async()=>({asset:'MON',points:[{time:points[0].time,value:Infinity}]})).mount(invalid,{asset:{id:'MON'}});assert.equal(invalid.innerHTML,'');assert.equal(invalid.textContent,'No recent price history');
console.log('Swipe history: spot, venue identity, curve interval, cache, invalid data passed.');

// The visible card shares a prefetched request, and departing requests cannot paint.
let release,reads=0;
const shared=swipeHistory(async()=>{reads++;return await new Promise(r=>release=r)});
const item={asset:{id:'MON'}},el=host();
const warm=shared.prefetch(item),visible=shared.mount(el,item);assert.equal(reads,1);
release({asset:'MON',points});await Promise.all([warm,visible]);assert.match(el.innerHTML,/<svg/);
let signals=[];
const bounded=swipeHistory((path,_,options)=>new Promise((resolve,reject)=>{signals.push(options.signal);options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')));}));
const hosts=[host(),host(),host()];
const pending=hosts.map((h,i)=>bounded.mount(h,{asset:{id:String(i)}}));assert.equal(signals.length,3);assert.equal(signals[0].aborted,true);
bounded.dispose();await Promise.all(pending);assert(signals.every(s=>s.aborted));assert(hosts.every(h=>!h.dataset.loaded));
let tries=0;const retry=swipeHistory(async()=>++tries===1?{asset:'MON',points:[]}:{asset:'MON',points});const again=host();await retry.mount(again,item);await retry.mount(again,item);assert.equal(tries,2);assert.match(again.innerHTML,/<svg/);
console.log('Swipe history: prefetch deduplication, cancellation, bounded reads and retry passed.');
