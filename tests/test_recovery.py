"""Deterministic recovery simulations; never send real Telegram or network traffic."""
import contextlib,io,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock,patch
from recovery import fetch,RunBudgetExceeded,remaining_ms,transient,update_health,format_health
import monitor as m

class Clock:
    def __init__(self):self.now=0
    def __call__(self):return self.now
    def sleep(self,seconds):self.now+=seconds

class RetryTests(unittest.TestCase):
    def setUp(self):self.clock=Clock();self.events=[]
    def invoke(self,op,deadline=100,**kwargs):return fetch(op,deadline,events=self.events,clock=self.clock,sleep=self.clock.sleep,**kwargs)
    def test_success_not_retried(self):
        op=Mock(return_value={'problem':None});self.invoke(op);self.assertEqual(op.call_count,1);self.assertEqual(self.events,[])
    def test_timeout_then_success(self):
        op=Mock(side_effect=[TimeoutError('temporary'),{'problem':None}]);self.invoke(op);self.assertEqual(op.call_count,2);self.assertTrue(self.events[0]['recovered'])
    def test_network_reset_retry(self):
        op=Mock(side_effect=[RuntimeError('net::ERR_CONNECTION_RESET'),{'problem':None}]);self.invoke(op);self.assertEqual(op.call_count,2)
    def test_http_server_retry(self):
        op=Mock(side_effect=[{'problem':'SEARCH_PROVIDER_FAILURE'},{'problem':None}]);self.invoke(op);self.assertTrue(self.events[0]['recovered'])
    def test_two_failures_stop(self):
        op=Mock(side_effect=TimeoutError('temporary'))
        with self.assertRaises(TimeoutError):self.invoke(op)
        self.assertEqual(op.call_count,2);self.assertFalse(self.events[0]['recovered'])
    def test_no_retry_for_access_restriction(self):
        for state in ['ACCESS_BLOCKED','RATE_LIMIT','LOGIN_REQUIRED','SOURCE_UNAVAILABLE']:
            op=Mock(return_value={'problem':state});self.invoke(op);self.assertEqual(op.call_count,1)
    def test_no_retry_for_parser_error(self):
        op=Mock(side_effect=ValueError('selector parser'))
        with self.assertRaises(ValueError):self.invoke(op)
        self.assertEqual(op.call_count,1)
    def test_no_retry_for_budget_error(self):
        op=Mock(side_effect=RunBudgetExceeded('budget'))
        with self.assertRaises(RunBudgetExceeded):self.invoke(op)
        self.assertEqual(op.call_count,1)
    def test_no_retry_when_budget_short(self):
        op=Mock(side_effect=TimeoutError('temporary'))
        with self.assertRaises(TimeoutError):self.invoke(op,deadline=8)
        self.assertEqual(op.call_count,1);self.assertEqual(self.events,[])
    def test_never_start_after_deadline(self):
        op=Mock()
        with self.assertRaises(RunBudgetExceeded):self.invoke(op,deadline=0)
        op.assert_not_called()
    def test_retry_limit_hard_cap(self):
        op=Mock(return_value={'problem':'SEARCH_PROVIDER_FAILURE'});self.invoke(op,cfg={'navigation_retries':99});self.assertEqual(op.call_count,2)
    def test_disabled_retry(self):
        op=Mock(return_value={'problem':'SEARCH_PROVIDER_FAILURE'});self.invoke(op,cfg={'navigation_retries':0});self.assertEqual(op.call_count,1)
    def test_browser_crash_restart_once(self):
        op=Mock(side_effect=[RuntimeError('Page crashed'),{'problem':None}]);reset=Mock();self.invoke(op,restart=reset);reset.assert_called_once();self.assertEqual(self.events[0]['action'],'restart browser')
    def test_timeout_does_not_restart_browser(self):
        op=Mock(side_effect=[TimeoutError(),{'problem':None}]);reset=Mock();self.invoke(op,restart=reset);reset.assert_not_called()
    def test_retry_can_find_access_block_and_stop(self):
        op=Mock(side_effect=[{'problem':'SEARCH_PROVIDER_FAILURE'},{'problem':'ACCESS_BLOCKED'}]);self.assertEqual(self.invoke(op)['problem'],'ACCESS_BLOCKED');self.assertFalse(self.events[0]['recovered'])
    def test_goto_timeout_respects_remaining(self):self.assertEqual(remaining_ms(5,40000,self.clock),5000)

class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.execute('create table app_settings(key text primary key,value text)');self.at=datetime.now(timezone.utc)
    def tearDown(self):self.c.close()
    def status(self,state='SEARCH_PROVIDER_FAILURE',term='n100',market='vinted',**kwargs):
        result=dict(marketplace=market,source='authorized_browser' if market=='vinted' else 'skelbiu',state=state)
        if term:result['search_term']=term
        result.update(kwargs);return result
    def update(self,status):return update_health(self.c,status,at=self.at)
    def test_single_transient_failure_quiet(self):self.assertEqual(self.update([self.status()]),[])
    def test_persistent_alert_after_three(self):
        self.update([self.status()]);self.update([self.status()]);events=self.update([self.status()]);self.assertEqual(events[0]['event'],'persistent_failure')
    def test_dedup_long_outage(self):
        events=[]
        for _ in range(8):events.extend(self.update([self.status()]))
        self.assertEqual(len(events),1)
    def test_recovery_notifies_once(self):
        for _ in range(3):self.update([self.status()])
        success=self.status('AUTHORIZED_BROWSER_CHECK');self.assertEqual(self.update([success])[0]['event'],'recovered');self.assertEqual(self.update([success]),[])
    def test_no_recovery_spam_for_unalerted_error(self):
        self.update([self.status()]);self.assertEqual(self.update([self.status('AUTHORIZED_BROWSER_CHECK')]),[])
    def test_unrelated_term_does_not_resolve(self):
        for _ in range(3):self.update([self.status()])
        self.assertEqual(self.update([self.status('AUTHORIZED_BROWSER_CHECK','n150')]),[]);state=json.loads(self.c.execute('select value from app_settings').fetchone()[0]);self.assertTrue(state['alert_open'])
    def test_disabled_source_does_not_resolve(self):
        for _ in range(3):self.update([self.status()])
        self.assertEqual(self.update([self.status('DISABLED')]),[]);self.assertTrue(json.loads(self.c.execute('select value from app_settings').fetchone()[0])['alert_open'])
    def test_blocked_source_alerts_immediately(self):self.assertEqual(self.update([self.status('ACCESS_BLOCKED')])[0]['event'],'persistent_failure')
    def test_marketplaces_independent(self):
        for _ in range(3):events=self.update([self.status(),self.status('AUTHORIZED_BROWSER_CHECK',market='skelbiu')])
        self.assertEqual([e['marketplace'] for e in events],['vinted'])
    def test_failed_term_reset_by_actual_success(self):
        self.update([self.status()]);self.update([self.status('AUTHORIZED_BROWSER_CHECK')]);self.assertEqual(self.update([self.status()]),[])
    def test_detail_needs_same_detail_success(self):
        bad=self.status(term=None,query='https://www.vinted.lt/items/123-mini')
        for _ in range(3):self.update([bad])
        self.assertEqual(self.update([self.status('AUTHORIZED_BROWSER_CHECK')]),[])
        self.assertEqual(self.update([self.status('AUTHORIZED_BROWSER_CHECK',detail_success_ids=['vinted:123'])])[0]['event'],'recovered')
    def test_source_wide_error_can_recover(self):
        for _ in range(3):self.update([self.status(term=None)])
        self.assertEqual(self.update([self.status('AUTHORIZED_BROWSER_CHECK')])[0]['event'],'recovered')
    def test_multiple_pending_terms_all_must_recover(self):
        for _ in range(3):self.update([self.status(),self.status(term='n150')])
        self.assertEqual(self.update([self.status('AUTHORIZED_BROWSER_CHECK')]),[]);self.assertEqual(self.update([self.status('AUTHORIZED_BROWSER_CHECK','n150')])[0]['event'],'recovered')
    def test_transaction_rollback_preserves_alert_eligibility(self):
        self.update([self.status()]);self.update([self.status()]);self.c.commit()
        with self.assertRaises(RuntimeError):
            with self.c:self.update([self.status()]);raise RuntimeError('outbox insert failed')
        self.assertEqual(self.update([self.status()])[0]['event'],'persistent_failure')
    def test_restart_persists_incident_state(self):
        for _ in range(3):self.update([self.status()])
        # State is entirely serializable, rather than an in-memory retry flag.
        state=self.c.execute('select key,value from app_settings').fetchone();other=sqlite3.connect(':memory:');other.execute('create table app_settings(key text primary key,value text)');other.execute('insert into app_settings values(?,?)',state)
        self.assertEqual(update_health(other,[self.status('AUTHORIZED_BROWSER_CHECK')],at=self.at)[0]['event'],'recovered');other.close()
    def test_message_omits_raw_error(self):
        events=self.update([self.status('ACCESS_BLOCKED',error='sensitive diagnostic should remain local')]);body=format_health(events);self.assertNotIn('sensitive diagnostic',body);self.assertIn('no automatic bypass',body)

class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=m.ROOT;m.ROOT=Path(self.temp.name);self.env=patch.dict(os.environ,{'DATABASE_PATH':str(m.ROOT/'state.sqlite'),'ENABLE_TELEGRAM':'false','NOTIFY_MODE':'deals_and_daily'});self.env.start();self.c=m.db()
    def tearDown(self):self.c.close();self.env.stop();m.ROOT=self.old;self.temp.cleanup()
    def check(self,status):
        with patch.object(m,'sources',return_value=([],[status],[])),contextlib.redirect_stdout(io.StringIO()):m.check()
    def test_incident_and_recovery_use_persistent_outbox(self):
        bad=dict(source='authorized_browser',search_term='n100',state='SEARCH_PROVIDER_FAILURE')
        for _ in range(4):self.check(bad)
        self.check(dict(source='authorized_browser',search_term='n100',state='AUTHORIZED_BROWSER_CHECK'))
        pending=self.c.execute("select body from outbox where state='PENDING' order by rowid").fetchall();self.assertEqual(len(pending),2);self.assertIn('PERSISTENT SOURCE FAILURE',pending[0][0]);self.assertIn('SOURCE RECOVERED',pending[1][0])
        self.assertEqual(self.c.execute('select count(*) from listings').fetchone()[0],0)

class AdapterRecoveryTests(unittest.TestCase):
    def exercise(self,market,blocked=False):
        import sys,types
        from contextlib import ExitStack,nullcontext
        import browser_source,skelbiu_source
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory);config=root/'config';config.mkdir();(config/'direct-authorization.json').write_text('{}')
            (config/'browser.json').write_text(json.dumps({'markets':['lt'],'queries':['N100'],'rotating_queries':[],'max_details':0}))
            (config/'skelbiu.json').write_text(json.dumps({'frequent_queries':['n100'],'rotating_queries':[],'max_details':0}))
            c=sqlite3.connect(':memory:');c.execute('create table app_settings(key text primary key,value text)');c.execute('create table listings(id text,current_json text)')
            history=[];pages=[]
            class Locator:
                def __init__(self,page,selector):self.page=page;self.selector=selector
                def inner_text(self,**kw):self.page.body_reads+=1;return 'No results found\nPagal Jūsų paiešką nieko neradome'
                def count(self):return 0
                def evaluate_all(self,*a):return []
            class Page:
                def __init__(self,index):self.index=index;self.url='';self.body_reads=0
                def goto(self,url,**kw):
                    self.url=url
                    if self.index==1 and not blocked:raise RuntimeError('Page crashed')
                    return types.SimpleNamespace(status=403 if blocked else 200)
                def locator(self,selector):return Locator(self,selector)
                def get_by_role(self,*args,**kw):return Locator(self,'button')
                def wait_for_timeout(self,*a):pass
                def screenshot(self,**kw):pass
                def content(self):return '<html></html>'
            class Browser:
                def __init__(self,index):self.index=index
                def new_page(self):p=Page(self.index);pages.append(p);return p
                def close(self):history.append('close'+str(self.index))
            def launch(**kw):
                index=1+sum(x.startswith('open') for x in history);history.append('open'+str(index));return Browser(index)
            p=types.SimpleNamespace(chromium=types.SimpleNamespace(launch=launch));fake=types.ModuleType('playwright.sync_api');fake.sync_playwright=lambda:nullcontext(p)
            stack.enter_context(patch.dict(sys.modules,{'playwright':types.ModuleType('playwright'),'playwright.sync_api':fake}))
            stack.enter_context(patch.object(browser_source,'display',lambda:nullcontext()));stack.enter_context(patch.object(skelbiu_source,'display',lambda:nullcontext()));stack.enter_context(patch('time.sleep',lambda _:None))
            # Override only the test delay; production retains its configured backoff.
            import recovery
            stack.enter_context(patch.object(recovery,'fetch',lambda operation,deadline,cfg,restart,events:fetch(operation,deadline,cfg,restart,events,sleep=lambda _:None)))
            adapter=browser_source if market=='vinted' else skelbiu_source
            records,statuses=adapter.collect(root,lambda *a:None,c,config)
            if blocked:
                self.assertEqual(statuses[-1]['state'],'ACCESS_BLOCKED');self.assertEqual(history,['open1','close1']);self.assertEqual(pages[0].body_reads,0);self.assertTrue((root/('browser-access-paused.json' if market=='vinted' else 'skelbiu-access-paused.json')).exists())
            else:
                self.assertEqual(statuses[-1]['state'],'NO_USABLE_RESULTS');self.assertEqual(history,['open1','close1','open2','close2']);self.assertTrue(statuses[-1]['navigation_retry_events'][0]['recovered'])
            self.assertEqual(records,[]);c.close()
    def test_vinted_crash_restarts_before_extraction(self):self.exercise('vinted')
    def test_skelbiu_crash_restarts_before_extraction(self):self.exercise('skelbiu')
    def test_vinted_http_block_never_retries(self):self.exercise('vinted',True)
    def test_skelbiu_http_block_never_retries(self):self.exercise('skelbiu',True)
