// Display references only. A percentage is a price change, never realized PnL.
export function compactUSD(value) {
 const n=Number(value);if(value==null||!Number.isFinite(n)||n<0)return '—';
 const [scale,suffix]=n>=1e9?[1e9,'B']:n>=1e6?[1e6,'M']:n>=1e3?[1e3,'K']:[1,''];
 return '$'+(n/scale).toLocaleString('en-US',{maximumFractionDigits:2,minimumFractionDigits:0})+suffix;
}
export function tokenAge(t,category,now=Date.now()/1000) {
 const stamp=Number(category==='graduated'?t.graduatedAt:t.created);
 if(!stamp||stamp>now)return null;
 const seconds=Math.max(0,now-stamp),label=seconds<60?'now':seconds<3600?Math.floor(seconds/60)+'m':seconds<86400?Math.floor(seconds/3600)+'h':seconds<2592000?Math.floor(seconds/86400)+'d':seconds<31536000?Math.floor(seconds/2592000)+'mo':Math.floor(seconds/31536000)+'y';
 return {label,stamp,kind:category==='graduated'?'Graduated':'Launched'};
}
export function priceChange(t) {
 const n=Number(t.change);return t.change==null||!Number.isFinite(n)||t.stale?null:n;
}
