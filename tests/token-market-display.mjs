import assert from 'node:assert/strict';
import {compactUSD,tokenAge,priceChange} from '../token-market-display.js';
assert.equal(compactUSD(9920000),'$9.92M');assert.equal(compactUSD(76700),'$76.7K');assert.equal(compactUSD(null),'—');assert.equal(compactUSD(0),'$0');
assert.equal(tokenAge({created:1000,graduatedAt:2000},'graduated',2060).label,'1m');assert.equal(tokenAge({created:1000},'graduated',2060),null);
assert.equal(tokenAge({created:3000},'new',2060),null);assert.equal(tokenAge({created:1000},'new',2200).label,'20m');
assert.equal(priceChange({change:0}),0);assert.equal(priceChange({change:null}),null);assert.equal(priceChange({change:50,stale:true}),null);
console.log('Token display: compact currency, event age, missing and stale references passed.');
