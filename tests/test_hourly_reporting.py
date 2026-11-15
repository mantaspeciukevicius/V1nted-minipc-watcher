import contextlib,io,json,os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import monitor as m

class HourlyReportingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'SCHEDULE':'hourly','NOTIFY_MODE':'deals_and_daily','DAILY_REPORT_TIME':'19:00','ENABLE_TELEGRAM':'false','ENABLE_AUTHORIZED_DIRECT_CHECKS':'false','DATABASE_PATH':str(self.root/'db.sqlite'),'BACKUP_DIR':str(self.root/'backups')})
        self.env.start(); self.old=m.ROOT; m.ROOT=self.root; (self.root/'inbox').mkdir(); self.c=m.db()
        self.output=contextlib.redirect_stdout(io.StringIO()); self.output.__enter__()
    def tearDown(self):
        self.output.__exit__(None,None,None); self.c.close(); m.ROOT=self.old; self.env.stop(); self.tmp.cleanup()
    def sources(self,records=None):
        return patch.object(m,'sources',return_value=(records or [],[{'source':'fixture','state':'AUTHORIZED_BROWSER_CHECK'}],[]))
    def row(self,price=100):
        return m.normalize(self.c,{'url':'https://vinted.lt/items/123-fixture','title':'Mini PC N100 16GB RAM','price':price},'manual_import')
    def states(self): return [r[0] for r in self.c.execute('SELECT state FROM outbox ORDER BY rowid')]
    def test_24_hour_slots(self): self.assertEqual(m.slots(),[f'{h:02d}:00' for h in range(24)])
    def test_next_full_hour(self):
        at=datetime(2026,11,14,12,12,tzinfo=timezone.utc)
        self.assertEqual(m.next_run(at).astimezone(timezone.utc),datetime(2026,11,14,13,tzinfo=timezone.utc))
    def test_exact_hour_advances(self):
        at=datetime(2026,11,14,12,tzinfo=timezone.utc)
        self.assertEqual(m.next_run(at).astimezone(timezone.utc)-at,timedelta(hours=1))
    def test_spring_skips_nonexistent_local_hour(self):
        at=datetime(2027,3,28,0,tzinfo=timezone.utc); due=m.next_run(at)
        self.assertEqual(due.hour,4); self.assertEqual(due.astimezone(timezone.utc)-at,timedelta(hours=1))
    def test_autumn_repeated_hour_runs_twice(self):
        at=datetime(2026,10,25,0,tzinfo=timezone.utc); due=m.next_run(at)
        self.assertEqual(at.astimezone(m.zone()).hour,due.hour)
        self.assertEqual(due.fold,1); self.assertEqual(due.astimezone(timezone.utc)-at,timedelta(hours=1))
    def test_summary_and_check_share_19_slot(self):
        at=datetime(2026,11,14,18,30,tzinfo=m.zone()); due,check,summary=m.next_event(at)
        self.assertEqual(due.hour,19); self.assertTrue(check); self.assertTrue(summary)
    def test_other_hour_no_summary(self):
        due,check,summary=m.next_event(datetime(2026,11,14,12,30,tzinfo=m.zone()))
        self.assertEqual(due.hour,13); self.assertTrue(check); self.assertFalse(summary)
    def test_quiet_hour_stays_local(self):
        with self.sources(): m.check('scheduled','quiet-hour')
        self.assertEqual(self.states(),['LOCAL_ONLY']); self.assertEqual(self.c.execute('SELECT COUNT(*) FROM search_runs').fetchone()[0],1)
    def test_first_candidate_notifies_then_unchanged_is_quiet(self):
        r=self.row()
        with self.sources([r]): m.check('scheduled','hour-1'); m.check('scheduled','hour-2')
        self.assertEqual(self.states(),['PENDING','LOCAL_ONLY'])
    def test_price_drop_notifies(self):
        with self.sources([self.row()]): m.check('scheduled','hour-1')
        with self.sources([self.row(90)]): m.check('scheduled','hour-2')
        self.assertEqual(self.states(),['PENDING','PENDING'])
        self.assertIn('PRICE_DROP',self.c.execute('SELECT body FROM outbox ORDER BY rowid DESC').fetchone()[0])
    def test_rejected_listing_is_quiet(self):
        r=self.row(); r['classification']='REJECTED'
        with self.sources([r]): m.check('scheduled','hour-1')
        self.assertEqual(self.states(),['LOCAL_ONLY'])
    def test_failure_saved_without_hourly_spam(self):
        with patch.object(m,'sources',side_effect=OSError): m.check('scheduled','hour-1')
        self.assertEqual(self.states(),['LOCAL_ONLY']); self.assertEqual(self.c.execute('SELECT outcome FROM search_runs').fetchone()[0],'PARTIAL_CHECK')
    def test_daily_report_even_if_no_matches(self):
        slot=datetime(2026,11,14,19,tzinfo=m.zone()); result=m.daily_summary(self.c,slot)
        self.assertIn('run_id',result); self.assertEqual(self.states(),['PENDING'])
        self.assertIn('DAILY MINI PC REPORT',self.c.execute('SELECT body FROM outbox').fetchone()[0])
    def test_daily_report_deduplicated_after_restart(self):
        slot=datetime(2026,11,14,19,tzinfo=m.zone()); m.daily_summary(self.c,slot)
        self.c.close(); self.c=m.db(); self.assertEqual(m.daily_summary(self.c,slot)['state'],'ALREADY_COMPLETED')
        self.assertEqual(self.states(),['PENDING'])
    def test_local_reports_never_flushed(self):
        with self.sources(): m.check('scheduled','hour-1')
        with patch.dict(os.environ,{'ENABLE_TELEGRAM':'true','TELEGRAM_BOT_TOKEN':'fixture','TELEGRAM_CHAT_ID':'fixture'}),patch.object(m,'urlopen') as send:
            m.flush(self.c); send.assert_not_called()
        self.assertEqual(self.states(),['LOCAL_ONLY'])
    def test_daily_report_and_quiet_hour_only_one_pending(self):
        slot=datetime(2026,11,14,19,tzinfo=m.zone()); m.daily_summary(self.c,slot)
        with self.sources(): m.check('scheduled',slot.isoformat())
        self.assertEqual(self.states(),['PENDING','LOCAL_ONLY'])
    def test_daily_window_handles_25_hour_day(self):
        m.daily_summary(self.c,datetime(2026,10,25,19,tzinfo=m.zone()))
        body=self.c.execute('SELECT body FROM outbox').fetchone()[0]
        self.assertIn('2026-10-24T19:00:00+03:00',body); self.assertIn('2026-10-25T19:00:00+02:00',body)
    def test_status_excludes_local_only_from_pending(self):
        with self.sources(): m.check('scheduled','hour-1')
        status=m.status(self.c); self.assertEqual(status['outbox'],[]); self.assertEqual(status['notification_mode'],'deals_and_daily')
    def test_missed_hourly_checks_coalesced(self):
        cursor=datetime(2026,11,14,9,1,tzinfo=timezone.utc); at=datetime(2026,11,14,13,1,tzinfo=timezone.utc)
        with patch.object(m,'check',return_value={'run_id':'recovery'}) as check:
            self.assertEqual(m.recover_hourly_gap(self.c,cursor,at),at)
            check.assert_called_once_with('recovery')
        recovery=json.loads(self.c.execute("SELECT value FROM app_settings WHERE key='last_schedule_recovery'").fetchone()[0])
        self.assertEqual(recovery['missed_checks'],4)
    def test_no_recovery_scan_when_nothing_missed(self):
        at=datetime(2026,11,14,13,1,tzinfo=timezone.utc)
        with patch.object(m,'check') as check:
            m.recover_hourly_gap(self.c,at-timedelta(minutes=1),at); check.assert_not_called()
