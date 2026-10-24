/* Lithographie intelligence engine. Input: sourced normalized monthly observations. */
(function(root){
'use strict';
function createEngine(data){
 const meta=data.metadata;
 const W=data.world, P=data.top_partners;
 const worldIndex=new Map(W.map(r=>[`${r.period}|${r.hs}|${r.flow}`,r]));
 const hs=Object.keys(meta.hs_codes);
 const periods=['202401','202402','202403','202501','202502','202503'];
 const world=(period,code,flow)=>worldIndex.get(`${period}|${code}|${flow}`)||null;
 const sumQuarter=(year,code,flow)=>{
  const a=[1,2,3].map(m=>world(`${year}${String(m).padStart(2,'0')}`,code,flow));
  const valid=a.filter(Boolean),weights=valid.map(x=>x.net_weight_kg);
  return {year,hs:code,flow,months:valid.length,value:valid.length===3?valid.reduce((s,x)=>s+x.value_usd,0):null,
   weight_kg:valid.length===3&&weights.every(x=>x!=null)?weights.reduce((s,w)=>s+w,0):null,
   qty_estimated:valid.some(x=>x.qty_estimated===true),sources:valid.map(x=>x.url)};
 };
 const compare=(code,flow)=>{
  const old=sumQuarter('2024',code,flow),now=sumQuarter('2025',code,flow);
  const delta=old.value!==null&&now.value!==null?now.value-old.value:null;
  const pct=delta!==null&&old.value?100*delta/old.value:null;
  return {hs:code,flow,old,now,delta,pct};
 };
 const basket=(year,flow)=>{
  const parts=hs.map(h=>sumQuarter(year,h,flow));
  return parts.every(x=>x.value!==null)?parts.reduce((s,x)=>s+x.value,0):null;
 };
 const changes=(flow)=>hs.map(h=>compare(h,flow)).sort((a,b)=>Math.abs(b.pct||0)-Math.abs(a.pct||0));
 const monthly=(code,flow)=>periods.map(p=>world(p,code,flow));
 const partners=(code,year)=>{
  const grouped=new Map();
  for(const r of P.filter(r=>r.hs===code && r.period.startsWith(year))){
   const key=r.partner_code;
   if(!grouped.has(key))grouped.set(key,{partner_code:key, value:0,months:new Set(),entries:[]});
   const g=grouped.get(key);g.value+=r.value_usd;g.months.add(r.period);g.entries.push(r);
  }
  return [...grouped.values()].map(g=>({...g,months:[...g.months].sort(),complete:g.months.size===3})).sort((a,b)=>b.value-a.value);
 };
 const partnerComparison=(code)=>{
  const p24=new Map(partners(code,'2024').map(p=>[p.partner_code,p]));
  const p25=new Map(partners(code,'2025').map(p=>[p.partner_code,p]));
  return [...new Set([...p24.keys(),...p25.keys()])].map(k=>{
   const a=p24.get(k),b=p25.get(k),comp=Boolean(a?.complete&&b?.complete);
   return {partner_code:k,old:a?.value??null,now:b?.value??null,old_months:a?.months.length||0,now_months:b?.months.length||0,
    comparable:comp,delta:comp?b.value-a.value:null,pct:comp&&a.value?100*(b.value-a.value)/a.value:null,
    known_partial:!comp};
  }).sort((a,b)=>(b.now||0)-(a.now||0));
 };
 const partnerCoverage=(code,year)=>{
  const months=[1,2,3].map(m=>`${year}${String(m).padStart(2,'0')}`);
  const obs=P.filter(p=>p.hs===code&&p.flow==='M'&&months.includes(p.period));
  const total=sumQuarter(year,code,'M');
  const observed=obs.reduce((n,p)=>n+p.value_usd,0);
  return {hs:code,year,flow:'M',months:total.months,partner_rows:obs.length,
   observed_usd:observed,world_usd:total.value,
   observed_share:total.value!=null&&total.value>0?observed/total.value:null,
   scope:'sampled_top_seven_per_month',complete_census:false,
   missing_or_unrepresented_usd:total.value!=null?total.value-observed:null};
 };
 const coverage=()=>{
  const out=[];
  for(const code of hs)for(const flow of ['M','X']){
   const a=sumQuarter('2024',code,flow),b=sumQuarter('2025',code,flow);
   out.push({hs:code,flow,months_2024:a.months,months_2025:b.months,weight_2024:a.weight_kg!==null,weight_2025:b.weight_kg!==null});
  }
  return out;
 };
 function validate(){
  const keys=new Set();const issues=[];
  for(const r of W){
   const k=`${r.period}|${r.hs}|${r.flow}`;
   if(keys.has(k))issues.push('duplicate '+k);keys.add(k);
   if(r.value_usd<0||!Number.isSafeInteger(r.value_usd))issues.push('invalid value '+k);
   if(r.net_weight_kg!=null&&r.net_weight_kg<=0)issues.push('invalid weight '+k);
  }
  const partnerKeys=new Set(), sampleTotals=new Map();
  for(const p of P){
   const k=`${p.period}|${p.hs}|${p.flow}|${p.partner_code}`;
   if(partnerKeys.has(k))issues.push('duplicate partner '+k);partnerKeys.add(k);
   const g=`${p.period}|${p.hs}|${p.flow}`;
   sampleTotals.set(g,(sampleTotals.get(g)||0)+p.value_usd);
   if(!Number.isSafeInteger(p.value_usd)||p.value_usd<0)issues.push('invalid partner value '+k);
   const w=world(p.period,p.hs,p.flow);
   if(!w)issues.push('missing parent '+p.period+p.hs);
   if(p.value_usd>w?.value_usd)issues.push('partner exceeds world '+p.period+p.hs);
  }
  for(const [k,sum] of sampleTotals){
    const [period,code,flow]=k.split('|');
    const total=world(period,code,flow);
    if(total&&sum>total.value_usd)issues.push('selected partners exceed world '+k);
  }
  for(const code of hs)for(const flow of ['M','X'])for(const y of ['2024','2025']){
   if(sumQuarter(y,code,flow).months!==3)issues.push('incomplete quarter '+y+code+flow);
  }
  return {ok:issues.length===0,issues,monthly_totals:W.length,partner_observations:P.length};
 }
 return {meta,W,P,hs,periods,world,monthly,compare,sumQuarter,basket,changes,partners,partnerComparison,partnerCoverage,coverage,validate};
}
root.LithoEngine={createEngine};
if(typeof module==='object'&&module.exports)module.exports={createEngine};
})(typeof window!=='undefined'?window:globalThis);
