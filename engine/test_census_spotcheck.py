"""Spot-check evidence must never be promoted to a complete Census month."""
from pathlib import Path
import json,unittest

ROOT=Path(__file__).resolve().parent
class CensusSpotcheckTests(unittest.TestCase):
    def test_sample_is_real_sourced_but_unarchived(self):
        s=json.loads((ROOT/'census-browser-spotcheck.json').read_text())
        self.assertEqual(s['period'],'202501')
        self.assertEqual(s['flow'],'M')
        self.assertEqual(s['archive_member'],'dporths6ir2501.txt')
        self.assertFalse(s['raw_archive_included'])
        self.assertFalse(s['full_month_coverage'])
        self.assertIsNone(s['archive_sha256'])
        self.assertEqual(len(s['rows']),5)
        self.assertEqual([(r['port_code'],r['value_usd']) for r in s['rows']],
                         [('0701',1213537),('0708',2526266),('0712',37460340),('0715',9648511),('0901',8702365)])
        self.assertTrue(all(r['hs6']=='760110' and r['country_code']=='1220' for r in s['rows']))

if __name__=='__main__': unittest.main()
