// Display preferences only; never store observations or trading state here.
export function chartSettings(scope='market'){
  let saved;try{saved=JSON.parse(localStorage.getItem('rally:chart-view:'+scope)||'{}');}catch{}
  return {mode:['history','line','candles','ticks','provider'].includes(saved?.mode)?saved.mode:'history',period:['1D','7D','1M'].includes(saved?.period)?saved.period:'1D',interval:['1','15','60','240'].includes(saved?.interval)?saved.interval:'60',window:[30,60,120].includes(saved?.window)?saved.window:60};
}
export function saveChartSettings(scope,settings){try{localStorage.setItem('rally:chart-view:'+scope,JSON.stringify(settings));}catch{}}
