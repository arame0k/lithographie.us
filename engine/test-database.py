import sqlite3,unittest
from pathlib import Path
class DataModelTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.db=sqlite3.connect(str(Path(__file__).resolve().parent/'lithographie.sqlite'))
  cls.db.execute('PRAGMA foreign_keys=ON')
 @classmethod
 def tearDownClass(cls):cls.db.close()
 def test_source_counts(self):
  self.assertEqual(self.db.execute('SELECT count(*) FROM trade_observations').fetchone()[0],634)
  self.assertEqual(self.db.execute('SELECT count(*) FROM ports').fetchone()[0],40)
  self.assertEqual(self.db.execute('SELECT count(*) FROM legal_entities').fetchone()[0],3)
 def test_census_schema_ready_but_no_unfetched_records(self):
  self.assertEqual(self.db.execute('SELECT count(*) FROM port_hs6').fetchone()[0],0)
  self.assertEqual(self.db.execute('SELECT count(*) FROM port_hs6_archives').fetchone()[0],0)
 def test_no_unverified_company_to_vessel_joins(self):
  self.assertEqual(self.db.execute('SELECT count(*) FROM company_shipment_links').fetchone()[0],0)
  self.assertEqual(self.db.execute('SELECT count(*) FROM shipment_evidence').fetchone()[0],0)
 def test_q1_months_exact(self):
  self.assertEqual(self.db.execute('SELECT count(*) FROM quarter_world WHERE months=3').fetchone()[0],20)
 def test_fts(self):
  r=self.db.execute("SELECT kind,label FROM search_index WHERE search_index MATCH 'Alcoa' LIMIT 1").fetchone()
  self.assertEqual(r[0],'legal')
 def test_port_not_commodity_code(self):
  rows=self.db.execute('SELECT name FROM ports WHERE name LIKE "%Houston%"').fetchall()
  self.assertTrue(rows)
  # Ports deliberately contain no HS column or foreign key to aluminum trade.
  cols={x[1] for x in self.db.execute('PRAGMA table_info(ports)')}
  self.assertNotIn('hs_code',cols)
 def test_world_totals_not_double_counted(self):
  r=self.db.execute('SELECT value_usd FROM quarter_world WHERE year="2025" AND hs_code="7601" AND flow_code="M"').fetchone()[0]
  self.assertEqual(r,3408701293)
 def test_source_links(self):
  self.assertEqual(self.db.execute('SELECT count(*) FROM trade_observations t LEFT JOIN sources s ON t.source_id=s.source_id WHERE s.source_id IS NULL').fetchone()[0],0)
if __name__=='__main__':unittest.main()
