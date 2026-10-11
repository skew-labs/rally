// Presentation only. These lanes do not change strategy execution or performance.
const first=['rally-ref-098','rally-ref-099','rally-ref-080','rally-ref-100','rally-ref-074'];
export const strategyLane=a=>['nad','kuru','nansen'].includes(a.sourceId)?'memes':a.category==='DeFi'?'yield':['Trader playbooks','Trend signals','Volume signals'].includes(a.category)?'momentum':'all';
export const strategyTag=a=>({memes:'Memes',yield:'Yield',momentum:'Momentum'}[strategyLane(a)]||({'Institutional':'Macro','Feed ranking':'Feeds','Token research':'Onchain'}[a.category]||a.category));
export function discoveryOrder(items,lane='all'){
 return items.filter(a=>lane==='all'||lane==='year'&&a.performance1Y||strategyLane(a)===lane).sort((a,b)=>{
  const pa=first.indexOf(a.id),pb=first.indexOf(b.id);
  return (pa<0?99:pa)-(pb<0?99:pb)||(['memes','momentum','yield','all'].indexOf(strategyLane(a))-['memes','momentum','yield','all'].indexOf(strategyLane(b)));
 });
}
export const strategyMarket=a=>a.sourceId==='perpl'?{tab:'perps',label:'Open perps'}:a.sourceId==='kuru'?{tab:'spot',label:'Open spot'}:['nad','nansen'].includes(a.sourceId)?{tab:'memes',label:'See tokens'}:null;
