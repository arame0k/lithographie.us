/* Research measures with explicit observation boundaries. */
(function(root){
'use strict';
function makeAnalysis(engine){
 const months=y=>[1,2,3].map(m=>`${y}0${m}`);
 function partnerMix(hs,year){
  const world=engine.sumQuarter(year,hs,'M');
  const observed=engine.P.filter(r=>r.hs===hs&&r.flow==='M'&&months(year).includes(r.period));
  const monthSums=months(year).map(period=>observed.filter(x=>x.period===period).reduce((a,x)=>a+x.value_usd,0));
  const partners=new Map();
  for(const row of observed){
   const k=String(row.partner_code), p=partners.get(k)||{code:k,value_usd:0,months:[]};
   if(p.months.includes(row.period))throw Error('Duplicate partner-period: '+k+' '+row.period);
   p.months.push(row.period);p.value_usd+=row.value_usd;partners.set(k,p);
  }
  const items=[...partners.values()].map(p=>({...p,months:p.months.sort(),complete:p.months.length===3,share_of_world:p.value_usd/world.value})).sort((a,b)=>b.value_usd-a.value_usd);
  const captured=monthSums.reduce((a,b)=>a+b,0);
  if(world.value==null) return {status:'unavailable',reason:'Incomplete world observations',items:[]};
  if(monthSums.some((n,i)=>n>engine.world(months(year)[i],hs,'M').value_usd))throw Error('Observed subset exceeds world total');
  return {status:'observed_subset',hs,year,flow:'M',world_usd:world.value,observed_usd:captured,
   unrepresented_usd:world.value-captured,observed_share:captured/world.value,
   items,months:months(year),source_scope:'top seven selected import partners per month',
   limitation:'Unrepresented value has unknown partner composition. Reported shares are lower bounds on quarter partner shares; missing months are not zero.'};
 }
 function compareMix(hs){
  const old=partnerMix(hs,'2024'),now=partnerMix(hs,'2025');
  if(old.status==='unavailable'||now.status==='unavailable')return {status:'unavailable',reason:'World quarter incomplete'};
  const keys=new Set([...old.items,...now.items].map(p=>p.code));
  const entries=[...keys].map(code=>{
   const a=old.items.find(x=>x.code===code),b=now.items.find(x=>x.code===code);
   const comparable=!!a?.complete&&!!b?.complete;
   return {code,old_usd:a?.value_usd??null,now_usd:b?.value_usd??null,
    old_months:a?.months.length||0,now_months:b?.months.length||0,
    lower_bound_old:a?.share_of_world??null,lower_bound_now:b?.share_of_world??null,
    change_usd:comparable?b.value_usd-a.value_usd:null,
    change_pct:comparable&&a.value_usd>0?100*(b.value_usd-a.value_usd)/a.value_usd:null,
    comparable};
  });
  return {status:'observed_subset',old,now,entries,limitation:'Coverage varies by month. The observed subset is not a complete partner ranking.'};
 }
 return {partnerMix,compareMix};
}
root.LithoAnalysis={makeAnalysis};
if(typeof module==='object'&&module.exports)module.exports={makeAnalysis};
})(typeof window!=='undefined'?window:globalThis);
