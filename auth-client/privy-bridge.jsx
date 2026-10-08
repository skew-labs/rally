import React, {useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {PrivyProvider, usePrivy, useLogin, useWallets, useCreateWallet, useConnectWallet, getIdentityToken} from '@privy-io/react-auth';
import {defineChain} from 'viem';

const monad = defineChain({id:143, name:'Monad', nativeCurrency:{name:'MON',symbol:'MON',decimals:18},
  rpcUrls:{default:{http:['https://rpc.monad.xyz']}}, blockExplorers:{default:{name:'MonadVision',url:'https://monadvision.com'}}});
let pending, walletPending, controller, ready, root;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function Bridge({onReady}) {
  const privy = usePrivy();
  const connected = useWallets();
  const {createWallet} = useCreateWallet();
  const finish = async () => {
    const request = pending;
    if (!request) return;
    try {
      const accessToken = await privy.getAccessToken();
      const identityToken = await getIdentityToken();
      if (!accessToken || !identityToken) throw new Error('Could not verify login. Enable identity tokens for this Privy app.');
      if (pending !== request) return;
      pending = null; request.resolve({accessToken,identityToken});
    } catch(error) {if (pending === request) {pending=null;request.reject(error);}}
  };
  const {login} = useLogin({onComplete:finish,onError:() => {
    if(pending){const request=pending;pending=null;request.reject(new Error('Login cancelled.'));}
  }});
  const {connectWallet}=useConnectWallet({
    onSuccess:({wallet})=>{
      if(!walletPending)return;
      const request=walletPending;walletPending=null;request.resolve(wallet.address);
    },
    onError:()=>{if(walletPending){const request=walletPending;walletPending=null;request.reject(new Error('Wallet connection cancelled.'));}}
  });
  useEffect(() => {
    controller = {privy,connected,createWallet,login,finish,connectWallet};
    if(privy.ready) onReady();
  });
  return null;
}

export async function initialize(config) {
  if(!ready) ready=new Promise(resolve => {
    const host=document.createElement('div');host.id='rally-privy-root';document.body.append(host);
    root=createRoot(host);
    root.render(<PrivyProvider appId={config.appId} {...(config.clientId?{clientId:config.clientId}:{})}
      config={{loginMethods:config.loginMethods,appearance:{theme:document.documentElement.dataset.theme==='dark'?'dark':'light',accentColor:'#765af2',logo:location.origin+'/assets/favicon.svg',showWalletLoginFirst:false,walletChainType:'ethereum-only',walletList:['metamask','coinbase_wallet','rainbow','detected_ethereum_wallets','wallet_connect']},
        defaultChain:monad,supportedChains:[monad],externalWallets:{coinbaseWallet:{config:{preference:{options:'eoaOnly'}}}},embeddedWallets:{ethereum:{createOnLogin:'off'}}}}>
      <Bridge onReady={resolve}/>
    </PrivyProvider>);
  });
  await Promise.race([ready,sleep(20000).then(()=>{throw new Error('Login took too long to load. Try again.');})]);
}

export function signIn(method=null) {
  if(pending) return Promise.reject(new Error('A login is already in progress.'));
  return new Promise((resolve,reject) => {
    pending={resolve,reject};
    if(controller.privy.authenticated) controller.finish(); else controller.login(method?{loginMethods:[method],walletChainType:'ethereum-only'}:undefined);
  });
}

export function cancel() {
  if(pending){const request=pending;pending=null;request.reject(new Error('Login cancelled.'));}
  if(walletPending){const request=walletPending;walletPending=null;request.reject(new Error('Wallet connection cancelled.'));}
}

export function authenticated() {return Boolean(controller?.privy.authenticated);}

export async function walletProvider(address=null, create=false) {
  if(!controller)throw new Error('Wallet connection is still loading.');
  if(create&&!controller.privy.authenticated)throw new Error('Sign in to create your wallet.');
  if(create && !controller.connected.wallets.some(w=>w.walletClientType==='privy')) await controller.createWallet();
  for(let attempt=0;attempt<40;attempt++) {
    const wallets=controller.connected.wallets;
    const wallet=address?wallets.find(w=>w.address.toLowerCase()===address.toLowerCase()):wallets.find(w=>w.walletClientType==='privy')||wallets[0];
    if(wallet)return wallet.getEthereumProvider();
    if(!create && controller.connected.ready) return null;
    await sleep(100);
  }
  if(!create)return null;
  throw new Error('Your wallet is still connecting. Try again.');
}

export async function connectExternal(id=null) {
  if(walletPending)throw new Error('Complete the open wallet request.');
  const address=await new Promise((resolve,reject)=>{
    walletPending={resolve,reject};
    controller.connectWallet({walletChainType:'ethereum-only',description:'Connect to Rally',...(id?{walletList:[id],preSelectedWalletId:id}:{})});
  });
  // The hook callback may precede useWallets' next render.
  for(let attempt=0;attempt<50;attempt++){
    const provider=await walletProvider(address);
    if(provider)return provider;
    await sleep(100);
  }
  throw new Error('Your wallet is still connecting. Try again.');
}

export async function logout() {cancel();if(controller?.privy.ready)await controller.privy.logout();}
