// Connect observed closing prices. Do not insert trades or prices in quiet gaps.
export function compactPoints(points,budget=320){
  if(points.length<=budget)return points;
  const buckets=new Map(),first=points[0],last=points.at(-1),span=Math.max(1,last.time-first.time),count=Math.floor((budget-2)/2);
  for(let i=1;i<points.length-1;i++){
    const p=points[i],key=Math.min(count-1,Math.floor((p.time-first.time)*count/span)),[low,high]=buckets.get(key)||[p,p];
    buckets.set(key,[p.value<low.value?p:low,p.value>high.value?p:high]);
  }
  const keep=new Map([[first.time,first],[last.time,last]]);
  for(const pair of buckets.values())for(const point of pair)keep.set(point.time,point);
  return [...keep.values()].sort((a,b)=>a.time-b.time);
}
export const closingPrices = candles => compactPoints(candles.map(({time,close})=>({time,value:close})));
export function fitPriceLine(chart,points){
  const span=points.length-1;
  // Logical ranges include half a bar at each edge. Trim that candle padding
  // for line-only history so three sparse observations still use the plot.
  chart.timeScale().setVisibleLogicalRange(span>1?{from:.4,to:span-.4}:span===1?{from:0,to:1}:{from:-1,to:1});
}
export const priceLineOptions = (precision=6) => ({
  color:'#9178ff',lineWidth:2,lineType:0,
  pointMarkersVisible:false,crosshairMarkerVisible:true,crosshairMarkerRadius:4,
  priceLineVisible:false,lastValueVisible:true,
  priceFormat:{type:'price',precision,minMove:10**-precision}
});
