import assert from 'node:assert/strict';
import {artworkSources,artworkTone} from '../token-art.js';
const art={'0xabc':'/exact.png'},resolve=x=>x.startsWith('javascript:')?'#':x;
assert.deepEqual(artworkSources({id:'0xAbC',logoThumbURI:'/thumb.png',logoURI:'/original.png',logoCandidates:['/exact.png','/original.png']},art,resolve),['/thumb.png','/exact.png','/original.png']);
assert.deepEqual(artworkSources({id:'0xdifferent',symbol:'BTC',logoURI:'javascript:bad'},art,resolve),[]);
assert.deepEqual(artworkSources({id:'a',logoThumbURI:'',logoURI:'/original.png'},art),['/original.png']);
assert.equal(artworkTone('0xabc'),artworkTone('0xabc'));assert(artworkTone('0xabc')>=0&&artworkTone('0xabc')<6);
console.log('Artwork sources: exact identity, bounded fallback, unsafe URL rejection');
