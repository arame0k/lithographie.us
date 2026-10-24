#!/usr/bin/env python3
"""Generate an explicit, reproducible inventory. Does not claim data was fetched."""
import hashlib,json,sqlite3
from pathlib import Path
from census_port_hs6 import source_url
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parent
HTML=ROOT.parent/'Lithographie_Research_Workbench.html'

def digest(contents):return hashlib.sha256(contents).hexdigest()

def build():
    parsed=BeautifulSoup(HTML.read_text(),'html.parser')
    datasets={k:parsed.find('script',id=k).text.encode() for k in ('corpus','ports','monthly-corpus')}
    annual=json.loads(datasets['corpus'])
    monthly=json.loads(datasets['monthly-corpus'])
    conn=sqlite3.connect(ROOT/'lithographie.sqlite')
    archive_rows=conn.execute('SELECT period,flow,sha256,physical_rows,stored_rows,selection FROM port_hs6_archives').fetchall()
    conn.close()
    hashes={k:digest(v) for k,v in datasets.items()}
    sample_path=ROOT/'census-browser-spotcheck.json'
    sample=json.loads(sample_path.read_text())
    futures=[]
    for yr in (2024,2025):
        for m in (1,2,3):
            p=f'{yr}{m:02d}'
            for flow in ('M','X'):
                row=next((x for x in archive_rows if x[0]==p and x[1]==flow),None)
                futures.append({'period':p,'flow':flow,'url':source_url(p,flow),
                    'ingestion':'unfetched' if row is None else row[-1],
                    'sha256':row[2] if row else None,
                    'rows':row[4] if row else None})
    report={
        'schema_version':2,'scope':'observed trade / reproducible derived measures / unknown edges',
        'data_sources':{'comtrade_annual':{'dataset_cohorts':len(annual['datasets']),'partner_observations':len(annual['observations']),'raw_response_files_included':0,'sha256':hashes['corpus']},
             'comtrade_monthly':{'world_observations':len(monthly['world']),'sampled_partner_observations':len(monthly['top_partners']), 'raw_response_files_included':0,'sha256':hashes['monthly-corpus']},
             'usace_all_cargo_ports':{'rows':len(json.loads(datasets['ports'])),'hs_breakdown_available':False,'sha256':hashes['ports']},
             'census_port_hs6':{'loaded_archives':len(archive_rows),'planned_monthly_archives':len(futures),'requested_cohorts':futures},
             'census_port_hs6_browser_spotcheck':{'rows':len(sample['rows']),'complete_months':0,'raw_archive_included':False,'archive_sha256':None,'spotcheck_manifest_sha256':digest(sample_path.read_bytes()),'archive_url':sample['archive_url'],'archive_member':sample['archive_member'],'period':sample['period']}},
        'assertions_not_supported':['company imports an HS code','shipment sailed on a named carrier','commodity passed through a named USACE port','real-time current flows'],
        'reproducible':{'root_script':'engine/build_database.py','census_ingest':'engine/census_port_hs6.py','comtrade_raw_audit':'engine/comtrade_audit.py'}
    }
    out=ROOT/'evidence-manifest.json';out.write_text(json.dumps(report,indent=2))
    print('Manifest',out,'census archives loaded',len(archive_rows))
    return report
if __name__=='__main__':build()
