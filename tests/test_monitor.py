import unittest, tempfile, os, json, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
sys.path.insert(0,'/app')
import monitor as m

class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'SCHEDULE':'02:00,11:00,16:00,23:00','NOTIFY_MODE':'every_check','DATABASE_PATH':str(self.root/'db.sqlite'),'ENABLE_TELEGRAM':'false','ENABLE_AUTHORIZED_DIRECT_CHECKS':'false','BACKUP_DIR':str(self.root/'backups')})
        self.env.start(); self.old=m.ROOT; m.ROOT=self.root
        (self.root/'inbox').mkdir(); self.c=m.db()
    def tearDown(self):
        self.c.close(); m.ROOT=self.old; self.env.stop(); self.tmp.cleanup()
    def row(self,**kw):
        r={'url':'https://www.vinted.lt/items/123-example','title':'Mini PC Intel N100 16 GB RAM 512 GB SSD','price':100,'currency':'EUR'}; r.update(kw); return m.normalize(self.c,r,'manual_import')
    def test_n100(self): self.assertEqual(m.specs('Intel N100 mini PC 16GB RAM')[0:2],('N100',16))
    def test_n150(self): self.assertEqual(m.specs('Intel N150 32 GB RAM')[0:2],('N150',32))
    def test_n97(self): self.assertEqual(m.specs('Intel N97 16 Go')[0:2],('N97',16))
    def test_8gb(self): self.assertEqual(m.specs('N100 8GB')[2],'REJECTED')
    def test_4gb(self): self.assertEqual(m.specs('N100 4GB')[2],'REJECTED')
    def test_supported(self): self.assertEqual(m.specs('N100 supports up to 16 GB, 8 GB installed')[2],'REJECTED')
    def test_unknown(self): self.assertEqual(m.specs('N100 supports up to 16 GB')[2],'NEEDS_MANUAL_REVIEW')
    def test_pair(self): self.assertEqual(m.specs('N97 2 × 8 GB RAM')[1],16)
    def test_cyrillic(self): self.assertEqual(m.specs('N100 16 ГБ')[1],16)
    def test_charger(self): self.assertIsNone(m.specs('N100 charger 16GB compatible with N100')[0])
    def test_ambiguous_cpu(self): self.assertIsNone(m.specs('N100 or N150 16GB')[0])
    def test_model_only(self): self.assertIsNone(m.specs('Beelink S12 16GB')[0])
    def test_sold(self): self.assertFalse(m.confirmed(self.row(availability='SOLD')))
    def test_reserved(self): self.assertFalse(m.confirmed(self.row(availability='RESERVED')))
    def test_collection(self): self.assertEqual(self.row(delivery='COLLECTION_ONLY')['classification'],'REJECTED')
    def test_unknown_delivery(self): self.assertFalse(m.confirmed(self.row()))
    def test_new_once(self):
        r=self.row(); self.assertEqual(m.observe(self.c,r,'1')[0],'NEW_UNVERIFIED_CANDIDATE'); self.assertEqual(m.observe(self.c,r,'2')[0],'NO_CHANGE')
    def test_price_drop(self):
        m.observe(self.c,self.row(),'1'); self.assertEqual(m.observe(self.c,self.row(price=75),'2')[0],'PRICE_DROP')
    def test_price_increase(self):
        m.observe(self.c,self.row(),'1'); self.assertEqual(m.observe(self.c,self.row(price=125),'2')[0],'PRICE_INCREASE')
    def test_fx_only(self):
        r=self.row(); m.observe(self.c,r,'1'); r['asking_eur']=95; self.assertEqual(m.observe(self.c,r,'2')[0],'NO_CHANGE')
    def test_currency_change(self):
        m.observe(self.c,self.row(),'1'); self.assertEqual(m.observe(self.c,self.row(price=75,currency='PLN'),'2')[0],'NO_CHANGE')
    def test_restart(self):
        r=self.row(); m.observe(self.c,r,'1'); self.c.commit(); self.c.close(); self.c=m.db(); self.assertEqual(m.observe(self.c,r,'2')[0],'NO_CHANGE')
    def test_telegram_failure(self):
        self.c.execute("INSERT INTO search_runs(id) VALUES('x')")
        self.c.execute("INSERT INTO outbox(id,body,state) VALUES('x','report','PENDING')"); self.c.commit()
        with patch.dict(os.environ,{'ENABLE_TELEGRAM':'true','TELEGRAM_BOT_TOKEN':'test','TELEGRAM_CHAT_ID':'test'}),patch.object(m,'urlopen',side_effect=OSError): m.flush(self.c)
        r=self.c.execute('SELECT * FROM outbox').fetchone(); self.assertEqual(r['state'],'PENDING'); self.assertEqual(r['attempts'],1)
    def test_partial_report(self):
        body,_,outcome=m.report('r','manual',[{'source':'test','state':'ACCESS_BLOCKED'}],[],[]); self.assertEqual(outcome,'PARTIAL_CHECK'); self.assertIn('ACCESS_BLOCKED',body)
    def test_no_matches_report(self): self.assertIn('No new verified',m.report('r','scheduled',[],[],[])[0])
    def test_dst_spring(self):
        at=datetime(2027,3,28,0,1,tzinfo=timezone.utc); self.assertEqual(m.next_run(at).hour,11); self.assertEqual(m.next_run(at).utcoffset(),timedelta(hours=3))
    def test_dst_autumn(self):
        at=datetime(2026,10,25,0,1,tzinfo=timezone.utc); self.assertEqual(m.next_run(at).hour,11); self.assertEqual(m.next_run(at).utcoffset(),timedelta(hours=2))
    def test_four_times(self): self.assertEqual(m.slots(),['02:00','11:00','16:00','23:00'])
    def test_no_configuration(self):
        rows,states,_=m.sources(self.c); self.assertEqual(rows,[]); self.assertTrue(any(s['state']=='UNAVAILABLE' for s in states))
    def test_unknown_fees(self):
        r=self.row(); self.assertFalse(r['cost_complete']); self.assertIsNone(r['tier'])
    def test_stale(self):
        r=self.row(observed_at=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),availability='AVAILABLE_CONFIRMED',availability_evidence='manual',delivery='DIRECT_LT_CONFIRMED',delivery_evidence='checkout',evidence_source='manual',details_confirmed=True); self.assertFalse(m.confirmed(r))
    def test_verified(self):
        r=self.row(availability='AVAILABLE_CONFIRMED',availability_evidence='manual',delivery='DIRECT_LT_CONFIRMED',delivery_evidence='checkout',evidence_source='manual',details_confirmed=True); self.assertTrue(m.confirmed(r))
    def test_index_not_verified(self):
        r=m.normalize(self.c,{'url':'https://vinted.lt/items/123-test','title':'N100 16GB','availability':'AVAILABLE_CONFIRMED'},'brave_index'); self.assertEqual(r['availability'],'UNKNOWN')
    def test_url_security(self):
        with self.assertRaises(ValueError): self.row(url='https://vinted.lt.evil.com/items/123')
    def test_numeric_id(self): self.assertEqual(self.row()['id'],'vinted:123')
    def test_backup(self):
        p=m.backup(self.c); self.assertTrue(Path(p).exists())
    def test_import_check(self):
        (self.root/'inbox'/'sample.json').write_text(json.dumps({'url':'https://vinted.lt/items/999-fixture','title':'N100 16GB','price':100}))
        result=m.check(); self.assertIn('run_id',result); self.assertEqual(self.c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
    def test_empty_check_report(self):
        m.check(); self.assertEqual(self.c.execute('SELECT COUNT(*) FROM search_runs').fetchone()[0],1)
    def test_slot_dedup(self):
        m.check('scheduled','test-slot'); self.assertEqual(m.check('scheduled','test-slot')['state'],'ALREADY_COMPLETED')
    def test_old_observation(self):
        m.observe(self.c,self.row(),'1'); r=self.row(price=50,observed_at=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()); self.assertEqual(m.observe(self.c,r,'2')[0],'NO_CHANGE')
    def test_ram_max_suffix(self): self.assertIsNone(m.specs('N100 16GB maximum')[1])
    def test_over_budget(self): self.assertEqual(self.row(price=200)['classification'],'REJECTED')
    def test_accessory(self): self.assertEqual(self.row(title='N100 charger',description='For mini PC 16 GB')['classification'],'REJECTED')
    def test_negative_price(self):
        with self.assertRaises(ValueError): self.row(price=-1)
    def test_bad_date(self):
        with self.assertRaises(ValueError): self.row(observed_at='2026-11-14')
    def test_eur_conversion(self):
        self.c.execute('INSERT INTO currency_rates VALUES(?,?,?,?)',(datetime.now(timezone.utc).date().isoformat(),'PLN','4','ECB'))
        self.assertEqual(self.row(price=400,currency='PLN')['asking_eur'],100)
    def test_complete_cost(self):
        costs={k:{'amount':0,'currency':'EUR','source':'manual checkout','timestamp':m.now(),'status':'confirmed'} for k in ['buyer_fee','seller_shipping','additional_charges']}
        r=self.row(costs=costs); self.assertTrue(r['cost_complete']); self.assertEqual(r['delivered_eur'],100)
    def test_sold_no_event(self): self.assertEqual(m.observe(self.c,self.row(availability='SOLD'),'1')[0],'NO_CHANGE')
    def test_malformed_import(self):
        (self.root/'inbox'/'bad.json').write_text('{')
        result=m.check(); self.assertEqual(result['outcome'],'PARTIAL_CHECK'); self.assertTrue((self.root/'inbox'/'bad.json').exists())
    def test_cross_domain_identity(self): self.assertEqual(self.row(url='https://vinted.pl/items/123-other')['id'],self.row()['id'])
    def test_brave_mock(self):
        hit={'web':{'results':[{'url':'https://vinted.pl/items/789-test','title':'Mini PC N150 16GB','description':'Indexed lead'}]}}
        with patch.dict(os.environ,{'BRAVE_API_KEY':'fixture','BRAVE_STORAGE_LICENSE_CONFIRMED':'true'}),patch.object(m,'QUERIES',['N150']),patch.object(m,'request_json',return_value=hit),patch.object(m.time,'sleep'):
            records,states,_=m.sources(self.c)
        self.assertEqual(len(records),5); self.assertTrue(all(r['availability']=='UNKNOWN' for r in records))
    def test_telegram_success_and_restart(self):
        self.c.execute("INSERT INTO search_runs(id) VALUES('x')")
        self.c.execute("INSERT INTO outbox(id,body,state) VALUES('x','report','PENDING')"); self.c.commit()
        response=unittest.mock.MagicMock(); response.__enter__.return_value=__import__('io').StringIO('{"ok":true,"result":{"message_id":123}}')
        with patch.dict(os.environ,{'ENABLE_TELEGRAM':'true','TELEGRAM_BOT_TOKEN':'test','TELEGRAM_CHAT_ID':'test'}),patch.object(m,'urlopen',return_value=response) as send:
            m.flush(self.c); m.flush(self.c); self.assertEqual(send.call_count,1)
        self.assertEqual(self.c.execute('SELECT state FROM outbox').fetchone()[0],'DELIVERED')
    def test_schedule_sequence(self):
        at=datetime(2026,11,14,0,0,tzinfo=m.zone()); hours=[]
        for _ in range(4): at=m.next_run(at); hours.append(at.hour)
        self.assertEqual(hours,[2,11,16,23])
    def test_source_exception_report(self):
        with patch.object(m,'sources',side_effect=OSError): result=m.check()
        self.assertEqual(result['outcome'],'PARTIAL_CHECK')
    def test_authorized_browser_details(self):
        raw={'url':'https://vinted.lt/items/123-test','title':'Mini PC N100 16GB RAM','availability':'AVAILABLE_CONFIRMED','availability_evidence':'Rendered enabled purchase button','details_confirmed':True,'evidence_source':'Rendered listing page'}
        with patch.dict(os.environ,{'ENABLE_AUTHORIZED_DIRECT_CHECKS':'true'}): r=m.normalize(self.c,raw,'authorized_browser_detail')
        self.assertEqual(r['classification'],'VERIFIED_MATCH'); self.assertEqual(r['availability'],'AVAILABLE_CONFIRMED'); self.assertEqual(r['delivery'],'UNKNOWN'); self.assertFalse(m.confirmed(r))
    def test_browser_card_never_available(self):
        with patch.dict(os.environ,{'ENABLE_AUTHORIZED_DIRECT_CHECKS':'true'}):
            r=m.normalize(self.c,{'url':'https://vinted.lt/items/123-test','title':'N100 16GB','availability':'AVAILABLE_CONFIRMED'},'authorized_browser_card')
        self.assertEqual(r['availability'],'UNKNOWN')
    def test_market_display_drop_unverified(self):
        r=self.row(); r['price_basis']='MARKET_DISPLAY'; m.observe(self.c,r,'1')
        r=self.row(price=90); r['price_basis']='MARKET_DISPLAY'
        self.assertEqual(m.observe(self.c,r,'2')[0],'DISPLAY_PRICE_DECREASE_UNVERIFIED')
if __name__=='__main__': unittest.main()
