const button=document.querySelector('.p-theme');
function updateTheme(){
 const dark=document.documentElement.dataset.theme==='dark';
 button?.setAttribute('aria-label',dark?'Switch to light mode':'Switch to dark mode');
 if(button)button.innerHTML=dark?'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5"/></svg>':'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M20.6 14A8.7 8.7 0 0 1 10 3.4 8.7 8.7 0 1 0 20.6 14Z"/></svg>';
 document.querySelector('meta[name="theme-color"]')?.setAttribute('content',dark?'#18151f':'#f6f5f9');
}
button?.addEventListener('click',()=>{window.RallyTheme?.set(document.documentElement.dataset.theme==='dark'?'light':'dark');updateTheme();});
window.addEventListener('rally-theme-change',updateTheme);
updateTheme();
