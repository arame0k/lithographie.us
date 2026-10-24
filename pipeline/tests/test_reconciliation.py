import csv, io, tempfile,unittest
from pathlib import Path
from pipeline.registry import CENSUS_EXTRACT_2024,CENSUS_EXTRACT_2025,CENSUS_COUNTRIES
from pipeline.ingest import EvidenceVault,ingest_bytes
from pipeline.reconcile import compare_monthly_hs6,chart_csv

ROOT=Path(__file__).resolve().parents[2]
class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.vault=EvidenceVault(Path(self.tmp.name));self.addCleanup(self.vault.close)
    def seed(self):
        for spec in (CENSUS_EXTRACT_2024,CENSUS_EXTRACT_2025):
            payload=(ROOT/'research/data'/f'census_760110_{spec.period}_verified.json').read_bytes()
            self.assertEqual(ingest_bytes(self.vault,spec,payload,spec.url,{})['status'],'accepted')
    def test_refuses_one_month_and_does_not_create_fake_zeros(self):
        spec=CENSUS_EXTRACT_2024
        blob=(ROOT/'research/data'/f'census_760110_{spec.period}_verified.json').read_bytes()
        ingest_bytes(self.vault,spec,blob,spec.url,{})
        result=compare_monthly_hs6(self.vault,'760110','202401','202501')
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['rows'],[])
        with self.assertRaises(ValueError):chart_csv(result)
    def test_warehouse_to_matched_month_comparison_and_ggplot_csv(self):
        self.seed()
        r=compare_monthly_hs6(self.vault,'760110','202401','202501')
        self.assertEqual(r['status'],'derived')
        self.assertEqual(r['evidence_tier'],'browser_verified_extract; original ZIP bytes not stored')
        self.assertEqual(r['base_usd'],452301510)
        self.assertEqual(r['comparison_usd'],570362693)
        self.assertEqual(r['change_usd'],118061183)
        self.assertEqual(r['base_vessel_usd'],212962776)
        self.assertEqual(r['comparison_vessel_usd'],302805284)
        self.assertEqual(len(r['rows']),51)
        one=next(x for x in r['rows'] if x['port_code']=='3802' and x['country_code']=='1220')
        self.assertEqual(one['base_usd'],118184745)
        self.assertEqual(one['comparison_usd'],145645455)
        first_year_only=next(x for x in r['rows'] if x['port_code']=='0704')
        self.assertIsNone(first_year_only['comparison_usd'])
        self.assertIsNone(first_year_only['change_usd'])
        chart=list(csv.DictReader(io.StringIO(chart_csv(r))))
        self.assertEqual(len(chart),102)
        self.assertTrue(any(x['value_usd']=='' for x in chart))
        self.assertEqual(list(chart[0]),['period','port_code','country_code','value_usd'])
    def test_out_of_scope_reference_data_cannot_be_joined_as_trade(self):
        self.seed()
        html=b'<table><tr><th>Name</th><th>Country Code</th><th>ISO Code</th></tr><tr><td>Canada</td><td>1220</td><td>CA</td></tr></table>'
        ingest_bytes(self.vault,CENSUS_COUNTRIES,html,CENSUS_COUNTRIES.url,{})
        r=compare_monthly_hs6(self.vault,'760110','202401','202501')
        self.assertEqual(r['base_usd'],452301510)
        self.assertEqual(r['sources'][0]['source_id'],'census_browser_hs6_extract')
        self.assertEqual(len(r['rows']),51)
    def test_rejects_unverified_period_and_unmatched_month(self):
        self.seed()
        self.assertEqual(compare_monthly_hs6(self.vault,'760110','202402','202502')['status'],'unavailable')
        with self.assertRaises(ValueError):compare_monthly_hs6(self.vault,'760110','202401','202502')

if __name__=='__main__':unittest.main()

class WorkflowCLITests(unittest.TestCase):
    def test_bootstrapped_warehouse_produces_ggplot_csv(self):
        import subprocess,sys,json
        with tempfile.TemporaryDirectory() as tmp:
            vault=Path(tmp)/'vault'
            a=subprocess.run([sys.executable,'-m','pipeline.cli','--vault',str(vault),'bootstrap'],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(a.returncode,0,a.stderr)
            csvfile=Path(tmp)/'plot.csv'
            b=subprocess.run([sys.executable,'-m','pipeline.cli','--vault',str(vault),'compare',
                       '--hs','760110','--base','202401','--comparison','202501','--csv',str(csvfile)],
                       cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(b.returncode,0,b.stderr)
            report=json.loads(b.stdout)
            self.assertEqual(report['change_usd'],118061183)
            self.assertEqual(report['evidence_tier'],'browser_verified_extract; original ZIP bytes not stored')
            with csvfile.open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))),102)
