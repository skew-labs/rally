// OAuth lifecycle fixtures only; no provider or real identity credentials.
import assert from 'node:assert/strict';
import {authUI} from '../auth-ui.js';
globalThis.location={origin:'https://rallydot.com',pathname:'/',href:'https://rallydot.com/?view=account'};
const values=new Map();globalThis.sessionStorage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
for(const mode of ['delayed','changed','expired','cancelled']) {
  values.clear();let calls=0,completed=0;
  const module='export async function initialize(){};export function authenticated(){return false};export async function waitForAuthentication(){await globalThis.fixtureWait()};export async function signIn(){return {accessToken:"fixture-access",identityToken:"fixture-identity"}}';
  const S={boot:{me:null,auth:{privy:{enabled:true,bridgeURL:'data:text/javascript,'+encodeURIComponent(module)}}}};
  sessionStorage.setItem('rally:privy-intent',JSON.stringify({owner:null,link:false,path:'/',created:Date.now()-(mode==='expired'?600001:0)}));
  globalThis.fixtureWait=async()=>{await new Promise(r=>setTimeout(r,20));if(mode==='changed')S.boot.me={id:'other'};if(mode==='cancelled')throw new Error('Cancelled');};
  const ui=authUI({S,api:async(path,data)=>{assert.equal(path,'/api/auth/privy');assert.equal(data.link,false);calls++;},boot:async()=>{S.boot.me={id:'fixture'};},closeModal:()=>{},render:async()=>{},notify:()=>{},afterLogin:async()=>{completed++;}});
  assert.equal(await ui.resume(),mode==='delayed');
  assert.equal(calls,mode==='delayed'?1:0);assert.equal(completed,calls);
  assert.equal(sessionStorage.getItem('rally:privy-intent'),null);
  assert.equal(await ui.resume(),false);assert.equal(calls,mode==='delayed'?1:0);
}
console.log('OAuth resume waits for authentication and rejects changed, expired, cancelled and replayed intents. Fixtures only.');
