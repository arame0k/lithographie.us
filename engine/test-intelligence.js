const {test}=require('node:test');const assert=require('node:assert/strict');
const {createEngine}=require('./intelligence-engine.js');
const data=require('./monthly-snapshot.json');const e=createEngine(data);
test('source totals and complete monthly coverage',()=>{
 assert.deepEqual(e.validate().issues,[]);
 assert.equal(e.validate().monthly_totals,60);
 assert.equal(e.validate().partner_observations,84);
 assert.equal(e.coverage().length,10);
});
test('exact sourced January 2025 primary aluminum',()=>{
 assert.equal(e.world('202501','7601','M').value_usd,1037631517);
 assert.equal(e.P.find(x=>x.period==='202501'&&x.hs==='7601'&&x.partner_code===124).value_usd,742120642);
});
test('quarter comparison derives from monthly world rows',()=>{
 const x=e.compare('7601','M');
 assert.equal(x.old.value,835909088+987116544+747757065);
 assert.equal(x.now.value,1037631517+1006009950+1365059826);
 assert.equal(x.delta,x.now.value-x.old.value);
});
test('missing weight is unknown, not zero',()=>{
 assert.equal(e.sumQuarter('2025','7601','M').weight_kg,null);
 assert.equal(e.sumQuarter('2025','7606','M').weight_kg,null);
 assert.equal(e.world('202503','7601','M').net_weight_kg,null);
});
test('partial partner coverage does not become a false zero',()=>{
 const p=e.partnerComparison('7601').find(x=>x.partner_code===554);
 assert.equal(p.old,null);assert.equal(p.comparable,false);assert.equal(p.delta,null);
});
test('two flows have distinct evidence and paired comparisons',()=>{
 assert.notEqual(e.sumQuarter('2025','7601','M').value,e.sumQuarter('2025','7601','X').value);
 assert.ok(e.basket('2025','M')>0);assert.ok(e.basket('2025','X')>0);
});
test('sampled partner duplicate identities are rejected',()=>{
 const altered=structuredClone(data);altered.top_partners.push({...altered.top_partners[0]});
 assert.equal(createEngine(altered).validate().ok,false);
});
test('selected partner sums may not exceed a reported world total',()=>{
 const altered=structuredClone(data);const first=altered.top_partners[0];
 first.value_usd=altered.world.find(w=>w.period===first.period&&w.hs===first.hs&&w.flow===first.flow).value_usd;
 assert.equal(createEngine(altered).validate().ok,false);
});
test('selected partner coverage is not mislabeled as a full census',()=>{
 const r=e.partnerCoverage('7601','2025');
 assert.equal(r.scope,'sampled_top_seven_per_month');
 assert.equal(r.months,3);assert.ok(r.observed_share>0 && r.observed_share<=1);
 assert.equal(r.complete_census,false);
});
