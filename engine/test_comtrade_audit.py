import json,unittest
from pathlib import Path
from comtrade_audit import audit_response, preview_world_url

class AuditTests(unittest.TestCase):
 def setUp(self):
  self.target={'period':'202501','hs':'7601','flow':'M','value_usd':1037631517,
    'net_weight_kg':313817191,'qty_estimated':True}
  self.raw={'data':[{'period':202501,'reporterCode':842,'partnerCode':0,'cmdCode':'7601',
   'flowCode':'M','primaryValue':1037631517,'netWgt':313817191,'isQtyEstimated':True}], 'error':''}
 def test_exact_match_with_one_observation(self):
  r=audit_response(self.target,self.raw)
  self.assertTrue(r['match']);self.assertEqual(r['problems'],[])
 def test_revision_value_is_reported_not_overwritten(self):
  self.raw['data'][0]['primaryValue']=1037631599
  r=audit_response(self.target,self.raw)
  self.assertFalse(r['match']);self.assertIn('trade_value_changed',r['problems'])
 def test_missing_or_duplicate_world_rejected(self):
  self.raw['data'][0]['partnerCode']=124
  self.assertIn('world_row_missing',audit_response(self.target,self.raw)['problems'])
  self.raw['data'][0]['partnerCode']=0
  self.raw['data'].append(dict(self.raw['data'][0]))
  self.assertIn('duplicate_world_rows',audit_response(self.target,self.raw)['problems'])
 def test_weight_unavailable_remains_unknown(self):
  self.target['net_weight_kg']=None
  self.raw['data'][0]['netWgt']=0
  self.assertTrue(audit_response(self.target,self.raw)['match'])
 def test_source_query_is_exactly_one_world_product_period(self):
  u=preview_world_url('202501','7601','M')
  for s in ('partnerCode=0','reporterCode=842','cmdCode=7601','period=202501','flowCode=M'):
   self.assertIn(s,u)
if __name__=='__main__': unittest.main()
