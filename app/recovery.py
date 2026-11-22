"""Bounded ordinary-public-page recovery; access restrictions are never retried."""
import json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit

class RunBudgetExceeded(TimeoutError):pass

def settings(config_dir=Path('/config')):
    p=config_dir/'recovery.json';return json.loads(p.read_text()) if p.exists() else {}

def remaining_ms(deadline,cap=40000,clock=time.monotonic):
    left=int((deadline-clock())*1000)
    if left<1000:raise RunBudgetExceeded('Browser run time budget exhausted')
    return min(cap,left)

def crash(exc):
    return type(exc).__name__=='TargetClosedError' or bool(re.search(r'page crashed|target page, context or browser has been closed|browser has been closed',str(exc),re.I))

def transient(exc):
    if isinstance(exc,RunBudgetExceeded):return False
    return isinstance(exc,ConnectionError) or type(exc).__name__=='TimeoutError' or crash(exc) or bool(re.search(r'net::ERR_(?:TIMED_OUT|CONNECTION_RESET|CONNECTION_CLOSED|CONNECTION_REFUSED|INTERNET_DISCONNECTED|NAME_NOT_RESOLVED|NETWORK_CHANGED)',str(exc)))

def fetch(operation,deadline,cfg=None,restart=None,events=None,clock=time.monotonic,sleep=time.sleep):
    """One bounded retry by default, sharing the original marketplace deadline."""
    cfg=cfg or {};limit=min(1,max(0,int(cfg.get('navigation_retries',1))));delay=min(15,max(3,float(cfg.get('retry_delay_seconds',5))))
    events=events if events is not None else [];last=None
    for attempt in range(limit+1):
        remaining_ms(deadline,clock=clock)
        error=None
        try:
            result=operation()
            retry=result.get('problem')=='SEARCH_PROVIDER_FAILURE'
            reason='temporary server error';reset=False
            if not retry:
                if last is not None:last['recovered']=result.get('problem') is None
                return result
        except Exception as exc:
            if not transient(exc):raise
            error=exc;reason='browser crash' if crash(exc) else 'navigation timeout' if type(exc).__name__=='TimeoutError' else 'network error';reset=crash(exc)
        if attempt>=limit or deadline-clock()<delay+5:
            if error is not None:raise error
            return result
        last={'reason':reason,'action':'restart browser' if reset else 'retry navigation','recovered':False};events.append(last)
        sleep(delay)
        remaining_ms(deadline,clock=clock)
        if reset and restart is not None:restart()
    raise AssertionError('Unreachable retry loop')

FAILURES={'ACCESS_BLOCKED','LOGIN_REQUIRED','RATE_LIMIT','UNAVAILABLE','PARSING_FAILURE','PARTIAL_CHECK','SEARCH_PROVIDER_FAILURE','SOURCE_UNAVAILABLE'}
BLOCKED={'ACCESS_BLOCKED','LOGIN_REQUIRED','RATE_LIMIT'}
SUCCESS={'AUTHORIZED_BROWSER_CHECK','NO_USABLE_RESULTS'}

def marketplace(status):
    if status.get('marketplace') in {'vinted','skelbiu'}:return status['marketplace']
    source=status.get('source','')
    return 'vinted' if source.startswith('authorized_browser') else 'skelbiu' if source=='skelbiu' else None

def clean(value):return re.sub(r'[^\w :.-]','',str(value))[:80]

def scope(status):
    if status.get('search_term'):return 'search:'+clean(status['search_term']).casefold()
    path=urlsplit(status.get('query','')).path
    ident=re.search(r'/items/(\d+)',path) or re.search(r'-(\d+)\.html$',path)
    return 'detail:'+ident[1] if ident else 'source'

def update_health(c,statuses,cfg=None,at=None):
    """Persist lifecycle state in caller transaction; emit one alert/recovery per episode.

    Omitted rotating terms, disabled adapters and successful unrelated queries do
    not falsely resolve an incident. Detail failures require that detail to succeed.
    """
    cfg=cfg or {};at=at or datetime.now(timezone.utc);threshold=max(2,int(cfg.get('persistent_failure_checks',3)));events=[]
    for market in ('vinted','skelbiu'):
        selected=[s for s in statuses if marketplace(s)==market and s['state']!='DISABLED']
        if not selected:continue
        key='failure_watch:'+market;row=c.execute('SELECT value FROM app_settings WHERE key=?',(key,)).fetchone();state=json.loads(row[0]) if row else {'issues':{},'alert_open':False};issues=state['issues']
        failed={scope(s):s for s in selected if s['state'] in FAILURES}
        succeeded={'search:'+clean(s['search_term']).casefold() for s in selected if s['state'] in SUCCESS and s.get('search_term')}
        succeeded.update('detail:'+str(i).split(':')[-1] for s in selected for i in s.get('detail_success_ids',[]))
        if not failed and any(s['state'] in SUCCESS for s in selected):succeeded.add('source')
        for name in succeeded-set(failed):issues.pop(name,None)
        for name,s in failed.items():
            old=issues.get(name,{})
            issues[name]={'failures':old.get('failures',0)+1,'first_failure':old.get('first_failure',at.isoformat()),'last_failure':at.isoformat(),'state':s['state'],'operator_review':s['state'] in BLOCKED}
        if issues and not state['alert_open'] and any(x['failures']>=threshold or x['operator_review'] for x in issues.values()):
            events.append({'event':'persistent_failure','marketplace':market,'issues':dict(issues),'at':at.isoformat()});state['alert_open']=True;state['alerted_at']=at.isoformat()
        elif not issues and state['alert_open']:
            events.append({'event':'recovered','marketplace':market,'at':at.isoformat(),'alerted_at':state.get('alerted_at')});state['alert_open']=False
        state['updated_at']=at.isoformat()
        c.execute('INSERT OR REPLACE INTO app_settings VALUES(?,?)',(key,json.dumps(state,sort_keys=True)))
    return events

def format_health(events):
    parts=[]
    for event in events:
        market=event['marketplace'];title=('SOURCE ACCESS PAUSED' if any(x.get('operator_review') for x in event.get('issues',{}).values()) else 'PERSISTENT SOURCE FAILURE') if event['event']=='persistent_failure' else 'SOURCE RECOVERED'
        lines=['MINI PC WATCHER — '+title,'Marketplace: '+market.title()+'.lt','Observed: '+event['at']]
        if event['event']=='persistent_failure':
            for name,issue in sorted(event['issues'].items())[:6]:lines.append(clean(name)+': '+issue['state']+f' ({issue["failures"]} failed checks; first {issue["first_failure"]})')
            if len(event['issues'])>6:lines.append(f'Additional affected checks: {len(event["issues"])-6}')
            blocked=any(x['operator_review'] for x in event['issues'].values())
            lines.append('Action: access restriction pauses this source. Review saved evidence and access authorization before manually resuming; no automatic bypass.' if blocked else 'Action: temporary navigation/server failures receive a bounded retry. Check saved diagnostics if failures persist; parser errors need a parser fix, not repeated requests.')
            lines.append('Other marketplace checks continue. Failed access is not zero listings or sold stock.')
        else:lines.append('Previously alerted checks have now succeeded. This confirms access/extraction recovery, not listing availability or delivery.')
        parts.append('\n'.join(lines))
    return '\n\n'.join(parts)
