"""Offline tests; all constructed advertisements are explicitly synthetic."""
import json,sqlite3,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from notifications import format_alert,message_chunks,utf16_units,notification_body
from search_quality import choose_terms,record_run,statistics,load,useful
from skelbiu_html import search_cards
from browser_source import price_from_text,candidate_hint,access_problem

class Improvements(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.execute('CREATE TABLE app_settings(key TEXT PRIMARY KEY,value TEXT)');self.at=datetime.now(timezone.utc)
        self.r=dict(id='skelbiu:123',marketplace='skelbiu',cpu='N100',ram_gb=16,asking_eur=110,price=110,currency='EUR',classification='LIKELY_MATCH_UNVERIFIED',deal_state='WITHIN_CPU_TARGET',details_confirmed=True,specs_observed_at=self.at.isoformat(),observed_at=self.at.isoformat(),availability='UNKNOWN',title='Synthetic mini PC',url='https://example.invalid/synthetic',original_asking_price=130,lowest_asking_price=110)
    def tearDown(self): self.c.close()
    def status(self,term='n100',state='AUTHORIZED_BROWSER_CHECK',ids=None):
        return dict(marketplace='skelbiu',search_term=term,state=state,listing_ids=ids if ids is not None else [self.r['id']],raw_count=2,duration_seconds=5)
    def test_price_targets_differ(self):
        a=format_alert(dict(self.r,asking_eur=150),'NEW_VERIFIED_MATCH',at=self.at)
        b=format_alert(dict(self.r,cpu='5600U',asking_eur=150),'NEW_VERIFIED_MATCH',at=self.at)
        self.assertIn('ABOVE_CPU_TARGET',a);self.assertIn('WITHIN_CPU_TARGET',b)
    def test_verification_gaps(self):
        text=format_alert(self.r,'NEW_UNVERIFIED_CANDIDATE',at=self.at)
        for item in ['current availability','delivery route','power adapter','idle power','power loss','INCOMPLETE','First observed €130.00','Lowest observed €110.00']: self.assertIn(item,text)
    def test_stale_evidence(self):
        text=format_alert(dict(self.r,specs_observed_at=(self.at-timedelta(days=3)).isoformat()),'PRICE_DROP',at=self.at)
        self.assertIn('3.0 days old',text);self.assertIn('fresh detail specifications',text);self.assertNotIn('Detail-supported',text)
    def test_price_drop_and_fx(self):
        text=format_alert(dict(self.r,price_basis='MARKET_DISPLAY'),'DISPLAY_PRICE_DECREASE_UNVERIFIED',dict(self.r,price=130),at=self.at)
        self.assertIn('€20.00 (15.4%)',text);self.assertIn('NOT established',text);self.assertIn('FX',text)
    def test_no_detail_invents_no_age(self):
        text=format_alert(dict(self.r,details_confirmed=False,specs_observed_at=None),'NEW_UNVERIFIED_CANDIDATE',at=self.at)
        self.assertIn('detail page not checked',text)
    def test_chunks_unicode_and_reassembly(self):
        text=('😀 & <test>\n'*1000)+'end';parts=message_chunks(text)
        self.assertEqual(''.join(parts),text);self.assertTrue(all(utf16_units(x)<=3500 for x in parts));self.assertEqual(parts,message_chunks(text))
    def test_chunks_long_line(self):
        text='😀'*5000;self.assertEqual(''.join(message_chunks(text)),text);self.assertTrue(all(utf16_units(x)<=3500 for x in message_chunks(text)))
    def test_report_fallback(self): self.assertEqual(notification_body('daily report',[]),'daily report')
    def test_unknown_cpu_no_credit(self): self.assertFalse(useful(dict(self.r,cpu='UNKNOWN'),self.at))
    def test_no_card_credit(self): self.assertFalse(useful(dict(self.r,details_confirmed=False),self.at))
    def test_no_stale_credit(self): self.assertFalse(useful(dict(self.r,specs_observed_at=(self.at-timedelta(days=2)).isoformat()),self.at))
    def test_no_sold_credit(self): self.assertFalse(useful(dict(self.r,availability='SOLD'),self.at))
    def test_fractional_duplicate_credit(self):
        record_run(self.c,[self.status('a'),self.status('b')],[self.r],set(),self.at)
        rows=statistics(self.c);self.assertEqual(sum(x['new_useful_credit'] for x in rows),1);self.assertEqual(sum(x['new_within_target_credit'] for x in rows),1)
    def test_failure_preserves_yield(self):
        record_run(self.c,[self.status()],[self.r],set(),self.at);old=load(self.c,'skelbiu')['n100']['ema_yield']
        record_run(self.c,[self.status(state='ACCESS_BLOCKED')],[],set(),self.at)
        row=load(self.c,'skelbiu')['n100'];self.assertEqual(row['ema_yield'],old);self.assertEqual(row['successes'],1);self.assertEqual(row['failures'],1)
    def test_empty_is_success(self):
        record_run(self.c,[self.status(state='NO_USABLE_RESULTS',ids=[])],[],set(),self.at);r=statistics(self.c)[0];self.assertEqual(r['successes'],1);self.assertEqual(r['useful_hits'],0)
    def test_known_is_not_new(self):
        record_run(self.c,[self.status()],[self.r],{self.r['id']},self.at);self.assertEqual(statistics(self.c)[0]['new_useful_credit'],0)
    def test_sources_isolated(self):
        record_run(self.c,[self.status()],[self.r],set(),self.at);self.assertEqual(statistics(self.c,'vinted'),[])
    def test_round_robin_covers_every_term_with_adaptation(self):
        for _ in range(3): record_run(self.c,[self.status('a')],[self.r],set(),self.at)
        seen=set()
        for _ in range(20):
            terms=choose_terms(self.c,'skelbiu',['a','b','c','d','e'],2,{},'rotation');self.assertEqual(len(set(terms)),2);seen.update(terms)
        self.assertEqual(seen,set('abcde'))
    def test_disabled_is_exact_round_robin(self):
        cfg={'adaptive_search':False};self.assertEqual(choose_terms(self.c,'vinted',['a','b','c'],2,cfg,'r'),['a','b']);self.assertEqual(choose_terms(self.c,'vinted',['a','b','c'],2,cfg,'r'),['c','a'])
    def test_zero_budget(self): self.assertEqual(choose_terms(self.c,'vinted',['a'],0,{},'r'),[])
    def test_case_duplicates(self): self.assertEqual(len(choose_terms(self.c,'vinted',['N100',' n100 '],3,{},'r')),1)
    def test_access_failure_never_empty(self): self.assertEqual(access_problem(403,'','https://www.vinted.lt'),'ACCESS_BLOCKED')
    def test_captured_search_replay(self):
        root=Path(__file__).parent/'fixtures'
        cards=search_cards((root/'skelbiu-search-expanded.html').read_text());self.assertGreater(len(cards),2)
        self.assertTrue(all('/skelbimai/' in c['url'] for c in cards))
        sbc=next(c for c in cards if '87452760' in c['url']);self.assertEqual(price_from_text(sbc['price']),('175','EUR'))
    def test_captured_vinted_cards(self):
        cards=json.loads((Path(__file__).parent/'fixtures/vinted-cards-captured.json').read_text());self.assertGreater(len(cards),0)
        for card in cards:
            self.assertIsInstance(card,dict)
        self.assertEqual(sum(candidate_hint(c['title']) for c in cards),0)
        self.assertEqual(price_from_text(cards[0]['price']),('31.92','EUR'))
    def test_source_failure_preserved_in_alert(self):
        text=notification_body('Source skelbiu: ACCESS_BLOCKED (1 checks)',[(self.r,'PRICE_DROP',None)])
        self.assertIn('Source limitations:',text);self.assertIn('ACCESS_BLOCKED',text)
