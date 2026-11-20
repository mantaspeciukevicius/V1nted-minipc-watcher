"""Offline regressions for detail prioritization, languages and watchlist persistence."""
import json,os,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
import monitor as m
from cpu_policy import parse
from detail_policy import plan,due,mark_attempt,priority

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old=m.ROOT;m.ROOT=self.root
        self.env=patch.dict(os.environ,{'DATABASE_PATH':str(self.root/'watcher.sqlite'),'ENABLE_TELEGRAM':'false','ENABLE_AUTHORIZED_DIRECT_CHECKS':'true','BUYER_MARKET':'LT'});self.env.start();self.c=m.db();self.at=datetime.now(timezone.utc)
    def tearDown(self): self.c.close();self.env.stop();m.ROOT=self.old;self.tmp.cleanup()
    def row(self,ident='12345678',price=110,description='16 GB RAM',**kw):
        raw=dict(url=f'https://www.skelbiu.lt/skelbimai/mini-pc-{ident}.html',title='Mini PC N100',description=description,price=price,currency='EUR',details_confirmed=True,evidence_source='fixture',observed_at=self.at.isoformat());raw.update(kw)
        return m.normalize(self.c,raw,'skelbiu_detail')
    def test_best_discovery_first(self):
        expensive=self.row('100',160);cheap=self.row('200',105)
        selected,_=plan(self.c,{r['id']:r for r in [expensive,cheap]}, {},{'max_details':1},self.at)
        self.assertEqual(selected[0]['id'],cheap['id'])
    def test_unknown_configuration_gets_detail_slot(self):
        r=self.row(description='');selected,_=plan(self.c,{r['id']:r},{},{'max_details':5},self.at);self.assertEqual(len(selected),1)
    def test_known_cannot_consume_discovery_reserve(self):
        fresh=[self.row(str(i),100) for i in range(10,15)];old=[self.row(str(i),90,observed_at=(self.at-timedelta(hours=3)).isoformat()) for i in range(20,40)]
        selected,metrics=plan(self.c,{r['id']:r for r in fresh},{r['id']:r for r in old},{'max_details':5,'max_rechecks':2},self.at)
        self.assertEqual(len(selected),5);self.assertGreaterEqual(metrics['new_selected'],3);self.assertLessEqual(metrics['known_selected'],2)
    def test_above_target_details_capped(self):
        rows=[self.row(str(i),130+i) for i in range(5)]
        selected,_=plan(self.c,{r['id']:r for r in rows},{},{'max_details':5,'max_above_target_details':1},self.at);self.assertEqual(len(selected),1)
    def test_zero_budget(self):
        r=self.row();self.assertEqual(plan(self.c,{r['id']:r},{},{'max_details':0},self.at)[0],[])
    def test_sold_not_rechecked(self):
        r=self.row(availability='SOLD');self.assertEqual(plan(self.c,{}, {r['id']:r},{'max_details':5},self.at)[0],[])
    def test_watchlist_six_hour_cooldown(self):
        r=self.row(price=145);mark_attempt(self.c,r,self.at);self.assertFalse(due(self.c,r,{},self.at+timedelta(hours=5)));self.assertTrue(due(self.c,r,{},self.at+timedelta(hours=6)))
    def test_candidate_two_hour_cooldown(self):
        r=self.row();mark_attempt(self.c,r,self.at);self.assertFalse(due(self.c,r,{},self.at+timedelta(hours=1)));self.assertTrue(due(self.c,r,{},self.at+timedelta(hours=2)))
    def test_cooldown_survives_restart(self):
        r=self.row(price=145);mark_attempt(self.c,r,self.at);self.c.close();self.c=m.db();self.assertFalse(due(self.c,r,{},self.at+timedelta(minutes=30)))
    def test_crossing_overrides_successful_recent_check(self):
        r=self.row(price=145);card=self.row(price=115);mark_attempt(self.c,r,self.at-timedelta(seconds=1));self.assertTrue(due(self.c,r,{},self.at+timedelta(minutes=30),card))
    def test_failed_crossing_check_has_backoff(self):
        r=self.row(price=145,observed_at=(self.at-timedelta(days=1)).isoformat());card=self.row(price=115);mark_attempt(self.c,r,self.at);self.assertFalse(due(self.c,r,{},self.at+timedelta(minutes=30),card));self.assertTrue(due(self.c,r,{},self.at+timedelta(hours=1),card))
    def test_watchlist_output(self):
        r=self.row(price=145);m.observe(self.c,r,'1');self.assertEqual(m.watchlist(self.c)[0]['above_target_eur'],25)
    def test_price_crossing_alert_once(self):
        m.observe(self.c,self.row(price=145),'1');self.assertEqual(m.observe(self.c,self.row(price=115),'2')[0],'CROSSED_CPU_TARGET');self.assertEqual(m.observe(self.c,self.row(price=115),'3')[0],'NO_CHANGE')
    def test_policy_change_not_price_drop(self):
        r=self.row(price=115);r['deal_state']='ABOVE_CPU_TARGET';m.observe(self.c,r,'1');self.assertNotEqual(m.observe(self.c,self.row(price=115),'2')[0],'CROSSED_CPU_TARGET')
    def test_fx_change_not_price_crossing(self):
        r=self.row(price=145);m.observe(self.c,r,'1');new=self.row(price=145);new.update(asking_eur=110,deal_state='WITHIN_CPU_TARGET');self.assertNotEqual(m.observe(self.c,new,'2')[0],'CROSSED_CPU_TARGET')
    def test_card_preserves_spec_age(self):
        old=self.row(observed_at=(self.at-timedelta(days=2)).isoformat());m.observe(self.c,old,'1')
        raw=dict(url=old['url'],title='Mini PC N100',price=100);card=m.normalize(self.c,raw,'skelbiu_card');m.observe(self.c,card,'2')
        self.assertEqual(card['ram_gb'],16);self.assertEqual(card['specs_observed_at'],old['specs_observed_at']);self.assertNotEqual(card['classification'],'VERIFIED_MATCH');self.assertFalse(card['cost_complete'])
    def test_card_conflict_not_verified(self):
        old=self.row();m.observe(self.c,old,'1');card=m.normalize(self.c,dict(url=old['url'],title='Mini PC N100 8GB RAM',price=100),'skelbiu_card');m.observe(self.c,card,'2');self.assertEqual(card['classification'],'REJECTED')
    def test_shipping_fee_not_second_computer(self): self.assertNotEqual(self.row(description='16 GB RAM\nKompiuteris 110 EUR\nSiuntimas 5 EUR')['classification'],'NEEDS_MANUAL_REVIEW')
    def test_polish_ram_optional(self): self.assertEqual(self.row(description='8GB RAM, 16GB RAM za dopłatą 30 EUR')['classification'],'NEEDS_MANUAL_REVIEW')
    def test_lithuanian_no_installed_ram(self): self.assertIsNone(parse('N100 be operatyviosios atminties, palaiko iki 32 GB')[1])
    def test_polish_supported_not_installed(self): self.assertIsNone(parse('N100 obsługuje do 32 GB')[1])
    def test_polish_installed_and_max(self): self.assertEqual(parse('N100 pamięć RAM 16 GB, maksymalnie 32 GB')[1],16)
    def test_missing_ssd_review(self): self.assertEqual(self.row(description='16GB RAM bez dysku')['classification'],'NEEDS_MANUAL_REVIEW')
    def test_missing_adapter_review(self): self.assertEqual(self.row(description='16GB RAM bez zasilacza')['classification'],'NEEDS_MANUAL_REVIEW')
    def test_defective_polish_rejected(self): self.assertEqual(self.row(description='16GB RAM uszkodzony')['classification'],'REJECTED')
    def test_multi_configuration_prices_review(self): self.assertEqual(self.row(description='16GB RAM 110 EUR\n32GB RAM 150 EUR')['classification'],'NEEDS_MANUAL_REVIEW')
    def test_configuration_flags_recorded(self): self.assertIn('POWER_ADAPTER_MISSING',self.row(description='16GB RAM be maitinimo adapterio')['configuration_flags'])
    def test_legacy_card_can_recover_dated_detail_from_history(self):
        from detail_policy import previous
        old=self.row();m.observe(self.c,old,'1');self.c.commit()
        card=m.normalize(self.c,dict(url=old['url'],title='Mini PC N100',price=145),'skelbiu_card')
        self.c.execute('UPDATE listings SET current_json=? WHERE id=?',(json.dumps(card),card['id']));self.c.commit()
        recovered=previous(self.c,'skelbiu')[card['id']]
        self.assertEqual(recovered['ram_gb'],16);self.assertEqual(recovered['asking_eur'],145);self.assertEqual(recovered['specs_observed_at'],old['specs_observed_at'])
    def test_watchlist_not_filled_with_missing_ram(self):
        r=self.row(price=145,description='supports up to 16GB RAM');m.observe(self.c,r,'1');self.assertEqual(m.watchlist(self.c),[])
    def test_changed_currency_does_not_force_crossing(self):
        from detail_policy import price_crossed
        old=self.row(price=145);new=self.row(price=115);new['currency']='PLN';self.assertFalse(price_crossed(new,old))
    def test_card_optional_ram_cannot_reuse_complete_configuration(self):
        old=self.row();m.observe(self.c,old,'1');card=m.normalize(self.c,dict(url=old['url'],title='Mini PC N100 bez RAM',price=100),'skelbiu_card');m.observe(self.c,card,'2')
        self.assertEqual(card['classification'],'NEEDS_MANUAL_REVIEW');self.assertIn('RAM_NOT_INSTALLED',card['configuration_flags'])
    def test_card_conflicting_claim_preserved(self):
        old=self.row();m.observe(self.c,old,'1');card=m.normalize(self.c,dict(url=old['url'],title='Mini PC N100 8GB RAM',price=100),'skelbiu_card');m.observe(self.c,card,'2');self.assertEqual(card['latest_card']['ram_gb'],8);self.assertIn('CARD_SPECIFICATION_CONFLICT',card['configuration_flags'])
    def test_new_missing_storage_claim_overrides_cooldown(self):
        old=self.row();mark_attempt(self.c,old,self.at-timedelta(seconds=1));card=self.row(description='16GB RAM bez dysku');self.assertTrue(due(self.c,old,{},self.at+timedelta(minutes=30),card))
    def test_maximum_mb_is_not_installed_ram(self): self.assertIsNone(parse('N100 maximum supported RAM: 16384 MB RAM')[1])
    def test_card_price_change_does_not_reuse_old_delivery_charges(self):
        old=self.row();old['costs']=[dict(name='buyer_fee',amount=5,eur=5,status='confirmed')];old['cost_complete']=True;old['delivered_eur']=115;m.observe(self.c,old,'1')
        card=m.normalize(self.c,dict(url=old['url'],title='Mini PC N100',price=100),'skelbiu_card');m.observe(self.c,card,'2')
        self.assertIsNone(card['costs'][0]['eur']);self.assertFalse(card['cost_complete']);self.assertEqual(card['delivered_eur'],100)
        historical=json.loads(self.c.execute('SELECT body FROM listing_observations ORDER BY id LIMIT 1').fetchone()[0]);self.assertEqual(historical['costs'][0]['eur'],5)
    def test_known_search_card_alerts_when_ram_is_later_verified(self):
        card=m.normalize(self.c,dict(url=self.row()['url'],title='Mini PC N100',price=110),'skelbiu_card');self.assertEqual(m.observe(self.c,card,'1')[0],'NO_CHANGE')
        self.assertEqual(m.observe(self.c,self.row(price=110,observed_at=m.now()),'2')[0],'NEW_UNVERIFIED_CANDIDATE');self.assertEqual(m.observe(self.c,self.row(price=110,observed_at=m.now()),'3')[0],'NO_CHANGE')
