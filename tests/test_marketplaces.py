"""Offline policy and marketplace regressions; no network or live credentials."""
import json, os, sqlite3, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import monitor as m
from cpu_policy import DEFAULTS, parse, assessment
from skelbiu_source import listing_id, detail_raw, search_plan

class MarketplaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'DATABASE_PATH':str(self.root/'watcher.sqlite'),'ENABLE_TELEGRAM':'false','ENABLE_AUTHORIZED_DIRECT_CHECKS':'true','BUYER_MARKET':'LT','MAX_ASKING_PRICE_EUR':'175'})
        self.env.start(); self.old=m.ROOT; m.ROOT=self.root; self.c=m.db()
    def tearDown(self):
        self.c.close(); m.ROOT=self.old; self.env.stop(); self.tmp.cleanup()
    def row(self,**kw):
        raw=dict(url='https://www.skelbiu.lt/skelbimai/mini-pc-12345678.html',title='Mini PC N100 16 GB RAM',price=115,currency='EUR');raw.update(kw)
        return m.normalize(self.c,raw,'skelbiu_detail')
    def test_namespaced_identity(self): self.assertEqual(self.row()['id'],'skelbiu:12345678')
    def test_identity_same_numeric_not_merged(self):
        a=self.row(); b=m.normalize(self.c,dict(url='https://www.vinted.lt/items/12345678-mini',title='Mini PC N100 16GB',price=115),'manual_import')
        m.observe(self.c,a,'x');m.observe(self.c,b,'x');self.assertEqual(self.c.execute('select count(*) from listings').fetchone()[0],2)
    def test_external_ad_not_identity(self):
        for u in ['https://shop.lt/skelbimai/a-123.html','http://www.skelbiu.lt/skelbimai/a-123.html','https://www.skelbiu.lt/skelbimai/?id=123']:
            with self.assertRaises(ValueError): listing_id(u)
    def test_n100_vs_5600_price(self):
        self.assertEqual(self.row(price=150)['deal_state'],'ABOVE_CPU_TARGET')
        self.assertEqual(self.row(title='Mini PC Ryzen 5 5600U 16GB',price=150)['deal_state'],'WITHIN_CPU_TARGET')
    def test_threshold_crossing(self):
        m.observe(self.c,self.row(price=145),'1');self.assertEqual(m.observe(self.c,self.row(price=119),'2')[0],'CROSSED_CPU_TARGET')
    def test_above_target_no_new_alert(self): self.assertEqual(m.observe(self.c,self.row(price=145),'1')[0],'NO_CHANGE')
    def test_price_above_hard_limit_preserved(self):
        r=self.row(price=200);m.observe(self.c,r,'1');self.assertEqual(r['deal_state'],'ABOVE_HARD_LIMIT');self.assertNotEqual(r['classification'],'REJECTED')
    def test_unknown_delivery(self):
        r=self.row();self.assertEqual(r['delivery'],'UNKNOWN');self.assertFalse(r['cost_complete']);self.assertFalse(m.confirmed(r))
    def test_collection_eligible_on_skelbiu(self): self.assertNotEqual(self.row(delivery='COLLECTION_ONLY')['classification'],'REJECTED')
    def test_page_visible_not_available(self): self.assertEqual(self.row()['availability'],'UNKNOWN')
    def test_explicit_sold(self): self.assertEqual(detail_raw(self.row()['url'],'Mini PC','N100 16GB','100 €',header='Parduota')['availability'],'SOLD')
    def test_removed_label(self): self.assertEqual(detail_raw(self.row()['url'],'Mini PC','N100 16GB','100 €',header='Skelbimas pašalintas')['availability'],'REMOVED')
    def test_detail_ambiguous_price(self): self.assertIsNone(detail_raw(self.row()['url'],'Mini','16GB','100 € / 150 €')['price'])
    def test_conflicting_cpus(self): self.assertEqual(self.row(description='N95 or N100')['classification'],'NEEDS_MANUAL_REVIEW')
    def test_multiple_offers(self): self.assertEqual(self.row(description='N100 16GB 100 EUR N150 32GB 130 EUR')['classification'],'NEEDS_MANUAL_REVIEW')
    def test_missing_form_factor(self): self.assertEqual(self.row(title='Intel N100 16GB')['classification'],'NEEDS_MANUAL_REVIEW')
    def test_motherboard_rejected(self): self.assertEqual(self.row(title='Mini PC motininė N100 16GB')['classification'],'REJECTED')
    def test_ram_upgrade(self): self.assertIsNone(parse('Mini PC N100 8GB RAM optional 16GB upgrade')[1])
    def test_ram_separate(self): self.assertIsNone(parse('Mini PC N100 without RAM 16GB supported')[1])
    def test_barebone(self): self.assertIsNone(parse('Mini PC N100 barebone 16GB optional')[1])
    def test_mb_units(self): self.assertEqual(parse('N100 16384 MB RAM')[1],16)
    def test_max_ram_after(self): self.assertEqual(parse('N100 8GB RAM 16GB maximum')[1],8)
    def test_ram_storage(self): self.assertIsNone(parse('N100 16GB eMMC')[1])
    def test_policy_override(self):
        p=self.root/'policy.json';p.write_text(json.dumps({'N100':dict(status='approved',max_asking_eur=90)}))
        with patch.dict(os.environ,{'CPU_POLICY_PATH':str(p)}): self.assertEqual(assessment('N100',100,'VERIFIED_MATCH')['deal_state'],'ABOVE_CPU_TARGET')
    def test_price_lowest_history(self):
        m.observe(self.c,self.row(price=115),'1');m.observe(self.c,self.row(price=110),'2');r=self.row(price=118);m.observe(self.c,r,'3');self.assertEqual(r['original_asking_price'],'115');self.assertEqual(r['lowest_asking_price'],'110')
    def test_refresh_no_repeat(self):
        m.observe(self.c,self.row(refreshed_at='Yesterday'),'1');self.assertEqual(m.observe(self.c,self.row(refreshed_at='Today'),'2')[0],'NO_CHANGE')
    def test_search_rotation(self):
        a=search_plan({},self.c);b=search_plan({},self.c);self.assertIn('n100',a);self.assertNotEqual(a,b);self.assertLessEqual(len(a),4)
    def test_independent_adapter_failure(self):
        with patch('browser_source.collect',side_effect=RuntimeError),patch('skelbiu_source.collect',return_value=([self.row()],[dict(source='skelbiu',state='AUTHORIZED_BROWSER_CHECK')])):
            rows,statuses,_=m.sources(self.c)
        self.assertEqual(len(rows),1);self.assertTrue(any(x['source']=='authorized_browser' and x['state']=='SEARCH_PROVIDER_FAILURE' for x in statuses))
    def test_no_manufactured_idle_power(self): self.assertIsNone(self.row(idle_power_w=6)['idle_power_w'])
    def test_no_manufactured_ac_recovery(self): self.assertEqual(self.row(ac_recovery='YES')['ac_recovery'],'UNKNOWN')
    def test_backup_and_restart(self):
        m.observe(self.c,self.row(),'1');self.c.commit()
        with patch.dict(os.environ,{'BACKUP_DIR':str(self.root/'backups')}): dest=m.backup(self.c)
        with sqlite3.connect(dest) as copy: self.assertEqual(copy.execute('pragma integrity_check').fetchone()[0],'ok');self.assertEqual(copy.execute('select count(*) from listings').fetchone()[0],1)
    def test_no_false_url(self):
        with self.assertRaises(ValueError): self.row(url='https://evil.lt/skelbimai/mini-123.html')

    def test_captured_search_markup(self):
        from skelbiu_html import search_cards
        cards=search_cards((Path(__file__).parent/'fixtures/skelbiu-search.html').read_text())
        self.assertEqual(len(cards),3);self.assertEqual(cards[2]['title'],'Intel N100 16/256gb Sbc');self.assertEqual(cards[2]['price'],'175 €');self.assertEqual(listing_id(cards[2]['url']),'skelbiu:87452760')
    def test_store_ad_excluded(self):
        from skelbiu_html import search_cards
        self.assertEqual(search_cards('<a href="https://store.lt/mini" class="store-product"><div class="title">Mini PC N100 16GB</div></a>'),[])
    def test_storage_prefix(self): self.assertIsNone(parse('N100 SSD 16GB')[1])
    def test_ryzen_spacing(self): self.assertEqual(parse('Ryzen 5 5600 U 16GB RAM')[0],'5600U')
    def test_research_no_invented_performance(self): self.assertIsNone(assessment('N305',100,'NEEDS_MANUAL_REVIEW')['cpu_reference']['reference_performance_pct'])

    def test_explicit_collection_only(self):
        r=detail_raw(self.row()['url'],'Mini PC','N100 16GB RAM. Tik atsiėmimas, nesiunčiu.','115 €');self.assertEqual(r['delivery'],'COLLECTION_ONLY')
    def test_explicit_shipping_unknown_cost(self):
        raw=detail_raw(self.row()['url'],'Mini PC N100','16GB RAM. Siunčiu į visą Lietuvą.','115 €');r=m.normalize(self.c,raw,'skelbiu_detail');self.assertEqual(r['delivery'],'DIRECT_LT_CONFIRMED');self.assertFalse(r['cost_complete'])
    def test_collection_available(self):
        raw=detail_raw(self.row()['url'],'Mini PC N100','16GB RAM. Galima atsiimti.','115 €');r=m.normalize(self.c,raw,'skelbiu_detail');self.assertEqual(r['delivery'],'COLLECTION_AVAILABLE')
    def test_phone_not_candidate(self):
        from browser_source import candidate_hint
        self.assertFalse(candidate_hint('Nokia n97 mini Vintage 2000s'))

    def test_maximum_supported_ram(self): self.assertIsNone(parse('Mini PC N100 maximum supported RAM: 16GB')[1])
    def test_lithuanian_optional_after_ram(self): self.assertIsNone(parse('Mini PC N100 16GB RAM papildomai 30 EUR')[1])
    def test_multiple_prices_multiline(self): self.assertEqual(self.row(description='Mini PC N100 16GB 100 EUR\nKitas Mini PC N100 16GB 150 EUR')['classification'],'NEEDS_MANUAL_REVIEW')

    def test_explicit_empty_search(self):
        from skelbiu_source import empty_search
        self.assertTrue(empty_search('Visi skelbimai(0)\nPagal Jūsų paiešką nieko neradome.\nExternal store products'))
    def test_unknown_page_not_empty(self):
        from skelbiu_source import empty_search
        self.assertFalse(empty_search('Something went wrong'))

    def test_foreign_shipping_not_domestic(self):
        raw=detail_raw(self.row()['url'],'Mini PC N100','16GB RAM. Siunčiu į Vokietiją.','115 €');self.assertEqual(raw['delivery'],'UNKNOWN')

# Individual generated cases are counted and named, including every approved and research CPU.
for cpu,p in DEFAULTS.items():
    def test(self,cpu=cpu,p=p):
        title=('Intel '+cpu if cpu.startswith('N') else 'Ryzen '+cpu)+' mini PC 16GB RAM'
        self.assertEqual(parse(title)[0],cpu)
        self.assertEqual(parse(title)[2],'LIKELY_MATCH_UNVERIFIED' if p['status']=='approved' else 'NEEDS_MANUAL_REVIEW')
        if p['status']=='approved':
            self.assertEqual(assessment(cpu,p['max_asking_eur'],'VERIFIED_MATCH')['deal_state'],'WITHIN_CPU_TARGET')
            self.assertEqual(assessment(cpu,p['max_asking_eur']+1,'VERIFIED_MATCH')['deal_state'],'ABOVE_CPU_TARGET')
    setattr(MarketplaceTests,'test_cpu_'+cpu,test)
