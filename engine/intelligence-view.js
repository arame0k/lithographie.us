/* Monthly research plate. Only renders computations made by intelligence-engine.js. */
(function(){
'use strict';
const snapshot=JSON.parse(document.getElementById('monthly-corpus').textContent);
const e=window.LithoEngine.createEngine(snapshot);
const analysis=window.LithoAnalysis.makeAnalysis(e);
const censusSample=JSON.parse(document.getElementById('census-inspected-sample').textContent);
const $=id=>document.getElementById(id);
const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>n==null?'—':'$'+Math.round(n).toLocaleString('en-US');
const abbrev=n=>n==null?'—':(Math.abs(n)>=1e9?'$'+(n/1e9).toFixed(2)+'bn':'$'+(n/1e6).toFixed(1)+'m');
const perc=n=>n==null?'—':(n>0?'+':'')+n.toFixed(1)+'%';
const sign=n=>n>0?'up':n<0?'down':'flat';
const s={tab:'overview',hs:'7601',flow:'M',focus:null};
const hNames=e.meta.hs_codes;
const descFlow=f=>f==='M'?'Imports':'Exports';
const opt=(value,label,selected)=>`<option value="${esc(value)}" ${value===selected?'selected':''}>${esc(label)}</option>`;
function yearBars(a,b,max){
 if(!max)return '';
 return `<div class="intel-bars"><div class="intel-bar old" style="width:${Math.max(0,(a||0)/max*100)}%"></div><div class="intel-bar newer" style="width:${Math.max(0,(b||0)/max*100)}%"></div></div>`;
}
function updateInspector(title,fields){
 $('inspector-title').textContent=title;
 $('detail').innerHTML='<dl>'+fields.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')+'</dl>';
}
function sourceLink(url){return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">UN Comtrade ▸</a>`;}
function commonSource(){
 return `<div class="intel-source"><span>UN COMTRADE · MONTHLY · HS4 · USA</span><span>2024 Q1 / 2025 Q1</span><span>${e.W.length} TOTALS · ${e.P.length} PARTNER ROWS</span><span>PREVIEW · RAW AUDIT PENDING · NOT BOL</span></div>`;
}
function matrix(){
 const comparisons=e.hs.map(h=>e.compare(h,s.flow));
 const max=Math.max(...comparisons.flatMap(x=>[x.old.value||0,x.now.value||0]));
 const totalOld=e.basket('2024',s.flow), totalNow=e.basket('2025',s.flow);
 const sumOld=e.basket('2024','M'),sumNew=e.basket('2025','M');
 const changes= e.changes(s.flow);
 const block=comparisons.map(x=>{
  const selected=s.hs===x.hs;
  return `<button type="button" class="intel-commodity${selected?' chosen':''}" data-intel-hs="${x.hs}" aria-pressed="${selected}">
    <div class="intel-code">${x.hs}</div><div class="intel-name">${esc(hNames[x.hs])}</div>
    <div class="intel-values"><span>24 ${abbrev(x.old.value)}</span><span>25 ${abbrev(x.now.value)}</span></div>
    ${yearBars(x.old.value,x.now.value,max)}
    <div class="intel-change ${sign(x.delta)}">${perc(x.pct)}</div></button>`;
 }).join('');
 const timeline=trendChart();
 const leads=changes.map((x,i)=>`<tr class="intel-row" data-intel-hs="${x.hs}"><td>${i+1}</td><td>HS ${x.hs}</td><td class="value">${money(x.delta)}</td><td class="value ${sign(x.delta)}">${perc(x.pct)}</td></tr>`).join('');
 return `<div class="intel-kpis"><div><span>2025 Q1 · ${descFlow(s.flow).toUpperCase()}</span><strong>${abbrev(totalNow)}</strong><small>5 HS groups</small></div>
 <div><span>2024 Q1 · ${descFlow(s.flow).toUpperCase()}</span><strong>${abbrev(totalOld)}</strong><small>Same quarter</small></div>
 <div><span>CHANGE · YEAR/YEAR</span><strong class="${sign(totalNow-totalOld)}">${perc((totalNow-totalOld)/totalOld*100)}</strong><small>${abbrev(totalNow-totalOld)}</small></div>
 <div><span>2025 Q1 · NET IMPORTS</span><strong>${abbrev(sumNew-e.basket('2025','X'))}</strong><small>Imports − exports</small></div></div>
 <div class="intel-section-label">01 / COMMODITY COMPARISON <span class="intel-legend"><i></i>2024 Q1 <i></i>2025 Q1</span></div>
 <div class="intel-commodity-grid">${block}</div>
 <div class="intel-grid"><section class="intel-panel intel-trend"><div class="intel-panel-head"><span>02 / MONTHLY VALUES</span><strong>HS ${s.hs} · ${descFlow(s.flow)}</strong></div>${timeline}</section>
 <section class="intel-panel"><div class="intel-panel-head"><span>03 / LARGEST CHANGES</span><strong>Q1 · 2025 vs 2024</strong></div>
 <div class="intel-scroll"><table class="intel-table"><thead><tr><th>#</th><th>HS</th><th>VALUE Δ</th><th>YoY</th></tr></thead><tbody>${leads}</tbody></table></div></section></div>
 <div class="intel-section-label">04 / MONTHLY RECORDS <span class="intel-muted">${s.hs} · ${descFlow(s.flow)} · PRIMARY VALUE USD</span></div>
 ${recordsTable()}${commonSource()}`;
}
function trendChart(){
 const A=e.monthly(s.hs,s.flow).map(x=>x?.value_usd||0);
 const max=Math.max(...A)*1.13||1,min=0, x0=55,x1=725,y0=228,y1=28;
 const XX=m=>x0+((m-1)/2)*(x1-x0);const YY=v=>y0-(v-min)/(max-min)*(y0-y1);
 const pts=year=>[0,1,2].map(i=>[XX(i+1),YY(A[(year==='2024'?0:3)+i])]);
 const line=points=>points.map(p=>p.join(',')).join(' ');
 const ticks=[0,.25,.5,.75,1].map(v=>{const val=v*max,y=YY(val);return `<path d="M${x0} ${y}H${x1}" stroke="#e7e7e7" stroke-width=".7"/><text x="${x0-8}" y="${y+4}" text-anchor="end">${abbrev(val)}</text>`}).join('');
 const circles=(yr,points,color)=>points.map((p,i)=>`<rect x="${p[0]-3.5}" y="${p[1]-3.5}" width="7" height="7" fill="${color}" data-intel-period="${yr}0${i+1}" tabindex="0" role="button"><title>${yr} ${['Jan','Feb','Mar'][i]} · ${money(A[(yr==='2024'?0:3)+i])}</title></rect>`).join('');
 return `<div class="intel-chart-wrap"><svg viewBox="0 0 780 275" role="img" aria-label="Monthly trade value 2024 compared with 2025 for HS ${s.hs}">
 ${ticks}<polyline points="${line(pts('2024'))}" fill="none" stroke="#8a8a8a" stroke-width="2.5"/>
 <polyline points="${line(pts('2025'))}" fill="none" stroke="#2339af" stroke-width="3"/>
 ${circles('2024',pts('2024'),'#747474')}${circles('2025',pts('2025'),'#2339af')}
 ${['JAN','FEB','MAR'].map((n,i)=>`<text x="${XX(i+1)}" y="256" text-anchor="middle">${n}</text>`).join('')}</svg></div>
 <div class="intel-chart-key"><span><i class="intel-key-old"></i>2024</span><span><i class="intel-key-new"></i>2025</span><span>USD · world totals</span></div>`;
}
function recordsTable(){
 const rs=e.monthly(s.hs,s.flow);
 return `<div class="intel-scroll"><table class="intel-table"><thead><tr><th>PERIOD</th><th>VALUE USD</th><th>NET WEIGHT KG</th><th>QUANTITY FLAG</th><th>SOURCE</th></tr></thead><tbody>
 ${rs.map(r=>`<tr data-intel-period="${r.period}" class="intel-row" tabindex="0"><td>${r.period.slice(0,4)} / ${r.period.slice(4)}</td><td class="value">${money(r.value_usd)}</td><td class="value">${r.net_weight_kg===null?'—':Number(r.net_weight_kg).toLocaleString('en-US')}</td><td>${r.qty_estimated?'Qty estimated':'Not flagged'}</td><td>${sourceLink(r.url)}</td></tr>`).join('')}
 </tbody></table></div>`;
}
const nameMap={124:'Canada',784:'United Arab Emirates',32:'Argentina',710:'South Africa',699:'India',48:'Bahrain',36:'Australia',634:'Qatar',554:'New Zealand',76:'Brazil',156:'China',410:'South Korea',300:'Greece',512:'Oman',40:'Austria',56:'Belgium',682:'Saudi Arabia',764:'Thailand'};
function originMix(){
 const m=analysis.compareMix(s.hs);
 if(m.status!=='observed_subset')return '<p class="intel-shortnote">Matched quarter evidence is not available.</p>';
 const top=m.entries.slice().sort((a,b)=>(b.now_usd||0)-(a.now_usd||0)).slice(0,10);
 const lines=top.map(x=>{
  const label=nameMap[Number(x.code)]||('UN '+x.code);
  const a=(x.lower_bound_old||0)*100,b=(x.lower_bound_now||0)*100;
  return `<div class="intel-mix-row"><div><strong>${esc(label)}</strong><small>MONTHS ${x.old_months}/3 · ${x.now_months}/3</small></div><div class="intel-mix-measures"><div><span>2024 ≥ ${a.toFixed(1)}%</span><i style="width:${Math.min(a,100)}%"></i></div><div><span>2025 ≥ ${b.toFixed(1)}%</span><i style="width:${Math.min(b,100)}%"></i></div></div></div>`;
 }).join('');
 return `<div class="intel-section-label">01 / REPORTED WORLD SHARE <span class="intel-muted">OBSERVED LOWER BOUNDS</span></div>
 <div class="intel-mix-key"><span>2024 Q1 · ${(m.old.observed_share*100).toFixed(1)+'% observed'}</span><span>2025 Q1 · ${(m.now.observed_share*100).toFixed(1)+'% observed'}</span><span>Share of world total</span></div>
 <div class="intel-mix">${lines}</div>
 <p class="intel-shortnote">Unobserved: 2024 ${money(m.old.unrepresented_usd)} · 2025 ${money(m.now.unrepresented_usd)} · Missing ≠ zero</p>`;
}
function originTable(){
 const comparisons=e.partnerComparison(s.hs);
 const current= comparisons.filter(x=>x.now!=null || x.old!=null);
 const all=comparisons.slice(0,18);
 return `${originMix()}<div class="intel-section-label">02 / OBSERVED PARTNER VALUES <span class="intel-muted">TOP SEVEN PER MONTH · IMPORTS</span></div>
 <p class="intel-shortnote">Top seven monthly sample · Missing ≠ zero</p>
 <div class="intel-scroll"><table class="intel-table"><thead><tr><th>PARTNER</th><th>2024 Q1 USD</th><th>MONTHS</th><th>2025 Q1 USD</th><th>MONTHS</th><th>CHANGE</th><th>YoY</th></tr></thead><tbody>
 ${all.map(x=>`<tr tabindex="0" data-intel-partner="${x.partner_code}" class="intel-row"><td>${esc(nameMap[x.partner_code]||('UN '+x.partner_code))}</td><td class="value">${x.old==null?'—':money(x.old)}</td><td class="value">${x.old_months}/3</td><td class="value">${x.now==null?'—':money(x.now)}</td><td class="value">${x.now_months}/3</td><td class="value">${money(x.delta)}</td><td class="value ${sign(x.delta)}">${perc(x.pct)}</td></tr>`).join('')}
 </tbody></table></div>
 <div class="intel-grid"><section class="intel-panel"><div class="intel-panel-head"><span>02 / SOURCE COVERAGE</span><strong>${e.P.filter(x=>x.hs===s.hs).length} PARTNER OBSERVATIONS</strong></div>
 <div class="intel-bars-list">${['2024','2025'].map(y=>{
  const c=e.partnerCoverage(s.hs,y);
  return `<div><span>${y} Q1</span><span>${money(c.observed_usd)} observed subset</span><div class="intel-progress"><i style="width:${Math.min(100,c.observed_share*100)}%"></i></div><small>${(c.observed_share*100).toFixed(1)}% of world value · sampled</small></div>`}).join('')}</div></section>
 <section class="intel-panel"><div class="intel-panel-head"><span>03 / COMPARISON RULE</span><strong>NON-IMPUTATION</strong></div>
 <div class="intel-method">YoY requires 3/3 months in both years. No imputation.</div></section></div>
 ${commonSource()}`;
}
function censusSampleTable(){
 const rows=censusSample.rows.map(x=>`<tr><td>${esc(x.hs6)}</td><td>${esc(x.country_code)} · ${esc(x.country_name)}</td><td>${esc(x.port_code)}</td><td class="value">${money(x.value_usd)}</td></tr>`).join('');
 return `<div id="intel-census-sample"><div class="intel-section-label">04 / RAW ZIP SPOT CHECK <span class="intel-muted">JAN 2025 · SAMPLE ONLY</span></div>
 <p class="intel-shortnote">5 verified records · INCOMPLETE MONTH · Excluded from totals</p>
 <div class="intel-scroll"><table class="intel-table"><thead><tr><th>HS6</th><th>COUNTRY</th><th>CUSTOMS PORT CODE</th><th>MONTH VALUE USD</th></tr></thead><tbody>${rows}</tbody></table></div>
 <div class="intel-source"><span>ARCHIVE · <a href="${esc(censusSample.archive_url)}" target="_blank" rel="noopener noreferrer">US CENSUS ZIP ▸</a></span><span>MEMBER · ${esc(censusSample.archive_member)}</span><span>ZIP HASH · NOT ARCHIVED</span></div></div>`;
}
function evidenceTable(){
 return `<div class="intel-section-label">01 / DATA COVERAGE <span>MONTHS / 3</span></div>
 <div class="intel-scroll"><table class="intel-table"><thead><tr><th>HS</th><th>DIRECTION</th><th>2024 Q1</th><th>2025 Q1</th><th>WEIGHT 2024</th><th>WEIGHT 2025</th></tr></thead><tbody>
 ${e.coverage().map(r=>`<tr class="intel-row" tabindex="0" data-intel-hs="${r.hs}" data-intel-flow="${r.flow}"><td>${r.hs}</td><td>${descFlow(r.flow)}</td><td>${r.months_2024}/3</td><td>${r.months_2025}/3</td><td>${r.weight_2024?'COMPLETE':'INCOMPLETE'}</td><td>${r.weight_2025?'COMPLETE':'INCOMPLETE'}</td></tr>`).join('')}</tbody></table></div>
 <div class="intel-grid"><section class="intel-panel"><div class="intel-panel-head"><span>02 / PROVENANCE</span><strong>PREVIEW</strong></div><dl class="intel-dl"><dt>PROVIDER</dt><dd>UN Comtrade public preview</dd><dt>REPORTER</dt><dd>842 · United States</dd><dt>CLASSIFICATION</dt><dd>HS · four digits</dd><dt>PERIODS</dt><dd>Jan–Mar 2024 / Jan–Mar 2025</dd><dt>RECORDED</dt><dd>2026-10-24</dd><dt>RAW AUDIT</dt><dd>Not complete; source queries linked</dd><dt>WORLD ROWS</dt><dd>${e.W.length}</dd><dt>SELECTED PARTNER ROWS</dt><dd>${e.P.length}</dd></dl></section>
 <section class="intel-panel"><div class="intel-panel-head"><span>03 / EVIDENCE BOUNDARIES</span><strong>NO SHIPMENT LINKS</strong></div>
 <div class="intel-evidence"><div><b>WORLD TRADE TOTALS</b><span>60 records</span></div><div><b>PARTNER IMPORT ROWS</b><span>84 sampled</span></div><div><b>VERIFIED BOL</b><span>0</span></div><div><b>COMPANY SHIPMENT LINKS</b><span>0</span></div><div><b>VESSEL LINKS</b><span>0</span></div><div><b>COMPLETE CENSUS MONTHS</b><span>0</span></div></div></section></div>
 ${censusSampleTable()}<div class="intel-section-label">05 / COMTRADE RECORDS <span class="intel-muted">HS ${s.hs} · ${descFlow(s.flow)}</span></div>${recordsTable()}${commonSource()}`;
}
function render(){
 if(s.tab==='origins'){s.flow='M';if(!['7601','7606'].includes(s.hs))s.hs='7601';}
 const valid=e.validate();
 $('section').textContent='RESEARCH / EVIDENCE ENGINE';$('title').textContent='Trade intelligence';
 $('active-view').textContent='INTELLIGENCE';
 $('count').textContent=`${e.W.length} MONTHLY TOTALS · ${e.P.length} PARTNER ROWS`;
 $('status').textContent='UN COMTRADE · SOURCE-SPECIFIC · BUNDLED Q1 2024/2025';
 $('retrieved').textContent='MONTHLY · JAN–MAR · 2024 / 2025';
 $('analysis-context').innerHTML='<span>REPORTER / UNITED STATES</span><strong>HS 76 · 5 GROUPS</strong><span>2024 Q1 vs 2025 Q1</span><span>AGGREGATE RECORDS ONLY</span>';
 $('controls').innerHTML=`<div class="intel-tabs" role="tablist" aria-label="Research plate"><button data-intel-tab="overview" type="button" aria-selected="${s.tab==='overview'}">COMPARISON</button><button data-intel-tab="origins" type="button" aria-selected="${s.tab==='origins'}">ORIGINS</button><button data-intel-tab="evidence" type="button" aria-selected="${s.tab==='evidence'}">EVIDENCE</button></div>
 <label>COMMODITY <select id="intel-hs">${(s.tab==='origins'?['7601','7606']:e.hs).map(h=>opt(h,h+' · '+hNames[h],s.hs)).join('')}</select></label>
 <label>DIRECTION <select id="intel-flow" ${s.tab==='origins'?'disabled':''}>${opt('M','Imports',s.flow)}${s.tab==='origins'?'':opt('X','Exports',s.flow)}</select></label>`;
 $('stats').innerHTML='';$('viz').className='intel-view';
 if(s.tab==='origins' && !['7601','7606'].includes(s.hs))s.hs='7601';
 $('viz').innerHTML=!valid.ok?'<p class="intel-error">DATA CHECK FAILED: '+esc(valid.issues.join(', '))+'</p>':s.tab==='origins'?originTable():s.tab==='evidence'?evidenceTable():matrix();
 $('note').textContent='UN COMTRADE · AGGREGATES ONLY';
 const selected=$('intel-hs'); if(selected)selected.value=s.hs;
 $('controls').querySelectorAll('[data-intel-tab]').forEach(b=>b.onclick=()=>{s.tab=b.dataset.intelTab;if(s.tab==='origins'&&!['7601','7606'].includes(s.hs))s.hs='7601';render()});
 $('intel-hs').onchange=ev=>{s.hs=ev.target.value;render()};
 $('intel-flow').onchange=ev=>{s.flow=ev.target.value;render()};
 $('viz').querySelectorAll('[data-intel-hs]').forEach(el=>{
  el.addEventListener('click',()=>{s.hs=el.dataset.intelHs;if(el.dataset.intelFlow)s.flow=el.dataset.intelFlow;render()});
  el.addEventListener('keydown',ev=>{if(ev.key==='Enter'){el.click()}})
 });
 $('viz').querySelectorAll('[data-intel-period]').forEach(el=>{
  const fn=()=>{
   const r=e.world(el.dataset.intelPeriod,s.hs,s.flow);if(!r)return;
   updateInspector(`${r.period} · HS ${r.hs}`,[['FLOW',descFlow(r.flow)],['VALUE USD',money(r.value_usd)],['NET WEIGHT',r.net_weight_kg==null?'Unavailable':r.net_weight_kg.toLocaleString('en-US')+' kg'],['SOURCE',sourceLink(r.url)]]);
  };el.addEventListener('click',fn);el.addEventListener('mouseenter',fn);el.addEventListener('focus',fn);
 });
 $('viz').querySelectorAll('[data-intel-partner]').forEach(el=>{
  const fn=()=>{
   const p=e.partnerComparison(s.hs).find(x=>x.partner_code===Number(el.dataset.intelPartner));
   if(!p)return;
   updateInspector(nameMap[p.partner_code]||('UN '+p.partner_code),[['HS',s.hs],['2024 SELECTED MONTHS',p.old_months+'/3'],['2024 OBSERVED VALUE',money(p.old)],['2025 SELECTED MONTHS',p.now_months+'/3'],['2025 OBSERVED VALUE',money(p.now)],['YOY COMPARABLE',p.comparable?'Yes':'No · Sample incomplete']]);
  };el.addEventListener('click',fn);el.addEventListener('mouseenter',fn);el.addEventListener('focus',fn);
 });
}
function exportRows(){
 const head=['period','reporter_code','hs','flow','partner_code','value_usd','net_weight_kg','qty_estimated','source_url'];
 const all=[...e.W,...e.P];
 return [head,...all.map(r=>[r.period,842,r.hs,r.flow,r.partner_code,r.value_usd,r.net_weight_kg??'',r.qty_estimated??'',r.url])];
}
window.lithoIntel={render,exportRows,engine:e,analysis};
})();
