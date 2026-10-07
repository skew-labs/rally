/* Applied before styles to avoid flashing the other theme. No account data. */
(()=>{
 const system=matchMedia('(prefers-color-scheme: dark)');
 let saved;try{saved=localStorage.getItem('rally-theme');}catch{}
 const apply=value=>{document.documentElement.dataset.theme=value;document.querySelector('meta[name="theme-color"]')?.setAttribute('content',value==='dark'?'#111114':'#f7f7f8');};
 apply(['light','dark'].includes(saved)?saved:system.matches?'dark':'light');
 window.RallyTheme={set(value){if(!['light','dark'].includes(value))return;try{localStorage.setItem('rally-theme',value);}catch{}saved=value;apply(value);},get(){return document.documentElement.dataset.theme;}};
 system.addEventListener('change',e=>{if(!saved){apply(e.matches?'dark':'light');window.dispatchEvent(new Event('rally-theme-change'));}});
})();
