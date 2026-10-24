import io
import json
import tempfile
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from workflow import validate_extract, build_comparison, rows_to_csv, load_browser_summary, build_summary_comparison, convert_browser_csv


def fixture(year,total=100):
    return {'period':f'{year}01','flow':'M','hs6':'760110','source_url':f'https://www.census.gov/source/{year}',
            'source_sha256':'f'*64,'archive_full_scan':True,'matching_rows_complete':True,
            'archive_physical_rows':320000,'matching_row_count':2,'total_usd':total,
            'rows':[{'country_code':'1220','port_code':'0712','value_usd':int(total*0.7),'air_value_usd':0,
                     'vessel_value_usd':int(total*0.6),'container_value_usd':int(total*0.1)},
                    {'country_code':'5700','port_code':'0901','value_usd':total-int(total*0.7),'air_value_usd':0,
                     'vessel_value_usd':int(total*0.2),'container_value_usd':int(total*0.1)}]}

class ContractTest(unittest.TestCase):
    def test_complete_source_required_for_comparison(self):
        a=fixture('2024');b=fixture('2025',150)
        out=build_comparison([a,b],'760110','202401','202501')
        self.assertEqual(out['status'],'derived')
        self.assertEqual(out['change_usd'],50)
        self.assertEqual(out['change_pct'],50.0)
        b['matching_rows_complete']=False
        self.assertEqual(build_comparison([a,b],'760110','202401','202501')['status'],'unavailable')

    def test_refuses_unsourced_observations(self):
        a=fixture('2024');a['source_sha256']=None
        with self.assertRaises(ValueError):validate_extract(a)

    def test_preserves_leading_zeros_and_aggregate_totals(self):
        a=fixture('2024');a['rows'][1]['port_code']='0001'
        self.assertEqual(validate_extract(a)['rows'][1]['port_code'],'0001')
        a['total_usd']+=1
        with self.assertRaises(ValueError):validate_extract(a)

    def test_rejects_duplicate_port_country(self):
        a=fixture('2024');a['rows'][1]['country_code']='1220';a['rows'][1]['port_code']='0712'
        with self.assertRaises(ValueError):validate_extract(a)

    def test_container_is_subset_of_vessel(self):
        a=fixture('2024');a['rows'][0]['container_value_usd']=101
        with self.assertRaises(ValueError):validate_extract(a)

    def test_partial_sample_never_makes_ranking(self):
        a=fixture('2024');b=fixture('2025');b['rows']=b['rows'][:1];b['matching_row_count']=1;b['total_usd']=70;b['matching_rows_complete']=False
        o=build_comparison([a,b],'760110','202401','202501')
        self.assertEqual(o['status'],'unavailable');self.assertEqual(o['port_rows'],[])

    def test_absent_record_is_not_a_zero_or_valid_delta(self):
        a=fixture('2024');b=fixture('2025',150)
        b['rows'][0]['port_code']='9999';b['rows'][1]['value_usd']=45
        # New port-country entry; sums still 150.
        r=build_comparison([a,b],'760110','202401','202501')
        port=next(x for x in r['port_rows'] if x['port_code']=='9999')
        self.assertIsNone(port['base_usd'])
        self.assertIsNone(port['delta_usd'])
        self.assertFalse(port['base_present'])
        self.assertIn('202401,9999,1220,',rows_to_csv(r))

    def test_chart_csv_contains_no_unverified_values(self):
        a=fixture('2024');b=fixture('2025',150)
        r=build_comparison([a,b],'760110','202401','202501')
        csv=rows_to_csv(r)
        self.assertIn('202401',csv);self.assertIn('0712',csv)
        self.assertIn('105',csv)
        with self.assertRaises(ValueError):rows_to_csv({'status':'unavailable'})

class BrowserSummaryTest(unittest.TestCase):
    def test_verified_january_totals_without_port_inference(self):
        payload=ROOT/'data'/'browser_scanned_totals.json'
        data=load_browser_summary(payload)
        result=build_summary_comparison(data)
        self.assertEqual(result['status'],'summary_only')
        self.assertEqual(result['change_usd'],118061183)
        self.assertEqual(result['port_rows'],[])
        self.assertIn('ALL,ALL,452301510',rows_to_csv(result))

    def test_invalid_hash_invalidates_summary(self):
        import copy
        source=load_browser_summary(ROOT/'data'/'browser_scanned_totals.json')
        bad=copy.deepcopy(source);bad['archives'][0]['source_sha256']='invalid'
        with tempfile.NamedTemporaryFile(mode='w',suffix='.json',delete=False) as f:
            json.dump(bad,f);path=f.name
        try:
            with self.assertRaises(ValueError):load_browser_summary(path)
        finally:Path(path).unlink()

class ExtractReconciliationTest(unittest.TestCase):
    def test_browser_rows_match_all_independent_source_sums(self):
        root=ROOT/'data'
        result=convert_browser_csv(root/'census_760110_jan_2024_2025.csv',
                                   root/'browser_scanned_totals.json')
        self.assertEqual(result['202401']['matching_row_count'],35)
        self.assertEqual(result['202501']['matching_row_count'],45)
        self.assertEqual(result['202501']['total_usd'],570362693)
        self.assertEqual(result['202501']['rows'][0]['country_code'],'1220')
        self.assertEqual(build_comparison(list(result.values()),'760110','202401','202501')['status'],'derived')

if __name__=='__main__': unittest.main()
