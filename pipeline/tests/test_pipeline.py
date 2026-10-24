"""Red/green contract gates for heterogeneous evidence acquisition."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline.ingest import EvidenceVault, SourceSpec, ingest_bytes, replay, compare_equivalent
from pipeline.adapters import parse_comtrade_world, parse_html_country_codes, parse_gleif_entity
from pipeline.registry import CENSUS_EXTRACT_2024, CENSUS_EXTRACT_2025, COMTRADE_WORLD, CENSUS_COUNTRIES, GLEIF_LEI, source_url

ROOT=Path(__file__).resolve().parents[2]

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.vault=EvidenceVault(Path(self.temp.name)); self.addCleanup(self.vault.close)

    def test_retain_raw_bytes_and_idempotent_versioned_parse(self):
        body=b'{"error":"","data":[{"period":202501,"cmdCode":"7601","flowCode":"M","reporterCode":842,"partnerCode":0,"primaryValue":12345,"netWgt":null,"isQtyEstimated":false}]}'
        result=ingest_bytes(self.vault,COMTRADE_WORLD,body,source_url(COMTRADE_WORLD,period='202501',hs='7601',flow='M'),scope={'period':'202501','hs':'7601','flow':'M'})
        self.assertEqual(result['status'],'accepted');self.assertEqual(result['records'],1)
        self.assertEqual(self.vault.raw_path(result['sha256']).read_bytes(),body)
        rows=self.vault.records(COMTRADE_WORLD.source_id)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['observation_type'],'trade_statistic_world')
        self.assertIsNone(rows[0]['data']['net_weight_kg'])
        self.assertEqual(rows[0]['data']['value_usd'],'12345')
        second=ingest_bytes(self.vault,COMTRADE_WORLD,body,source_url(COMTRADE_WORLD,period='202501',hs='7601',flow='M'),scope={'period':'202501','hs':'7601','flow':'M'})
        self.assertEqual(second['status'],'unchanged');self.assertEqual(len(self.vault.records(COMTRADE_WORLD.source_id)),1)
        self.assertEqual(replay(self.vault,COMTRADE_WORLD,result['sha256'],scope={'period':'202501','hs':'7601','flow':'M'})['status'],'unchanged')

    def test_source_api_rejects_scope_mismatch_and_quarantines_raw(self):
        body=b'{"error":"","data":[{"period":202401,"cmdCode":"7601","flowCode":"M","reporterCode":842,"partnerCode":0,"primaryValue":22}]}'
        result=ingest_bytes(self.vault,COMTRADE_WORLD,body,source_url(COMTRADE_WORLD,period='202501',hs='7601',flow='M'),scope={'period':'202501','hs':'7601','flow':'M'})
        self.assertEqual(result['status'],'quarantined')
        self.assertEqual(len(self.vault.records(COMTRADE_WORLD.source_id)),0)
        self.assertTrue(self.vault.raw_path(result['sha256']).exists())
        self.assertIn('scope',self.vault.failures()[0]['reason'].lower())

    def test_no_silent_api_truncation_or_error(self):
        scope={'period':'202501','hs':'7601','flow':'M'}
        with self.assertRaises(ValueError):parse_comtrade_world(json.dumps({'count':500,'data':[]}).encode(),scope)
        with self.assertRaises(ValueError):parse_comtrade_world(json.dumps({'error':'quota','data':[]}).encode(),scope)

    def test_html_parser_ignores_unrelated_tables(self):
        html=b'''<table><tr><th>Name</th><th>Country Code</th><th>ISO Code</th></tr>
        <tr><td>Canada</td><td>1220</td><td>CA</td></tr></table>
        <table><tr><td>Invented entity</td><td>9999</td><td>XX</td></tr></table>'''
        rows=parse_html_country_codes(html,{})
        self.assertEqual([r['key'] for r in rows],['1220'])

    def test_zip_rollback_when_acceptance_log_fails(self):
        import io, zipfile
        from pipeline.registry import CENSUS_BULK
        values=['760110','1220','0701','2023','01'] + [100,0,0,50,0,0,0]*2
        line=''.join(str(v).zfill(n) for v,n in zip(values,[6,4,4,4,2]+[15]*14))+'\n'
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as zipout:
            zipout.writestr('dporths6ir2301.txt',line)
        self.vault.conn.execute('''CREATE TRIGGER fail_accept BEFORE INSERT ON ingestion_runs
            WHEN NEW.status='accepted' BEGIN SELECT RAISE(ABORT,'test failure'); END''')
        spec=CENSUS_BULK;scope={'period':'202301'}
        output=ingest_bytes(self.vault,spec,buf.getvalue(),source_url(spec,**scope),scope,origin='https_fetch')
        self.assertEqual(output['status'],'quarantined')
        self.assertEqual(self.vault.conn.execute('SELECT COUNT(*) FROM port_hs6').fetchone()[0],0)
        self.assertEqual(self.vault.conn.execute('SELECT COUNT(*) FROM port_hs6_archives').fetchone()[0],0)
        self.assertEqual(self.vault.status()['quarantined_runs'],1)

    def test_html_reference_scrape_preserves_codes_and_cannot_be_trade_record(self):
        html=b'''<html><table><tr><th>Name</th><th>Country Code</th><th>ISO Code</th></tr>
<tr><td>Canada</td><td>1220</td><td>CA</td></tr><tr><td>China</td><td>5700</td><td>CN</td></tr></table></html>'''
        result=ingest_bytes(self.vault,CENSUS_COUNTRIES,html,CENSUS_COUNTRIES.url,scope={})
        self.assertEqual(result['status'],'accepted');self.assertEqual(result['records'],2)
        rows=self.vault.records(CENSUS_COUNTRIES.source_id)
        self.assertEqual(rows[0]['observation_type'],'geographic_reference')
        self.assertEqual({r['data']['country_code'] for r in rows},{'1220','5700'})
        bad=b'<html><form><input name="login"></form></html>'
        self.assertEqual(ingest_bytes(self.vault,CENSUS_COUNTRIES,bad,CENSUS_COUNTRIES.url,scope={})['status'],'quarantined')

    def test_rejects_foreign_host_downgrade_and_wrong_content(self):
        body=b'<html>error</html>'
        with self.assertRaises(ValueError):ingest_bytes(self.vault,CENSUS_COUNTRIES,body,'https://untrusted.example/data',scope={})
        with self.assertRaises(ValueError):ingest_bytes(self.vault,CENSUS_COUNTRIES,body,'http://www.census.gov/foreign-trade/schedules/c/countrycode.html',scope={})
        with self.assertRaises(ValueError):ingest_bytes(self.vault,CENSUS_COUNTRIES,body,'https://www.census.gov/foreign-trade/schedules/c/elsewhere.html',scope={})

    def test_two_real_scanned_extracts_are_retained_but_not_raw_archives(self):
        for spec in (CENSUS_EXTRACT_2024,CENSUS_EXTRACT_2025):
            path=ROOT/'research'/'data'/f'census_760110_{spec.period}_verified.json'
            result=ingest_bytes(self.vault,spec,path.read_bytes(),spec.url,scope={})
            self.assertEqual(result['status'],'accepted');self.assertEqual(result['records'],35 if spec.period=='202401' else 45)
        rows=self.vault.records('census_browser_hs6_extract')
        self.assertEqual(len(rows),80)
        self.assertEqual(sum(r['data']['value_usd'] for r in rows if r['data']['period']=='202501'),570362693)
        self.assertEqual(sum(r['data']['vessel_value_usd'] for r in rows if r['data']['period']=='202501'),302805284)
        status=self.vault.status()
        self.assertEqual(status['raw_census_archives_imported'],0)
        self.assertEqual(status['browser_verified_extract_rows'],80)
        self.assertEqual(status['distinct_raw_objects'],2)

    def test_unmatched_source_revision_preserves_both_versions(self):
        blob=b'<table><tr><th>Name</th><th>Country Code</th><th>ISO Code</th></tr><tr><td>Canada</td><td>1220</td><td>CA</td></tr></table>'
        a=ingest_bytes(self.vault,CENSUS_COUNTRIES,blob,CENSUS_COUNTRIES.url,{})
        b=ingest_bytes(self.vault,CENSUS_COUNTRIES,blob.replace(b'Canada',b'Canadian region'),CENSUS_COUNTRIES.url,{})
        self.assertNotEqual(a['sha256'],b['sha256'])
        self.assertEqual(len(self.vault.records('census_country_codes')),2)
        self.assertEqual(len(self.vault.revisions('census_country_codes')),2)

    def test_cross_source_comparison_rejects_false_equivalence(self):
        data=[{'observation_type':'customs_port_aggregate','data':{'hs6':'760110','value_usd':50}},
              {'observation_type':'trade_statistic_world','data':{'hs6':'760110','value_usd':'50'}}]
        result=compare_equivalent(data)
        self.assertEqual(result['status'],'not_comparable')

    def test_lei_reference_does_not_establish_importer_link(self):
        raw={'data':{'type':'lei-records','id':'506700GE1G29325QX363','attributes':{
            'lei':'506700GE1G29325QX363','entity':{'legalName':{'name':'EXAMPLE ENTITY'}},
            'registration':{'status':'ISSUED'}}}}
        result=ingest_bytes(self.vault,GLEIF_LEI,json.dumps(raw).encode(),source_url(GLEIF_LEI,lei='506700GE1G29325QX363'),scope={'lei':'506700GE1G29325QX363'})
        self.assertEqual(result['status'],'accepted')
        row=self.vault.records(GLEIF_LEI.source_id)[0]
        self.assertEqual(row['data']['legal_name'],'EXAMPLE ENTITY')
        self.assertNotIn('importer',str(row).lower())

if __name__=='__main__':unittest.main()

class DeeperEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.vault=EvidenceVault(Path(self.temp.name));self.addCleanup(self.vault.close)
    def test_browser_scan_independent_mode_checksum_rejects_tampering(self):
        original=json.loads((ROOT/'research/data/census_760110_202501_verified.json').read_text())
        # Existing source audit: port 3901, country 4280, has zero vessel value.
        row=next(r for r in original['rows'] if r['port_code']=='3901' and r['country_code']=='4280')
        self.assertEqual(row['vessel_value_usd'],0)
        row['vessel_value_usd']=246517
        result=ingest_bytes(self.vault,CENSUS_EXTRACT_2025,json.dumps(original).encode(),CENSUS_EXTRACT_2025.url,{})
        self.assertEqual(result['status'],'quarantined')
        self.assertEqual(self.vault.records(CENSUS_EXTRACT_2025.source_id),[])
    def test_browser_scan_sha_mismatch_rejected(self):
        original=json.loads((ROOT/'research/data/census_760110_202501_verified.json').read_text())
        original['source_sha256']='0'*64
        result=ingest_bytes(self.vault,CENSUS_EXTRACT_2025,json.dumps(original).encode(),CENSUS_EXTRACT_2025.url,{})
        self.assertEqual(result['status'],'quarantined')
    def test_non_zip_cannot_be_accepted_as_original_census_archive(self):
        from pipeline.registry import CENSUS_BULK
        r=ingest_bytes(self.vault,CENSUS_BULK,b'<!doctype html>Request denied',source_url(CENSUS_BULK,period='202501'),{'period':'202501'})
        self.assertEqual(r['status'],'quarantined')
        self.assertEqual(self.vault.status()['raw_census_archives_imported'],0)
    def test_census_archive_full_import_does_not_claim_shipment(self):
        from pipeline.registry import CENSUS_BULK
        import zipfile,io
        def fixture(period,country,port,value,vessel,container):
            parts=["760110",country,port,period[:4],period[4:]]
            nums=[value,0,0,vessel,0,container,0]*2
            return "".join(parts)+"".join(str(v).zfill(15) for v in nums)+"\r\n"
        target=io.BytesIO()
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('dporths6ir2301.txt',fixture(period='202301',country='1220',port='0701',value=100,vessel=40,container=25))
        result=ingest_bytes(self.vault,CENSUS_BULK,target.getvalue(),source_url(CENSUS_BULK,period='202301'),{'period':'202301'},origin='https_fetch')
        self.assertEqual(result['status'],'accepted',result)
        self.assertEqual(self.vault.status()['raw_census_archives_imported'],1)
        self.assertEqual(self.vault.conn.execute('SELECT COUNT(*) FROM port_hs6').fetchone()[0],1)
        self.assertEqual(self.vault.records('census_port_hs6_imports'),[])
    def test_cli_bootstrap_and_export(self):
        import subprocess,sys
        vault=self.vault.root
        p=subprocess.run([sys.executable,'-m','pipeline.cli','--vault',str(vault),'bootstrap'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.vault.status()['browser_verified_extract_rows'],80)
        f=vault/'normalized.csv'
        p=subprocess.run([sys.executable,'-m','pipeline.cli','--vault',str(vault),'export','--source','census_browser_hs6_extract','--out',str(f)],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        with f.open() as stream:
            self.assertEqual(sum(1 for _ in stream),81)

class RevisionSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.vault=EvidenceVault(Path(self.temp.name));self.addCleanup(self.vault.close)
    def test_explicit_current_projection_and_revision_diff(self):
        from pipeline.ingest import compare_revisions
        def html(name):
            return (f'<table><tr><th>Name</th><th>Country Code</th><th>ISO Code</th></tr>'
                    f'<tr><td>{name}</td><td>1220</td><td>CA</td></tr></table>').encode()
        a=ingest_bytes(self.vault,CENSUS_COUNTRIES,html('Canada'),CENSUS_COUNTRIES.url,{})
        b=ingest_bytes(self.vault,CENSUS_COUNTRIES,html('Canada revised'),CENSUS_COUNTRIES.url,{})
        self.assertEqual(len(self.vault.records('census_country_codes')),2)
        current=self.vault.current_records('census_country_codes')
        self.assertEqual(len(current),1)
        self.assertEqual(current[0]['data']['display_name'],'Canada revised')
        diff=compare_revisions(self.vault,'census_country_codes',a['sha256'],b['sha256'])
        self.assertEqual(diff['changed_keys'],['1220'])
        self.assertEqual(diff['added_keys'],[])
        self.assertEqual(diff['removed_keys'],[])
    def test_two_period_extracts_both_current_despite_shared_source_id(self):
        for spec in (CENSUS_EXTRACT_2024,CENSUS_EXTRACT_2025):
            blob=(ROOT/'research/data'/f'census_760110_{spec.period}_verified.json').read_bytes()
            ingest_bytes(self.vault,spec,blob,spec.url,{})
        self.assertEqual(len(self.vault.current_records('census_browser_hs6_extract')),80)
    def test_cli_export_defaults_to_current_not_all_historical_versions(self):
        import subprocess,sys
        def html(name):
            return (f'<table><tr><th>Name</th><th>Country Code</th><th>ISO Code</th></tr>'
                    f'<tr><td>{name}</td><td>1220</td><td>CA</td></tr></table>').encode()
        ingest_bytes(self.vault,CENSUS_COUNTRIES,html('Canada'),CENSUS_COUNTRIES.url,{})
        ingest_bytes(self.vault,CENSUS_COUNTRIES,html('Canada new'),CENSUS_COUNTRIES.url,{})
        dest=self.vault.root/'output.csv'
        proc=subprocess.run([sys.executable,'-m','pipeline.cli','--vault',str(self.vault.root),'export',
                 '--source','census_country_codes','--out',str(dest)],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(len(dest.read_text().splitlines()),2)
        self.assertIn('Canada new',dest.read_text())

class LiveSourceContractTests(unittest.TestCase):
    def test_real_census_html_nested_heading_annotation(self):
        # Exact public 2026-10-24 browser-inspected source fragment (truncated HTML page).
        html=b'''<table width='100%' border='0'><tr><td><table border=1>
<tr bgcolor='#FFFFCC'><th><a href='countryname.html'>Name</a></th>
<th><a href='countrycode.html'>Country Code</a> <BR><font size=-1>(NOTE: Table is sorted on this field)</font></th>
<th><a href='countryiso.html'>ISO Code</a></th></tr>
<tr><td>United States of America</td><td>1000</td><td>US</td></tr>
<tr><td>Greenland</td><td>1010</td><td>GL</td></tr>
<tr><td>Canada</td><td>1220</td><td>CA</td></tr>
<tr><td>Saint Pierre and Miquelon</td><td>1610</td><td>PM</td></tr>
</table></td></tr></table>'''
        rows=parse_html_country_codes(html,{})
        self.assertEqual(len(rows),4)
        self.assertEqual(next(x['data']['display_name'] for x in rows if x['key']=='1220'),'Canada')
    def test_real_comtrade_browser_json_with_classification_estimation_flags(self):
        # Values verified against Comtrade preview, not equal to Census HS 760110.
        payload={'count':1,'error':'','data':[{'period':'202501','cmdCode':'7601','flowCode':'M',
            'reporterCode':842,'partnerCode':0,'primaryValue':1037631517.0,
            'netWgt':339706505.614,'isQtyEstimated':True,'isNetWgtEstimated':True,
            'classificationCode':'H6','isReported':False,'isAggregate':True}]}
        row=parse_comtrade_world(json.dumps(payload).encode(),{'period':'202501','hs':'7601','flow':'M'})[0]['data']
        self.assertEqual(row['value_usd'],'1037631517.0')
        self.assertEqual(row['net_weight_kg'],'339706505.614')
        self.assertEqual(row['classification'],'H6')
        self.assertTrue(row['is_net_weight_estimated'])
        self.assertFalse(row['is_reported'])
        self.assertTrue(row['is_aggregate'])

class OriginTrustTests(unittest.TestCase):
    def test_census_zip_with_official_filename_cannot_fake_source_authenticity(self):
        import io,zipfile
        from pipeline.registry import CENSUS_BULK
        from pipeline.ingest import fetch
        with tempfile.TemporaryDirectory() as root:
            vault=EvidenceVault(root)
            self.addCleanup(vault.close)
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,'w') as z:
                z.writestr('dporths6ir2301.txt','76011012200701202501'+'0'*210+'\n')
            result=ingest_bytes(vault,CENSUS_BULK,buf.getvalue(),source_url(CENSUS_BULK,period='202501'),{'period':'202501'})
            self.assertEqual(result['status'],'quarantined')
            self.assertIn('checksum',result['reason'].lower())
            self.assertEqual(vault.status()['raw_census_archives_imported'],0)
    def test_local_api_payload_is_not_called_direct_source(self):
        fixture={'error':'','count':1,'data':[{'period':'202501','cmdCode':'7601','flowCode':'M',
                'reporterCode':842,'partnerCode':0,'primaryValue':123}]}
        with tempfile.TemporaryDirectory() as root:
            vault=EvidenceVault(root);self.addCleanup(vault.close)
            ingest_bytes(vault,COMTRADE_WORLD,json.dumps(fixture).encode(),
                source_url(COMTRADE_WORLD,period='202501',hs='7601',flow='M'),{'period':'202501','hs':'7601','flow':'M'})
            self.assertEqual(vault.records(COMTRADE_WORLD.source_id)[0]['provenance'],'local_payload_unverified_origin')

class ReplaySourceTrustTests(unittest.TestCase):
    def test_reparse_fetched_original_zip_with_new_parser_version(self):
        import io,zipfile
        from unittest.mock import patch
        from pipeline.registry import CENSUS_BULK
        with tempfile.TemporaryDirectory() as root:
            vault=EvidenceVault(root);self.addCleanup(vault.close)
            period='202301';buf=io.BytesIO()
            fields=['760110','1220','0701','2023','01']
            nums=[100,0,0,40,0,25,0]*2
            raw=''.join(fields)+''.join(str(x).zfill(15) for x in nums)+'\r\n'
            with zipfile.ZipFile(buf,'w') as z:z.writestr('dporths6ir2301.txt',raw)
            r=ingest_bytes(vault,CENSUS_BULK,buf.getvalue(),source_url(CENSUS_BULK,period=period),{'period':period},origin='https_fetch')
            self.assertEqual(r['status'],'accepted')
            from pipeline.ingest import replay
            with patch('pipeline.ingest.PARSER_VERSION','4'):
                updated=replay(vault,CENSUS_BULK,r['sha256'],{'period':period})
            with patch('pipeline.ingest.PARSER_VERSION','4'):
                duplicate=ingest_bytes(vault,CENSUS_BULK,buf.getvalue(),source_url(CENSUS_BULK,period=period),{'period':period},origin='https_fetch')
            self.assertEqual(duplicate['status'],'quarantined')
            self.assertIn('replay',duplicate['reason'])
            self.assertEqual(updated['status'],'verified_replay')
            self.assertTrue(Path(updated['staging_database']).exists())
            self.assertTrue(updated['not_promoted'])
            self.assertEqual(vault.conn.execute('SELECT COUNT(*) FROM port_hs6').fetchone()[0],1)
