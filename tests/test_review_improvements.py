import unittest,tempfile,os,json
from pathlib import Path
from unittest.mock import patch
import monitor as m
class ReviewTests(unittest.TestCase):
 def test_increase_kept_in_history_without_alert(self):
  with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'DATABASE_PATH':tmp+'/test.sqlite','ENABLE_AUTHORIZED_DIRECT_CHECKS':'true','NEGOTIATION_MARGIN_PERCENT':'20'}), patch.object(m,'ROOT',Path(tmp)):
   c=m.db()
   try:
    def row(price):return m.normalize(c,dict(url='https://www.skelbiu.lt/skelbimai/mini-pc-123.html',title='Mini PC N100 16GB RAM',price=price,currency='EUR'),'skelbiu_detail')
    self.assertEqual(m.observe(c,row(100),'first')[0],'NEW_UNVERIFIED_CANDIDATE')
    self.assertEqual(m.observe(c,row(110),'increase')[0],'NO_CHANGE')
    self.assertEqual(c.execute('SELECT count(*) FROM price_history').fetchone()[0],2)
    self.assertEqual(c.execute("SELECT count(*) FROM alerts_sent WHERE event='PRICE_INCREASE'").fetchone()[0],0)
    self.assertEqual(m.observe(c,row(90),'drop')[0],'PRICE_DROP')
   finally:c.close()
