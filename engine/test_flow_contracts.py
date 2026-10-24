import sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from census_port_hs6 import initialize,import_archive
from test_census_port_hs6 import fixture
from flow_contracts import port_corridors, compare_quarters
class FlowContractsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)
  self.db=sqlite3.connect(self.path/'db.sqlite');self.addCleanup(self.db.close)
  initialize(self.db)
 def add(self,year,months=('01','02','03'),two=False):
  for month in months:
   period=year+month
   content=fixture(period=period,value=100)
   if two: content+=fixture(country='0036',port='0401',period=period,value=50,vessel=40,container=25)
   z=self.path/f'{period}.zip'
   with zipfile.ZipFile(z,'w') as archive:archive.writestr('DPORTHS6I'+period[2:]+'.TXT',content)
   import_archive(self.db,z,period,'M')
 def test_incomplete_quarter_cannot_render_port_graph(self):
  self.add('2025',('01',))
  g=port_corridors(self.db,'2025','7601','M')
  self.assertEqual(g['status'],'unavailable');self.assertEqual(g['edges'],[])
  self.assertIn('incomplete',g['reason'])
 def test_complete_flow_has_deterministic_nodes_and_no_vessel_link(self):
  self.add('2025',two=True)
  g=port_corridors(self.db,'2025','7601','M',top=1)
  self.assertEqual(g['status'],'observed')
  self.assertEqual(g['total_value_usd'],450)
  self.assertEqual(g['edges'][0]['value_usd'],300)
  self.assertEqual(g['unshown_value_usd'],150)
  self.assertEqual(g['edges'][0]['source_type'],'customs_aggregate')
  self.assertEqual(len(g['source_archives']),3)
  self.assertEqual([a['period'] for a in g['source_archives']],['202501','202502','202503'])
  self.assertTrue(all(a['sha256'] and a['source_url'].startswith('https://www.census.gov/') for a in g['source_archives']))
  self.assertTrue(all(a['selection']=='complete_file' for a in g['source_archives']))
  self.assertFalse(any('company' in str(e) or 'carrier' in str(e) for e in g['edges']))
  self.assertEqual(g['mode_value_usd']['vessel'],315)
  self.assertEqual(g['mode_value_usd']['containerized_within_vessel'],195)
  self.assertEqual(g['mode_value_usd']['air'],60)
  self.assertLessEqual(g['mode_value_usd']['containerized_within_vessel'],g['mode_value_usd']['vessel'])
 def test_comparison_requires_both_complete_quarters(self):
  self.add('2025')
  c=compare_quarters(self.db,'2024','2025','7601','M')
  self.assertEqual(c['status'],'unavailable');self.assertIsNone(c['change_usd'])
  self.add('2024')
  c=compare_quarters(self.db,'2024','2025','7601','M')
  self.assertEqual(c['status'],'derived');self.assertEqual(c['change_usd'],0)
  self.assertEqual(c['change_pct'],0)
 def test_output_does_not_claim_trade_route_as_shipment(self):
  self.add('2025')
  g=port_corridors(self.db,'2025','7601','M')
  self.assertEqual(g['evidence_level'],'observed_aggregate')
  self.assertNotIn('shipment_id',str(g))
if __name__=='__main__':unittest.main()
