// Observe the real renderer in read-only browser fixtures, without replacing it.
import fs from 'node:fs/promises';
const engine=await fs.readFile(new URL('../assets/lightweight-charts-5.2.1.mjs',import.meta.url),'utf8');
export async function observeChartRenderer(route){
 const path=new URL(route.request().url()).pathname;
 if(path==='/assets/chart-engine-observed.mjs'){await route.fulfill({contentType:'text/javascript',body:engine});return true;}
 if(path!=='/assets/lightweight-charts-5.2.1.mjs')return false;
 await route.fulfill({contentType:'text/javascript',body:`
 export * from '/assets/chart-engine-observed.mjs';
 import * as L from '/assets/chart-engine-observed.mjs';
 export function createChart(...args){
  const chart=L.createChart(...args),add=chart.addSeries.bind(chart);
  chart.addSeries=(type,...rest)=>{const entry={type:type===L.LineSeries?'line':type===L.CandlestickSeries?'candles':'other',points:[]};
   (window.chartSeriesObserved||=[]).push(entry);const series=add(type,...rest),set=series.setData.bind(series);
   series.setData=data=>{entry.points=structuredClone(data);return set(data);};
   window.chartCoverage=()=>{const ts=chart.timeScale(),points=entry.points;if(points.length<2)return 1;return (ts.timeToCoordinate(points.at(-1).time)-ts.timeToCoordinate(points[0].time))/ts.width();};return series;
  };return chart;
 }
 `});return true;
}
