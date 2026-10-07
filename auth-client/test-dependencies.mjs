// Exercise compatibility across the patched wallet-URI and identifier boundaries.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {Worker} from 'node:worker_threads';
const require=createRequire(import.meta.url);
const uuid=await import('uuid'),qs=(await import('query-string')).default;
let checks=0;
function ok(test){assert(test);checks++;}
const namespace='6ba7b810-9dad-11d1-80b4-00c04fd430c8';
ok(uuid.validate(uuid.v4()));
ok(uuid.v5('rally',namespace)===uuid.v5('rally',namespace));
ok(require('uuid').validate(require('uuid').v4()));
for(const fn of [()=>uuid.v3('rally',namespace,new Uint8Array(8),4),
    ()=>uuid.v5('rally',namespace,new Uint8Array(8),4),()=>uuid.v6({},new Uint8Array(8),4)]){
  assert.throws(fn,RangeError);checks++;
}
ok(qs.parse('redirect=https%3A%2F%2Frally.example%2Fmcp&label=Rally%20wallet').redirect==='https://rally.example/mcp');
ok(qs.parse('label=hello%20world').label==='hello world');
const query={'relay-protocol':'irn',symKey:'ab'.repeat(32),expiryTimestamp:'1791399999'};
ok(qs.parse(qs.stringify(query)).symKey===query.symKey);
// These consumers use the same parser through their own dependency resolution.
const uri=`wc:${'12'.repeat(32)}@2?${qs.stringify(query)}`;
for(const consumer of ['@walletconnect/utils','@walletconnect/universal-provider','@walletconnect/ethereum-provider']){
  const local=createRequire(require.resolve(consumer));
  const parser=(await import(local.resolve('query-string'))).default;
  ok(parser.parse(uri.split('?')[1]).symKey===query.symKey);
}
const walletconnect=await import('@walletconnect/utils');
const parsed=walletconnect.parseUri(uri);
ok(parsed.version===2&&parsed.symKey===query.symKey&&parsed.relay.protocol==='irn');
// Run malformed decoding in a worker so a regression cannot hang the test host.
await new Promise((resolve,reject)=>{
  const worker=new Worker(`const {parentPort}=require('node:worker_threads');
    import(${JSON.stringify(require.resolve('decode-uri-component'))}).then(({default:decode})=>{
      const start=performance.now(); decode('%A'.repeat(50000));
      parentPort.postMessage(performance.now()-start);
    }).catch(e=>{throw e});`,{eval:true});
  const timeout=setTimeout(()=>{worker.terminate();reject(new Error('Malformed URI decoding exceeded 2 seconds'));},2000);
  worker.once('message',ms=>{clearTimeout(timeout);worker.terminate();ok(ms<1500);resolve();});
  worker.once('error',e=>{clearTimeout(timeout);reject(e);});
});
console.log(JSON.stringify({ok:true,checks,providerRequests:0,walletSignatures:0}));
