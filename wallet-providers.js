// EIP-6963 keeps the chosen extension separate from window.ethereum overrides.
const announced=new Map();
if(typeof window!=='undefined'){
  window.addEventListener('eip6963:announceProvider',event=>{
    const {info,provider}=event.detail||{};
    if(!info||typeof info.uuid!=='string'||typeof provider?.request!=='function'||announced.size>=32)return;
    const image=typeof info.icon==='string'&&info.icon.length<65536&&/^data:image\/(?:png|jpeg|webp|svg\+xml)[;,]/.test(info.icon)?info.icon:null;
    announced.set(info.uuid,{provider,name:String(info.name||'Wallet').slice(0,60),rdns:String(info.rdns||'').slice(0,150),image});
  });
  window.dispatchEvent(new Event('eip6963:requestProvider'));
}
export const walletBrands=[
  {id:'metamask',name:'MetaMask',image:'/assets/agent-metamask.svg'},
  {id:'coinbase_wallet',name:'Coinbase Wallet',image:'/assets/wallet-coinbase.svg'},
  {id:'rainbow',name:'Rainbow',image:'/assets/wallet-rainbow.svg'},
];
function identity(item){
  const p=item.provider,label=(item.rdns+' '+item.name).toLowerCase();
  if(/rabby/.test(label)||p.isRabby)return 'rabby';
  if(/coinbase/.test(label)||p.isCoinbaseWallet)return 'coinbase_wallet';
  if(/rainbow/.test(label)||p.isRainbow)return 'rainbow';
  if(/phantom/.test(label)||p.isPhantom)return 'phantom';
  if(/metamask/.test(label)||p.isMetaMask)return 'metamask';
  return 'injected';
}
export function detectedWallets(){
  const result=[...announced.values()];
  for(const provider of (window.ethereum?.providers||[window.ethereum].filter(Boolean))){
    if(typeof provider?.request==='function'&&!result.some(item=>item.provider===provider))result.push({provider,name:'Browser wallet',rdns:''});
  }
  return result.map(item=>({...item,id:identity(item)}));
}
export function detectedProvider(id){return detectedWallets().find(item=>item.id===id)?.provider||null;}
