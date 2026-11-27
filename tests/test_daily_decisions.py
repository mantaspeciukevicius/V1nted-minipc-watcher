"""Synthetic decision reports; no live marketplace or Telegram calls."""
import contextlib,io,json,os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import monitor as m
from cpu_policy import parse,minimum_ram
from detail_policy import priority,due,plan
from search_quality import useful
from daily_reporting import reason,funnel,availability_counts,failure_lines,build

class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=m.ROOT;m.ROOT=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'MIN_RAM_GB':'12','DATABASE_PATH':str(m.ROOT/'state.sqlite'),'ENABLE_TELEGRAM':'false','ENABLE_AUTHORIZED_DIRECT_CHECKS':'true','BUYER_MARKET':'LT'});self.env.start();self.c=m.db();self.at=datetime.now(timezone.utc)
    def tearDown(self):self.c.close();self.env.stop();m.ROOT=self.old;self.temp.cleanup()
    def row(self,ident='1234',price=110,description='12 GB RAM',**kw):
        raw=dict(url=f'https://www.skelbiu.lt/skelbimai/mini-pc-{ident}.html',title='Mini PC N100',description=description,price=price,currency='EUR',details_confirmed=True,evidence_source='Synthetic fixture',observed_at=self.at.isoformat());raw.update(kw);return m.normalize(self.c,raw,'skelbiu_detail')
    def status(self,term='n100',state='AUTHORIZED_BROWSER_CHECK',**kw):
        r=dict(source='skelbiu',marketplace='skelbiu',search_term=term,state=state,raw_count=20,listing_ids=['skelbiu:1234'],details_attempted=1);r.update(kw);return r
    def runrow(self,sources,stamp=None,counts=None):
        stamp=stamp or self.at;return dict(id='fixture',started=(stamp-timedelta(minutes=1)).isoformat(),completed=stamp.isoformat(),outcome='AUTHORIZED_BROWSER_CHECK',sources=json.dumps(sources),counts=json.dumps(counts or {}))
    def test_12_installed_qualifies(self):self.assertEqual(self.row()['classification'],'VERIFIED_MATCH')
    def test_8_stays_rejected(self):self.assertEqual(self.row(description='8GB RAM')['classification'],'REJECTED')
    def test_12_gb_variants(self):
        for text in ['12GB RAM','12 Go','12 ГБ RAM','12288 MB RAM','2x6GB RAM','8GB + 4GB RAM','DDR5 12GB']:
            with self.subTest(text=text):self.assertEqual(parse('N100 '+text)[1],12)
    def test_larger_ram(self):
        for amount in [16,20,24,32,40,48,64,96,128]:self.assertEqual(parse(f'N100 {amount} GB RAM')[1],amount)
    def test_storage_is_not_memory(self):
        for text in ['12GB eMMC','128GB SSD','128GB NVMe','128GB HDD']:self.assertIsNone(parse('N100 '+text)[1])
    def test_supported_12_not_installed(self):self.assertIsNone(parse('N100 supports up to 12GB RAM')[1])
    def test_optional_12_not_installed(self):self.assertIsNone(parse('N100 without RAM optional 12GB upgrade')[1])
    def test_configurable_minimum(self):
        with patch.dict(os.environ,{'MIN_RAM_GB':'16'}):self.assertEqual(parse('N100 12GB RAM')[2],'REJECTED')
    def test_ceiling_unchanged(self):self.assertEqual(self.row()['cpu_max_asking_eur'],120)
    def test_useful_12(self):self.assertTrue(useful(self.row(),self.at))
    def test_within_budget_priority(self):self.assertLess(priority(self.row(price=110)),priority(self.row(price=125)))
    def test_near_target_before_expensive(self):self.assertLess(priority(self.row(price=125)),priority(self.row(price=250)))
    def test_12_not_penalized_against_16(self):self.assertEqual(priority(self.row()),priority(self.row(description='16GB RAM')))
    def test_low_priority_rechecks_slowed(self):
        r=self.row(price=250,observed_at=(self.at-timedelta(hours=8)).isoformat());self.assertFalse(due(self.c,r,{'low_priority_recheck_hours':24},self.at))
    def test_promising_rechecks_stay_frequent(self):
        r=self.row(observed_at=(self.at-timedelta(hours=3)).isoformat());self.assertTrue(due(self.c,r,{},self.at))
    def test_threshold_crossing_overrides_slow_refresh(self):
        old=self.row(price=250,observed_at=(self.at-timedelta(hours=3)).isoformat());self.assertTrue(due(self.c,old,{},self.at,self.row(price=110)))
    def test_review_reason_cpu_conflict(self):self.assertEqual(reason(self.row(description='12GB RAM N150'),self.at),'CPU_CONFLICT')
    def test_review_reason_missing_cpu(self):self.assertEqual(reason(self.row(title='Mini PC',description='12GB RAM'),self.at),'CPU_UNKNOWN')
    def test_review_reason_unsupported(self):self.assertEqual(reason(self.row(title='Mini PC N200'),self.at),'CPU_UNSUPPORTED')
    def test_review_reason_ram(self):self.assertEqual(reason(self.row(description='SSD 512GB'),self.at),'RAM_UNKNOWN')
    def test_review_reason_multiple_configs(self):self.assertEqual(reason(self.row(description='12GB RAM 110 EUR\n12GB RAM 150 EUR'),self.at),'MULTIPLE_CONFIGURATIONS')
    def test_review_reason_incomplete(self):self.assertEqual(reason(self.row(description='12GB RAM without SSD'),self.at),'INCOMPLETE')
    def test_review_reason_stale(self):self.assertEqual(reason(self.row(observed_at=(self.at-timedelta(days=2)).isoformat()),self.at),'STALE')
    def test_above_budget_hardware_not_manual_review(self):self.assertEqual(reason(self.row(price=140),self.at),'QUALIFIED')
    def test_funnel_cards_not_matches(self):
        f=funnel([self.status()],[],self.at)['skelbiu'];self.assertEqual(f['raw_cards'],20);self.assertEqual(f['hardware_matches'],0)
    def test_funnel_12_hardware(self):
        f=funnel([self.status()],[self.row()],self.at)['skelbiu'];self.assertEqual(f['detail_successes'],1);self.assertEqual(f['hardware_matches'],1);self.assertEqual(f['within_target'],1)
    def test_funnel_duplicate_terms(self):self.assertEqual(funnel([self.status(),self.status('mini-pc')],[self.row()],self.at)['skelbiu']['relevant_candidates'],1)
    def test_failure_recovery_requires_same_query_later_check(self):
        fail=self.runrow([self.status(state='SEARCH_PROVIDER_FAILURE',error='TimeoutError')]);ok=self.runrow([self.status()],self.at+timedelta(minutes=30));self.assertIn('recovered in a later check',failure_lines([fail,ok])[0])
    def test_other_query_does_not_prove_recovery(self):
        fail=self.runrow([self.status(state='ACCESS_BLOCKED')]);ok=self.runrow([self.status('other')],self.at+timedelta(minutes=30));self.assertIn('not yet confirmed recovered',failure_lines([fail,ok])[0])
    def test_global_pipeline_failure_visible(self):self.assertIn('source_pipeline',failure_lines([self.runrow([dict(source='source_pipeline',state='SEARCH_PROVIDER_FAILURE')])])[0])
    def test_daily_no_duplicated_technical_footer(self):
        with contextlib.redirect_stdout(io.StringIO()):m.daily_summary(self.c,self.at.astimezone(m.zone()))
        body=self.c.execute('select body from outbox').fetchone()[0];self.assertNotIn('Mini PC watcher —',body);self.assertNotIn('Source brave:',body);self.assertNotIn('since tracking began',body)
    def test_daily_funnel_uses_window_runs_not_lifetime(self):
        self.c.execute('insert into app_settings values(?,?)',('search_quality:skelbiu',json.dumps({'n100':{'successes':9000}})))
        run=self.runrow([self.status()],counts={'funnel':funnel([self.status()],[self.row()],self.at)})
        body,metrics,_=build(self.c,self.at,self.at-timedelta(days=1),self.at,[run],[self.row()],[],lambda r:False)
        self.assertIn('searches 1/1',body);self.assertNotIn('9000',body);self.assertEqual(metrics['funnel']['skelbiu']['within_target'],1)
    def test_availability_first_vs_transition(self):
        r=self.row();m.observe(self.c,r,'fixture');self.c.execute('insert into availability_history(listing_id,observed_at,state) values(?,?,?)',(r['id'],(self.at+timedelta(hours=1)).isoformat(),'SOLD'))
        counts,dest=availability_counts(self.c,self.at-timedelta(seconds=1),self.at+timedelta(hours=2));self.assertEqual(counts['initial'],1);self.assertEqual(counts['transitions'],1);self.assertEqual(dest['SOLD'],1)
    def test_stored_snapshots_not_observed_this_run(self):
        row=self.row();body,_,_=build(self.c,self.at,self.at-timedelta(days=1),self.at,[],[row],[],lambda r:False);self.assertIn('Stored candidates: 1',body);self.assertNotIn('Observed unique listings',body)

    def test_preview_never_queues_or_records(self):
        before=self.c.execute('select count(*) from search_runs').fetchone()[0]
        result=m.daily_summary(self.c,self.at,preview=True)
        self.assertIn('body',result);self.assertEqual(self.c.execute('select count(*) from outbox').fetchone()[0],0);self.assertEqual(self.c.execute('select count(*) from search_runs').fetchone()[0],before)
    def test_preview_existing_summary_does_not_resend(self):
        with contextlib.redirect_stdout(io.StringIO()):m.daily_summary(self.c,self.at)
        before=self.c.execute('select count(*) from outbox').fetchone()[0];self.assertIn('body',m.daily_summary(self.c,self.at,preview=True));self.assertEqual(self.c.execute('select count(*) from outbox').fetchone()[0],before)
    def test_preview_does_not_count_later_observation(self):
        m.observe(self.c,self.row(observed_at=self.at.isoformat()),'fixture');result=m.daily_summary(self.c,self.at-timedelta(minutes=1),preview=True);self.assertEqual(result['counts']['stored_candidates'],0)
    def test_12_gb_card_discovery(self):
        from browser_source import candidate_hint
        self.assertTrue(candidate_hint('N100 12GB RAM'))
    def test_availability_timestamp_offsets(self):
        r=self.row();m.observe(self.c,r,'fixture')
        later=self.at+timedelta(hours=1);stamp=later.astimezone(timezone(timedelta(hours=3))).isoformat()
        self.c.execute('insert into availability_history(listing_id,observed_at,state) values(?,?,?)',(r['id'],stamp,'SOLD'))
        counts,_=availability_counts(self.c,self.at-timedelta(seconds=1),later+timedelta(seconds=1));self.assertEqual(counts['transitions'],1)

    def test_negotiation_candidates_visible_in_daily_summary(self):
        with patch.dict(os.environ,{'NEGOTIATION_MARGIN_PERCENT':'20'}):
            row=self.row(price=140)
            body,metrics,outcome=build(self.c,self.at,self.at-timedelta(days=1),self.at,[],[row],[],lambda r:False)
            self.assertIn('negotiation options 1',body)
            self.assertIn('within budget 0',body)
