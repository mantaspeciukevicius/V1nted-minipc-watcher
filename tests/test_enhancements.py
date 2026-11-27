import unittest,tempfile,sqlite3,json,os
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from enhancements import next_page,fee_evidence,cleanup,verification_template
class EnhancementsTests(unittest.TestCase):
 def test_visible_next_same_site(self):
  self.assertEqual(next_page([dict(href='/catalog?page=2',label='2')],'https://www.vinted.lt/catalog?q=N100'),'https://www.vinted.lt/catalog?page=2')
 def test_no_external_links(self):
  self.assertIsNone(next_page([dict(href='https://bad.test/catalog?page=2',label='2')],'https://www.vinted.lt/catalog'))
 def test_no_item_links(self):
  self.assertIsNone(next_page([dict(href='/items/123',label='2')],'https://www.vinted.lt/catalog'))
 def test_skelbiu_next(self):
  self.assertEqual(next_page([dict(href='/paieska/n100/2/',label='Kitas')],'https://www.skelbiu.lt/paieska/n100/'),'https://www.skelbiu.lt/paieska/n100/2/')
 def test_explicit_buyer_fee(self):
  costs,notes=fee_evidence('100,00 €\n105,70 €įsk. Vinted mokestį',100,'https://example','stamp')
  self.assertEqual(costs['buyer_fee']['amount'],'5.70')
 def test_shipping_from_is_lower_bound(self):
  costs,notes=fee_evidence('Siuntimas\nnuo 2,41 €',100,'url','stamp')
  self.assertTrue(costs['seller_shipping']['lower_bound']);self.assertTrue(notes)
 def test_no_fee_invention(self):
  self.assertEqual(fee_evidence('Price €100',100,'url','stamp')[0],{})
 def test_impossible_negative_fee(self):
  self.assertNotIn('buyer_fee',fee_evidence('90,00 €įsk. Vinted mokestį',100,'url','stamp')[0])
 def test_manual_template_does_not_claim_verified(self):
  t=verification_template(dict(url='url',availability='AVAILABLE_CONFIRMED',delivery='DIRECT_LT_CONFIRMED'))
  self.assertEqual(t['availability'],'UNKNOWN');self.assertEqual(t['delivery'],'UNKNOWN');self.assertFalse(t['details_confirmed'])
 def test_retention_keeps_recent_and_failure_evidence(self):
  with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'EVIDENCE_RETENTION_DAYS':'30','EVIDENCE_MAX_MB':'512'}):
   root=Path(tmp);at=datetime(2026,11,27,tzinfo=timezone.utc)
   for name,file in [('20260901T000000','page.txt'),('20260902T000000','item-123.txt'),('20261126T000000','page.txt')]:
    p=root/'browser-evidence'/name;p.mkdir(parents=True);(p/file).write_text('test')
   c=sqlite3.connect(':memory:');c.execute('CREATE TABLE app_settings(key TEXT,value TEXT)');c.execute('INSERT INTO app_settings VALUES(?,?)',('failure_watch:vinted',json.dumps({'issues':{'detail:123':{}}})))
   preview=cleanup(root,c,at,dry_run=True);self.assertEqual(preview['removed_directories'],1);self.assertTrue((root/'browser-evidence/20260901T000000').exists())
   result=cleanup(root,c,at);self.assertEqual(result['removed_directories'],1);self.assertTrue((root/'browser-evidence/20260902T000000').exists());self.assertTrue((root/'browser-evidence/20261126T000000').exists());c.close()
 def test_lower_bound_never_complete(self):
  import monitor as m
  with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'DATABASE_PATH':tmp+'/test.sqlite'}),patch.object(m,'ROOT',Path(tmp)):
   c=m.db()
   try:
    stamp=datetime.now(timezone.utc).isoformat();costs={k:dict(amount=0,currency='EUR',status='confirmed',source='checkout',timestamp=stamp) for k in ['buyer_fee','seller_shipping','additional_charges']};costs['seller_shipping']['lower_bound']=True
    r=m.normalize(c,dict(url='https://www.vinted.lt/items/123',title='N100 mini PC 16GB RAM',price=100,costs=costs),'manual_import');self.assertFalse(r['cost_complete'])
   finally:c.close()

 def test_english_fee_and_shipping(self):
  costs,notes=fee_evidence('€100.00\n€105.70incl. Vinted fee\nShipping\nfrom €2.41',100,'url','stamp')
  self.assertEqual(costs['buyer_fee']['amount'],'5.70');self.assertEqual(costs['seller_shipping']['amount'],'2.41')

 def test_stale_asking_does_not_create_fee(self):
  costs,_=fee_evidence('110,00 €\n116,20 €įsk. Vinted mokestį',100,'url','stamp')
  self.assertNotIn('buyer_fee',costs)
