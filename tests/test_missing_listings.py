import unittest,json,sqlite3
from datetime import datetime,timezone
from browser_source import missing_listing,removed_record
from recovery import update_health
class MissingListingsTests(unittest.TestCase):
 def test_explicit_item_404(self):
  self.assertTrue(missing_listing(404,'Page not found','https://www.vinted.lt/items/10409539952'))
 def test_gone_item(self):
  self.assertTrue(missing_listing(410,'Item removed','https://www.vinted.lt/items/123-item'))
 def test_restrictions_are_not_removals(self):
  for status in [200,401,403,429,500]:
   self.assertFalse(missing_listing(status,'Page not found','https://www.vinted.lt/items/123'))
  self.assertFalse(missing_listing(404,'captcha Page not found','https://www.vinted.lt/items/123'))
 def test_generic_error_not_removal(self):
  self.assertFalse(missing_listing(404,'Temporary error','https://www.vinted.lt/items/123'))
 def test_search_and_external_not_removal(self):
  for url in ['https://www.vinted.lt/catalog','https://other.example/items/123']:
   self.assertFalse(missing_listing(404,'Page not found',url))
 def test_preserves_specs_age_and_unknown_delivery(self):
  old=dict(id='vinted:123',url='https://www.vinted.lt/items/123',observed_at='2026-11-20T10:00:00+00:00',ram_gb=16,delivery='UNKNOWN')
  new=removed_record(old,'Page not found')
  self.assertEqual(new['availability'],'REMOVED');self.assertEqual(new['specs_observed_at'],old['observed_at']);self.assertEqual(new['delivery'],'UNKNOWN');self.assertNotIn('availability',old)
 def test_terminal_response_resolves_only_specific_incident(self):
  c=sqlite3.connect(':memory:');c.execute('CREATE TABLE app_settings(key TEXT PRIMARY KEY,value TEXT)')
  issues={key:dict(failures=3,state='SOURCE_UNAVAILABLE') for key in ['detail:123','detail:456']}
  c.execute('INSERT INTO app_settings VALUES(?,?)',('failure_watch:vinted',json.dumps(dict(issues=issues,alert_open=True))))
  update_health(c,[dict(source='authorized_browser',state='AUTHORIZED_BROWSER_CHECK',detail_success_ids=['vinted:123'])])
  state=json.loads(c.execute('SELECT value FROM app_settings').fetchone()[0]);self.assertEqual(set(state['issues']),{'detail:456'});c.close()

 def test_removed_card_does_not_restore_old_available_state(self):
  import tempfile,os
  from pathlib import Path
  from unittest.mock import patch
  import monitor as m
  with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'DATABASE_PATH':tmp+'/test.sqlite','ENABLE_AUTHORIZED_DIRECT_CHECKS':'true'}), patch.object(m,'ROOT',Path(tmp)):
   c=m.db()
   try:
    old=m.normalize(c,dict(url='https://www.vinted.lt/items/123',title='Mini PC N100 16GB',price=100,availability='AVAILABLE_CONFIRMED'),'authorized_browser_detail')
    m.observe(c,old,'initial')
    card=dict(old,source='authorized_browser_card')
    self.assertEqual(m.observe(c,removed_record(card,'Page not found'),'removed')[0],'NO_CHANGE')
    stored=json.loads(c.execute('SELECT current_json FROM listings').fetchone()[0]);self.assertEqual(stored['availability'],'REMOVED')
   finally:c.close()
