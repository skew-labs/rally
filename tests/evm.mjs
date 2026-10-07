// Disposable loopback EVM. No fork URL, provider credentials or persisted wallet.
import {spawn} from 'node:child_process';
import net from 'node:net';
import {fileURLToPath} from 'node:url';

export async function evm() {
  const reservation=net.createServer();
  await new Promise((resolve,reject)=>{reservation.once('error',reject);reservation.listen(0,'127.0.0.1',resolve);});
  const port=reservation.address().port;
  await new Promise(resolve=>reservation.close(resolve));
  const child=spawn(process.execPath,[fileURLToPath(new URL('../node_modules/@foundry-rs/anvil/bin.mjs',import.meta.url)),
    '--host','127.0.0.1','--port',String(port),'--chain-id','143','--hardfork','shanghai',
    '--accounts','4','--silent'],{stdio:['ignore','ignore','pipe']});
  let failure='',stopped=false;
  child.stderr.on('data',chunk=>{failure=(failure+chunk).slice(-2000);});
  child.once('error',error=>{failure=error.message;});
  const stop=()=>{if(!stopped){stopped=true;child.kill('SIGTERM');}};
  process.once('exit',stop);
  const network={
    async request({method,params=[]}) {
      const response=await fetch(`http://127.0.0.1:${port}`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({jsonrpc:'2.0',id:1,method,params}),signal:AbortSignal.timeout(5000)});
      const value=await response.json();
      if(value.error)throw Object.assign(new Error(value.error.message),value.error);
      return value.result;
    },
    async disconnect(){stop();if(child.exitCode===null)await new Promise(resolve=>child.once('exit',resolve));process.removeListener('exit',stop);}
  };
  for(let attempt=0;attempt<100;attempt++) {
    if(child.exitCode!==null||failure)throw new Error('Isolated EVM failed: '+failure);
    try{if(await network.request({method:'eth_chainId'})==='0x8f')return network;}catch{}
    await new Promise(resolve=>setTimeout(resolve,50));
  }
  stop();throw new Error('Isolated EVM startup timed out');
}
