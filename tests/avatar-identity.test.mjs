import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {avatarIndex,avatarAsset,avatarCharacters,profileAvatarAsset} from '../avatar-identity.js';
test('web and Android identity vectors use UTF-16 and identical namespaces',()=>{
 for(const [id,namespace,expected] of [['guest','profile',5],['alice','profile',5],['studio','community',3],['a🐈','profile',3],['2a785c16f45743309f82f6c80a45ec35','profile',0]])assert.equal(avatarIndex(id,namespace),expected);
});
test('editorial accounts have distinct faces, independent of display names',()=>{
 const ids=['rally','ce835f7aadde4129bfe8d993385c21d2','1a4c47df1581408e913ca68056d07fe7','c0d47e94549f4e5c93c9e0eacce45c25'];
 assert.equal(new Set(ids.map(id=>avatarAsset(id))).size,4);
 for(const id of ids)assert.equal(profileAvatarAsset({id,name:'Before',handle:'before'}),profileAvatarAsset({id,name:'After',handle:'after'}));
});
test('web and native ship the exact same six images',async()=>{
 const seen=new Set();
 for(const suffix of avatarCharacters){
  const web=await fs.readFile(new URL('../assets/rally-character-'+suffix+'.webp',import.meta.url));
  const native=await fs.readFile(new URL('../android/app/src/main/res/drawable-nodpi/rally_character'+(suffix==='v1'?'':'_'+suffix.split('-')[0])+'.webp',import.meta.url));
  assert.deepEqual(web,native);assert(web.length<16000);seen.add(web.toString('base64'));
 }
 assert.equal(seen.size,6);
});
