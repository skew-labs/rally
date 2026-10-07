// Run on the authorized remote Rally host.
import {build} from 'esbuild';
import fs from 'node:fs/promises';
import path from 'node:path';
const output=process.argv[2]||'../assets/auth';
const result=await build({entryPoints:['privy-bridge.jsx'],bundle:true,format:'esm',splitting:true,minify:true,
  target:'es2022',define:{'process.env.NODE_ENV':'"production"'},outdir:output,
  entryNames:'privy-bridge-[hash]',chunkNames:'chunk-[hash]',assetNames:'asset-[hash]',metafile:true});
const entry=Object.entries(result.metafile.outputs).find(([,value])=>value.entryPoint==='privy-bridge.jsx');
if(!entry)throw new Error('Auth entry bundle missing');
await fs.writeFile(path.join(output,'manifest.json'),JSON.stringify({entry:path.basename(entry[0])})+'\n');
// Keep existing callers on the patched bundle during the versioned-entry rollout.
await fs.writeFile(path.join(output,'privy-bridge.js'),`export * from './${path.basename(entry[0])}';\n`);
await fs.writeFile('privy-build.json',JSON.stringify(result.metafile));
