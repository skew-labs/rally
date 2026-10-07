import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import solc from 'solc';

const root=fileURLToPath(new URL('..',import.meta.url));
const settings={optimizer:{enabled:true,runs:100},viaIR:true,evmVersion:'shanghai',outputSelection:{'*':{'*':['abi','evm.bytecode.object','evm.deployedBytecode.object','evm.deployedBytecode.immutableReferences']}}};
const hash=data=>createHash('sha256').update(data).digest('hex');
function compile(names){
 const sources=Object.fromEntries(names.map(name=>[name,{content:fs.readFileSync(path.join(root,'contracts',name),'utf8')}]));
 const out=JSON.parse(solc.compile(JSON.stringify({language:'Solidity',sources,settings}),{import:name=>{
  if(!name.startsWith('@openzeppelin/contracts/')||name.includes('..'))return {error:'Unsupported dependency'};
  return {contents:fs.readFileSync(path.join(root,'node_modules',name),'utf8')};
 }}));
 for(const item of out.errors||[])if(item.severity==='error')throw new Error(item.formattedMessage);
 const contracts={};
 for(const [file,items] of Object.entries(out.contracts||{}))if(names.includes(file))for(const [name,c] of Object.entries(items))if(c.evm.bytecode.object){
  if(c.evm.deployedBytecode.object.length/2>24576)throw new Error('Runtime exceeds EIP-170: '+name);
  contracts[name]={abi:c.abi,bytecode:'0x'+c.evm.bytecode.object,runtime:'0x'+c.evm.deployedBytecode.object,immutables:c.evm.deployedBytecode.immutableReferences};
 }
 return {compiler:solc.version(),settings,sourceHashes:Object.fromEntries(Object.entries(sources).map(([name,s])=>[name,hash(s.content)])),contracts};
}
const community=compile(['RallyCommunity.sol','Mocks.sol']);
const revenue=compile(['RallyCommunity.sol','RallyNadRevenue.sol','Mocks.sol','NadMocks.sol']);
fs.mkdirSync(path.join(root,'build'),{recursive:true});
const save=(name,value)=>fs.writeFileSync(path.join(root,name),JSON.stringify(value,null,2)+'\n');
save('build/contracts.json',community);save('build/revenue-contracts.json',revenue);
save('community-contracts.json',{compiler:community.compiler,sourceHashes:community.sourceHashes,contracts:Object.fromEntries(Object.entries(community.contracts).filter(([name])=>name.startsWith('RallyCommunity')))});
save('community-deployment.json',{sourceHash:community.sourceHashes['RallyCommunity.sol'],bytecode:community.contracts.RallyCommunityFactory.bytecode});
save('nad-revenue-contract.json',{...revenue,contracts:{RallyNadRevenueVault:revenue.contracts.RallyNadRevenueVault}});
console.log(JSON.stringify({compiler:solc.version(),communityContracts:3,revenueContracts:1,networkCalls:0}));
