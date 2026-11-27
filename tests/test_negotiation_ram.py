import os, unittest
from unittest.mock import patch
from cpu_policy import parse, assessment
from notifications import format_alert
class NegotiationRamTests(unittest.TestCase):
 def test_compact_m2_storage(self):
  self.assertEqual(parse('NiPoGi Mini PC N100 16GB RAM+256GB M.2 SSD')[0:2],('N100',16))
 def test_storage_variants(self):
  for storage in ['256GB M.2 SSD','256 GB M2 NVMe','256GB SSD']:
   self.assertEqual(parse('N100 16GB RAM+'+storage)[1],16)
 def test_insufficient_installed(self):
  self.assertEqual(parse('N100 8GB RAM+256GB M.2 SSD supports up to 16GB')[2],'REJECTED')
 def test_conflicting_memory(self):
  self.assertIsNone(parse('N100 8GB RAM or 16GB RAM 256GB M.2 SSD')[1])
 def test_negotiation_band(self):
  with patch.dict(os.environ,{'NEGOTIATION_MARGIN_PERCENT':'20','MAX_ASKING_PRICE_EUR':'175'}):
   for amount,state in [(120,'WITHIN_CPU_TARGET'),(140,'NEGOTIATION_CANDIDATE'),(144,'NEGOTIATION_CANDIDATE'),(145,'ABOVE_CPU_TARGET'),(180,'ABOVE_HARD_LIMIT')]:
    self.assertEqual(assessment('N100',amount,'VERIFIED_MATCH')['deal_state'],state)
 def test_uncertain_not_promoted(self):
  self.assertEqual(assessment('N100',140,'NEEDS_MANUAL_REVIEW')['deal_state'],'CONFIGURATION_REVIEW')
 def test_alert_explains_negotiation(self):
  with patch.dict(os.environ,{'NEGOTIATION_MARGIN_PERCENT':'20'}): body=format_alert({'cpu':'N100','ram_gb':16,'asking_eur':140,'classification':'VERIFIED_MATCH'},'NEW_UNVERIFIED_CANDIDATE')
  self.assertIn('NEGOTIATION OPTION',body)

 def test_near_target_alert_once_and_sold_excluded(self):
  import tempfile
  from pathlib import Path
  import monitor as m
  with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'DATABASE_PATH':tmp+'/test.sqlite','NEGOTIATION_MARGIN_PERCENT':'20','ENABLE_AUTHORIZED_DIRECT_CHECKS':'true','MAX_ASKING_PRICE_EUR':'175'}), patch.object(m,'ROOT',Path(tmp)):
   c=m.db()
   try:
    def row(availability='UNKNOWN'):
     return m.normalize(c,dict(url='https://www.skelbiu.lt/skelbimai/nipogi-mini-pc-88410680.html',title='NiPoGi Mini PC',description='Intel N100 16GB RAM+256GB M.2 SSD',price=140,currency='EUR',availability=availability),'skelbiu_detail')
    self.assertEqual(m.observe(c,row(),'1')[0],'NEW_UNVERIFIED_CANDIDATE')
    self.assertEqual(m.observe(c,row(),'2')[0],'NO_CHANGE')
    self.assertEqual(m.observe(c,row('SOLD'),'3')[0],'NO_CHANGE')
   finally: c.close()
