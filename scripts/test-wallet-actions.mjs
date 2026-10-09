// Fixture-only submission boundary: no browser wallet, RPC, or network access.
import assert from 'node:assert/strict';
import {financeUI} from '../finance.js';
const values=new Map();
globalThis.document={hidden:false,addEventListener:()=>{}};
globalThis.localStorage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
const wallet='0x'+'1'.repeat(40),recipient='0x'+'2'.repeat(40);
for(const mutated of [false,true]){
 values.clear();let requests=0,recorded=0,error;
 const S={boot:{me:{id:'fixture'},wallet},provider:{request:async()=>{requests++;return '0x'+'a'.repeat(64);}}};
 const ui=financeUI({S,spotPending:()=>[],walletReady:async()=>true,api:async path=>{
  if(path.endsWith('/prepare'))return {transaction:{from:wallet,to:mutated?wallet:recipient,value:'0x1',data:'0x',chainId:143}};
  if(path.endsWith('/record')){recorded++;return {state:'submitted'};}
  throw new Error('Unexpected fixture request');
 }});
 await ui.submitInline({id:'fixture-plan',expires:Date.now()/1000+90},{kind:'execution',current:()=>true,done:()=>{},error:message=>{error=message;},validateTransaction:tx=>assert.equal(tx.to,recipient,'Prepared recipient changed')});
 assert.equal(requests,mutated?0:1);assert.equal(recorded,mutated?0:1);
 assert.equal(S.financialBusy,false);
 assert.equal(Boolean(error),mutated);
}
console.log('Prepared-send recipient check passed; fixture signer only.');
