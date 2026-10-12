import assert from 'node:assert/strict';
import {swipeHistory} from '../swipe-history.js';
const host=()=>({dataset:{},isConnected:true,innerHTML:'',textContent:''});
const points=[{time:Math.floor(Date.now()/1000)-60,value:1},{time:Math.floor(Date.now()/1000),value:2}];
for(const [item,expected] of [
 [{asset:{id:'MON'}},{asset:'MON',kind:'spot'}],
 [{asset:{id:'perp:btc'},market:{id:1,venue:'Perpl'}},{asset:'1',kind:'perps'}],
 [{asset:{id:'perp:btc'},market:{id:'leverup:btc',venue:'LeverUp'}},{asset:'leverup:btc',kind:'perps'}],
 [{asset:{id:'0xcurve',nadfun:true}},{token:'0xcurve',interval:'60'}]
]){
 const el=host();let reads=0;
 const preview=swipeHistory(async path=>{reads++;const q=new URL(path,'https://rally.invalid').searchParams;for(const [k,v]of Object.entries(expected))assert.equal(q.get(k),v);return {asset:expected.asset,token:expected.token,points};});
 await preview.mount(el,item);assert.match(el.innerHTML,/<svg/);await preview.mount(host(),item);assert.equal(reads,1);preview.dispose();
}
const wrong=host();await swipeHistory(async()=>({asset:'another-token',points})).mount(wrong,{asset:{id:'MON'}});assert.equal(wrong.innerHTML,'');assert.equal(wrong.textContent,'Open chart for details');
const invalid=host();await swipeHistory(async()=>({asset:'MON',points:[{time:points[0].time,value:Infinity}]})).mount(invalid,{asset:{id:'MON'}});assert.equal(invalid.innerHTML,'');assert.equal(invalid.textContent,'Price history unavailable');
console.log('Swipe history: spot, venue identity, curve interval, cache, invalid data passed.');
