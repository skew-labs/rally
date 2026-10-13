// Contract identities stay authoritative; a matching ticker is not a logo match.
export function artworkSources(token,registry,resolve=x=>x){
 const identity=String(token?.id||token?.address||'').toLowerCase();
 return [...new Set([token?.logoThumbURI,registry[identity],...(Array.isArray(token?.logoCandidates)?token.logoCandidates:[]),token?.logoURI].filter(x=>typeof x==='string'&&x.trim()).map(resolve).filter(x=>x&&x!=='#'))].slice(0,4);
}
export function artworkTone(identity){let hash=0;for(const c of String(identity))hash=(hash*31+c.charCodeAt(0))>>>0;return hash%6;}
