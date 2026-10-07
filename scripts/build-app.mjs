// Content-addressed browser bundles. No environment or credential injection.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url),{build,transform}=require('esbuild');
const root=path.resolve(process.argv[2]||'.'),digest=data=>createHash('sha256').update(data).digest('hex');
const index=await fs.readFile(path.join(root,'index.html'),'utf8');
const cssFiles=[...index.matchAll(/<link rel="stylesheet" href="(?:\.\/|\/)([^"?]+)(?:\?[^"]*)?"/g)].map(x=>x[1]);
const js=await build({absWorkingDir:root,entryPoints:['live-app.js'],bundle:true,format:'esm',minify:true,target:'es2022',write:false,metafile:true,legalComments:'inline',external:['https://*','http://*','/assets/auth/*']});
const styles=[];
for(const name of cssFiles){
 const data=await fs.readFile(path.join(root,name),'utf8');
 styles.push(data.replace(/url\((['"]?)([^)'"\s]+)\1\)/g,(all,quote,url)=>/^(?:data:|https?:|\/|#)/.test(url)?all:`url(${quote}/${path.posix.normalize(path.posix.join(path.posix.dirname(name),url))}${quote})`));
}
const css=await transform(styles.join('\n'),{loader:'css',minify:true,target:'es2022',legalComments:'inline'});
const outputs={},sources={};await fs.mkdir(path.join(root,'assets'),{recursive:true});
const save=async(kind,data)=>{const hash=digest(data),name=`assets/rally-app-${hash.slice(0,20)}.${kind}`;await fs.writeFile(path.join(root,name),data);outputs[name]=hash;return name;};
const jsName=await save('js',js.outputFiles[0].contents),cssName=await save('css',css.code);
for(const name of new Set(['index.html',...Object.keys(js.metafile.inputs),...cssFiles]))sources[name]=digest(await fs.readFile(path.join(root,name)));
const manifest={version:1,js:jsName,css:cssName,sources,outputs};
await fs.writeFile(path.join(root,'app-bundle.json.tmp'),JSON.stringify(manifest,null,2)+'\n');await fs.rename(path.join(root,'app-bundle.json.tmp'),path.join(root,'app-bundle.json'));
console.log(JSON.stringify({js:jsName,css:cssName,jsBytes:js.outputFiles[0].contents.length,cssBytes:Buffer.byteLength(css.code),sourceFiles:Object.keys(sources).length}));
