// Run on the authorized remote Rally host.
import {build} from 'esbuild';
import fs from 'node:fs/promises';
const output=process.argv[2]||'../assets/auth';
const result=await build({entryPoints:['privy-bridge.jsx'],bundle:true,format:'esm',splitting:true,minify:true,
  target:'es2022',define:{'process.env.NODE_ENV':'"production"'},outdir:output,
  entryNames:'privy-bridge',chunkNames:'chunk-[hash]',assetNames:'asset-[hash]',metafile:true});
await fs.writeFile('privy-build.json',JSON.stringify(result.metafile));
