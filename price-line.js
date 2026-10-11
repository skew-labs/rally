// Connect observed closing prices. Do not insert trades or prices in quiet gaps.
export const closingPrices = candles => candles.map(({time,close})=>({time,value:close}));
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
