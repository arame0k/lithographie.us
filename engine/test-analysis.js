const {test}=require('node:test');const assert=require('node:assert/strict');
const {createEngine}=require('./intelligence-engine.js');
const {makeAnalysis}=require('./analysis_contracts.js');
const corpus=require('./monthly-snapshot.json');
const a=makeAnalysis(createEngine(corpus));
test('month-preserving lower bound and exact remainder',()=>{
 const m=a.partnerMix('7601','2025');
 assert.equal(m.status,'observed_subset');
 assert.equal(m.observed_usd+m.unrepresented_usd,m.world_usd);
 assert.ok(m.unrepresented_usd>=0&&m.observed_share<1);
 assert.equal(m.items.reduce((s,x)=>s+x.value_usd,0),m.observed_usd);
 assert.equal(m.items.find(x=>x.code==='124').months.length,3);
});
test('sampled partner is not promoted to complete country ranking',()=>{
 const m=a.compareMix('7601');assert.equal(m.status,'observed_subset');
 const absent=m.entries.find(x=>!x.comparable);
 assert.ok(absent);assert.equal(absent.change_usd,null);
 assert.ok(m.limitation.includes('not a complete'));
});
test('incomplete world quarter refuses comparison',()=>{
 const partial=structuredClone(corpus);partial.world=partial.world.filter(x=>!(x.hs==='7601'&&x.period==='202501'&&x.flow==='M'));
 const m=makeAnalysis(createEngine(partial)).compareMix('7601');
 assert.equal(m.status,'unavailable');
});
test('sample exceeding monthly world is rejected',()=>{
 const edited=structuredClone(corpus);edited.top_partners.find(x=>x.hs==='7601').value_usd=999999999999;
 assert.throws(()=>makeAnalysis(createEngine(edited)).partnerMix('7601','2024'),/exceeds world/);
});
