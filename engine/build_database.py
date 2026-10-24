#!/usr/bin/env python3
"""Materialize bounded, sourced Lithographie research evidence in SQLite."""
import json,sqlite3,re
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parent
HTML=ROOT.parent/'Lithographie_Research_Workbench.html'
D=BeautifulSoup(HTML.read_text(),'html.parser')
annual=json.loads(D.find('script',id='corpus').text)
ports=json.loads(D.find('script',id='ports').text)
monthly=json.loads((ROOT/'monthly-snapshot.json').read_text())
DB=ROOT/'lithographie.sqlite'
from db_safety import assert_safe_to_rebuild
assert_safe_to_rebuild(DB)
DB.unlink(missing_ok=True)
conn=sqlite3.connect(DB);conn.execute('PRAGMA foreign_keys=ON');conn.execute('PRAGMA journal_mode=DELETE');conn.execute('PRAGMA synchronous=FULL')
conn.executescript('''
CREATE TABLE sources(
  source_id TEXT PRIMARY KEY,provider TEXT NOT NULL,granularity TEXT NOT NULL CHECK(granularity IN('monthly','annual','port','legal')),
  url TEXT NOT NULL,as_of TEXT,source_status TEXT,notes TEXT);
CREATE TABLE trade_observations(
  source_id TEXT NOT NULL REFERENCES sources(source_id),period TEXT NOT NULL,period_type TEXT NOT NULL CHECK(period_type IN('M','A')),
  reporter_code INTEGER NOT NULL,partner_code INTEGER NOT NULL,hs_code TEXT NOT NULL,flow_code TEXT NOT NULL CHECK(flow_code IN('M','X')),
  trade_value_usd INTEGER NOT NULL CHECK(trade_value_usd>=0),net_weight_kg INTEGER CHECK(net_weight_kg>0),
  qty_estimated INTEGER CHECK(qty_estimated IN(0,1)),observation_scope TEXT NOT NULL CHECK(observation_scope IN('world','annual_preview_partner','monthly_top7_partner')),
  PRIMARY KEY(source_id,partner_code));
CREATE INDEX ix_trade_period_hs_flow ON trade_observations(period,hs_code,flow_code,partner_code);
CREATE TABLE ports(
  rank INTEGER PRIMARY KEY,name TEXT NOT NULL,longitude REAL,latitude REAL,imports_short_tons INTEGER,exports_short_tons INTEGER,total_short_tons INTEGER,
  source_id TEXT NOT NULL REFERENCES sources(source_id));
CREATE TABLE legal_entities(
  lei TEXT PRIMARY KEY,name TEXT NOT NULL,country TEXT,status TEXT,source_id TEXT NOT NULL REFERENCES sources(source_id));
CREATE TABLE shipment_evidence(
  evidence_id TEXT PRIMARY KEY,kind TEXT NOT NULL,url TEXT NOT NULL,document_date TEXT NOT NULL,
  original_shipper TEXT,original_consignee TEXT,port_id TEXT,manifest_id TEXT);
CREATE TABLE company_shipment_links(
  lei TEXT NOT NULL REFERENCES legal_entities(lei),evidence_id TEXT NOT NULL REFERENCES shipment_evidence(evidence_id),
  role TEXT NOT NULL,PRIMARY KEY(lei,evidence_id,role));
CREATE VIRTUAL TABLE search_index USING fts5(kind,record_id,label,notes,tokenize='unicode61');
CREATE VIEW quarter_world AS
SELECT substr(period,1,4) AS year,hs_code,flow_code,COUNT(*) AS months,SUM(trade_value_usd) AS value_usd,
COUNT(net_weight_kg) AS months_with_weight,SUM(net_weight_kg) AS available_weight_kg
FROM trade_observations WHERE period_type='M' AND partner_code=0 AND substr(period,5,2) IN('01','02','03')
GROUP BY substr(period,1,4),hs_code,flow_code;
CREATE VIEW monthly_source_coverage AS
SELECT period,hs_code,flow_code,COUNT(*) AS rows,
SUM(CASE WHEN partner_code=0 THEN 1 ELSE 0 END) AS world_rows,
SUM(CASE WHEN observation_scope='monthly_top7_partner' THEN 1 ELSE 0 END) AS sampled_partner_rows
FROM trade_observations WHERE period_type='M' GROUP BY period,hs_code,flow_code;
''')
for d in annual['datasets']:
 sid=d['source_id'];conn.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)',(sid,'UN Comtrade public preview','annual',d['url'],d.get('retrieved'),'partial','annual partner observations; quantities not retained'))
 conn.execute('INSERT INTO trade_observations VALUES(?,?,?,?,?,?,?,?,?,?,?)',(sid,str(d['period']),'A',842,0,str(d['hs']),d['flow'],int(d['world_total_usd']),None,None,'world'))
for o in annual['observations']:
 conn.execute('INSERT INTO trade_observations VALUES(?,?,?,?,?,?,?,?,?,?,?)',(o['source_id'],str(o['period']),'A',842,int(o['partner_code']),str(o['hs']),o['flow'],int(o['value_usd']),None,None,'annual_preview_partner'))
 conn.execute('INSERT INTO search_index VALUES(?,?,?,?)',('country',str(o['partner_code']),o['partner_name'],f"HS {o['hs']} {o['period']}"))
for year in ['2024','2025']:
 for month in ['01','02','03']:
  per=year+month
  for code in monthly['metadata']['hs_codes']:
   for flow in ['M','X']:
    rows=[x for x in monthly['world'] if (x['period'],x['hs'],x['flow'])==(per,code,flow)]
    assert len(rows)==1,(per,code,flow)
    r=rows[0];sid=f'comtrade:{per}:{code}:{flow}:842'
    conn.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)',(sid,'UN Comtrade public preview','monthly',r['url'],'2026-10-24','preview','world row; preview source; aggregate trade'))
    conn.execute('INSERT INTO trade_observations VALUES(?,?,?,?,?,?,?,?,?,?,?)',(sid,per,'M',842,0,code,flow,r['value_usd'],r['net_weight_kg'],int(r['qty_estimated']),'world'))
    for p in (p for p in monthly['top_partners'] if (p['period'],p['hs'],p['flow'])==(per,code,flow)):
     conn.execute('INSERT INTO trade_observations VALUES(?,?,?,?,?,?,?,?,?,?,?)',(sid,per,'M',842,int(p['partner_code']),code,flow,p['value_usd'],None,None,'monthly_top7_partner'))
port_source='usdot:principal-ports:2023'
conn.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)',(port_source,'USDOT / USACE','port','https://geo.dot.gov/server/rest/services/hosted/principal_ports_view/FeatureServer/0','2026-10-23','source-year-2023','all commodities, port-centric tonnage; NOT HS76'))
for p in ports:
 conn.execute('INSERT INTO ports VALUES(?,?,?,?,?,?,?,?)',(int(p['rank']),p['portname'],p['lon'],p['lat'],p['imports'],p['exports'],p['total'],port_source))
 conn.execute('INSERT INTO search_index VALUES(?,?,?,?)',('port',str(p['rank']),p['portname'],'principal ports; all commodities 2023'))
for l in annual['legal_entities']:
 sid='gleif:'+l['lei'];conn.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)',(sid,'GLEIF API','legal',l['source_url'],l.get('retrieved'),'registry','legal entity ONLY, no shipment assertion'))
 conn.execute('INSERT INTO legal_entities VALUES(?,?,?,?,?)',(l['lei'],l['legal_name'],l['country'],l['status'],sid))
 conn.execute('INSERT INTO search_index VALUES(?,?,?,?)',('legal',l['lei'],l['legal_name'],l['country']))
from census_port_hs6 import initialize
initialize(conn)
conn.commit()
summary={t:conn.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ['sources','trade_observations','ports','legal_entities','shipment_evidence','company_shipment_links']}
assert summary['trade_observations']==9+len(annual['observations'])+len(monthly['world'])+len(monthly['top_partners'])
assert summary['company_shipment_links']==0
assert conn.execute("SELECT value_usd FROM quarter_world WHERE year='2025' AND hs_code='7601' AND flow_code='M'").fetchone()[0]==1037631517+1006009950+1365059826
assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
print('Database',DB,'size',DB.stat().st_size,'summary',summary)
conn.close()
