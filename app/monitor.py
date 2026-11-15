"""Mini PC monitor with imports, indexed discovery and explicitly authorized browser access."""
import argparse, tempfile, csv, fcntl, hashlib, html, io, json, os, re, sqlite3, sys, time, uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

UTC=timezone.utc
ROOT=Path(os.getenv('STATE_DIR','/state'))
def now(): return datetime.now(UTC).isoformat()
def envbool(k): return os.getenv(k,'false').lower()=='true'
def zone(): return ZoneInfo(os.getenv('TIMEZONE','Europe/Vilnius'))
def slots():
    value=os.getenv('SCHEDULE','hourly').strip()
    if value.lower()=='hourly': return [f'{h:02d}:00' for h in range(24)]
    if value.lower()=='half_hourly': return [f'{h:02d}:{minute:02d}' for h in range(24) for minute in (0,30)]
    result=sorted(set(v.strip() for v in value.split(',')))
    for value in result:
        datetime.strptime(value,'%H:%M')
    return result

def next_slot(at,times):
    # Iterate real UTC minutes so nonexistent local hours are skipped and repeated
    # DST hours both execute once, distinguished by their UTC offset.
    at=at.astimezone(UTC)
    candidate=at.replace(second=0,microsecond=0)+timedelta(minutes=1)
    for _ in range(3*24*60):
        local=candidate.astimezone(zone())
        if local.strftime('%H:%M') in times: return local
        candidate+=timedelta(minutes=1)
    raise ValueError('No schedule slot within three days')

def next_run(at=None):
    return next_slot(at or datetime.now(UTC),set(slots()))

def next_daily_report(at=None):
    return next_slot(at or datetime.now(UTC),{os.getenv('DAILY_REPORT_TIME','19:00')})

def next_event(at):
    check_at=next_run(at); summary_at=next_daily_report(at)
    due=min(check_at,summary_at,key=lambda d:d.astimezone(UTC))
    return due,check_at.astimezone(UTC)==due.astimezone(UTC),summary_at.astimezone(UTC)==due.astimezone(UTC)

def should_notify(events):
    if os.getenv('NOTIFY_MODE','deals_and_daily')=='every_check': return True
    return bool(events)

def db():
    ROOT.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(os.getenv('DATABASE_PATH',str(ROOT/'watcher.sqlite')),timeout=30)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA foreign_keys=ON')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY);
    INSERT OR IGNORE INTO migrations VALUES(1);
    CREATE TABLE IF NOT EXISTS listings(id TEXT PRIMARY KEY,url TEXT NOT NULL,first_seen TEXT,last_seen TEXT,current_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS listing_observations(id INTEGER PRIMARY KEY,listing_id TEXT REFERENCES listings(id),observed_at TEXT,source TEXT,digest TEXT UNIQUE,body TEXT);
    CREATE INDEX IF NOT EXISTS observation_listing ON listing_observations(listing_id,observed_at);
    CREATE TABLE IF NOT EXISTS price_history(id INTEGER PRIMARY KEY,listing_id TEXT REFERENCES listings(id),observed_at TEXT,amount TEXT,currency TEXT,eur TEXT,source TEXT);
    CREATE INDEX IF NOT EXISTS price_listing ON price_history(listing_id,observed_at);
    CREATE TABLE IF NOT EXISTS availability_history(id INTEGER PRIMARY KEY,listing_id TEXT REFERENCES listings(id),observed_at TEXT,state TEXT);
    CREATE TABLE IF NOT EXISTS search_runs(id TEXT PRIMARY KEY,started TEXT,completed TEXT,kind TEXT,slot TEXT UNIQUE,outcome TEXT,counts TEXT,sources TEXT,report TEXT);
    CREATE TABLE IF NOT EXISTS source_health(source TEXT PRIMARY KEY,last_attempt TEXT,last_success TEXT,state TEXT,detail TEXT);
    CREATE TABLE IF NOT EXISTS alerts_sent(event_id TEXT PRIMARY KEY,listing_id TEXT,event TEXT,run_id TEXT,delivered_at TEXT);
    CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY REFERENCES search_runs(id),body TEXT,state TEXT,attempts INTEGER DEFAULT 0,next_attempt REAL DEFAULT 0,error TEXT);
    CREATE TABLE IF NOT EXISTS outbox_parts(run_id TEXT,part INTEGER,message_id TEXT,PRIMARY KEY(run_id,part));
    CREATE TABLE IF NOT EXISTS currency_rates(date TEXT,currency TEXT,rate TEXT,source TEXT,PRIMARY KEY(date,currency));
    CREATE TABLE IF NOT EXISTS shipping_estimates(listing_id TEXT,observed_at TEXT,body TEXT);
    CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT);
    ''')
    return c

def request_json(url,headers=None):
    with urlopen(Request(url,headers=headers or {}),timeout=25) as r: return json.load(r)

def rates_refresh(c):
    url='https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'
    with urlopen(url,timeout=25) as r: tree=ET.fromstring(r.read())
    for el in tree.iter():
        if 'time' in el.attrib: date=el.attrib['time']
        if 'currency' in el.attrib: c.execute('INSERT OR REPLACE INTO currency_rates VALUES(?,?,?,?)',(date,el.attrib['currency'],el.attrib['rate'],url))
    c.commit()

def eur(c,amount,currency):
    if amount is None or amount=='': return None,None
    a=Decimal(str(amount)); currency=currency.upper()
    if a<0 or not a.is_finite(): raise ValueError('invalid monetary amount')
    if currency=='EUR': return float(a),{'date':None,'source':'EUR'}
    row=c.execute('SELECT * FROM currency_rates WHERE currency=? ORDER BY date DESC LIMIT 1',(currency,)).fetchone()
    if not row or (datetime.now(UTC).date()-datetime.fromisoformat(row['date']).date()).days>7: return None,None
    return float(a/Decimal(row['rate'])),dict(row)

def specs(text):
    t=text.lower().replace('×','x')
    cpus=set(re.findall(r'\bn\s*[- ]?(100|150|97)\b',t))
    cpu='N'+next(iter(cpus)) if len(cpus)==1 else None
    if re.search(r'\b(charger|compatible with|power supply|chargeur|ladegerät)\b',t) and not re.search(r'\b(mini\s*(pc|computer)|komputer|ordinateur|rechner)\b',t): cpu=None
    # Remove capacity claims before looking for installed memory; avoid storage units.
    clean=re.sub(r'(supports?(?:\s+up\s+to)?|up to|max(?:imum)?|jusqu[’\x27]?à|bis zu|iki)\s*\d+\s*(?:gb|go|гб|gib)', '',t)
    unit=r'(?:gb|go|гб|gib)'
    clean=re.sub(r'\b\d+\s*'+unit+r'\s*(?:maximum|max\b|supported|supportés)', '',clean)
    pairs=re.findall(r'\b([124])\s*x\s*(\d+)\s*'+unit,clean)
    values=[int(a)*int(b) for a,b in pairs]
    clean=re.sub(r'\b[124]\s*x\s*\d+\s*'+unit,'',clean)
    for m in re.finditer(r'\b(4|8|16|24|32|48|64)\s*'+unit+r'\b',clean):
        tail=clean[m.end():m.end()+15]
        if not re.match(r'\s*(ssd|emmc|storage|disk|flash)',tail): values.append(int(m[1]))
    ram=values[0] if values and len(set(values))==1 else None
    if ram is not None and ram<int(os.getenv('MIN_RAM_GB','16')): cls='REJECTED'
    elif cpu not in os.getenv('ALLOWED_CPUS','N100,N150,N97').split(',') or ram is None: cls='NEEDS_MANUAL_REVIEW'
    else: cls='LIKELY_MATCH_UNVERIFIED'
    return cpu,ram,cls

STATES={'AVAILABLE_CONFIRMED','SOLD','RESERVED','PURCHASE_IN_PROGRESS','REMOVED','UNKNOWN','ACCESS_BLOCKED'}
DEAD={'SOLD','RESERVED','PURCHASE_IN_PROGRESS','REMOVED'}

def normalize(c,r,source):
    u=urlsplit(r.get('url',''))
    if u.scheme!='https' or not re.fullmatch(r'(?:www\.)?vinted\.(?:lt|pl|de|fr|nl|lv|ee|it|es|cz|com|co.uk|be|at|pt|fi|se|dk)',u.hostname or ''): raise ValueError('expected direct HTTPS Vinted listing URL')
    match=re.match(r'/items/(\d+)(?:-|/|$)',u.path)
    if not match: raise ValueError('URL lacks numeric listing identity')
    ident='vinted:'+match[1]
    title=str(r.get('title','')); description=str(r.get('description',''))
    cpu,ram,cls=specs(title+' '+description)
    if re.search(r'\b(charger|cable|power supply|chargeur|ladegerät)\b',title.lower()) and not re.search(r'\b(mini\s*pc|computer|komputer|ordinateur|rechner)\b',title.lower()):
        cpu=None; cls='REJECTED'
    if re.search(r'\b(nokia|oneplus|smartphone|smartfon|laptop|notebook|chromebook|gemibook|ideapad|vivobook|thinkpad|aspire|latitude|elitebook|probook|netbook|portable|nolan)\b',title.lower()): cls='REJECTED'
    if re.search(r'(?:samsung\s+n150|lenovo\s+3000)',title.lower()): cls='REJECTED'
    stamp=r.get('observed_at') or now()
    ts=datetime.fromisoformat(stamp)
    if ts.tzinfo is None or ts>datetime.now(UTC)+timedelta(minutes=5): raise ValueError('observed_at must be timezone aware and not future')
    manual=source=='manual_import' or (source=='authorized_browser_detail' and envbool('ENABLE_AUTHORIZED_DIRECT_CHECKS'))
    trusted=manual and r.get('evidence_source') and r.get('details_confirmed') in (True,'true')
    fresh=(datetime.now(UTC)-ts.astimezone(UTC)).total_seconds()<int(os.getenv('VERIFICATION_TTL_HOURS','24'))*3600
    availability=r.get('availability','UNKNOWN') if manual else 'UNKNOWN'
    if availability not in STATES: raise ValueError('invalid availability state')
    delivery=r.get('delivery','UNKNOWN') if manual else 'UNKNOWN'
    if delivery not in {'UNKNOWN','DIRECT_LT_CONFIRMED','FORWARDER_CONFIRMED','COLLECTION_ONLY','INELIGIBLE'}: raise ValueError('invalid delivery')
    if not r.get('availability_evidence') or not fresh: availability='UNKNOWN' if availability=='AVAILABLE_CONFIRMED' else availability
    if not r.get('delivery_evidence') or not fresh: delivery='UNKNOWN' if delivery.endswith('CONFIRMED') else delivery
    if cls=='LIKELY_MATCH_UNVERIFIED' and trusted and fresh: cls='VERIFIED_MATCH'
    if delivery in {'COLLECTION_ONLY','INELIGIBLE'}: cls='REJECTED'
    currency=r.get('currency','EUR').upper()
    amount=r.get('price'); amount=None if amount in ('',None) else str(Decimal(str(amount)))
    converted,fx=eur(c,amount,currency)
    if converted is not None and converted>float(os.getenv('MAX_ASKING_PRICE_EUR',os.getenv('TARGET_PRICE_EUR','175'))): cls='REJECTED'
    components=[]
    required=['buyer_fee','seller_shipping']
    if delivery=='FORWARDER_CONFIRMED' or r.get('route')=='forwarder': required+=['forwarding','local_delivery']
    required+=['additional_charges']
    for key in required:
        p=r.get('costs',{}).get(key,{})
        valid=p.get('source') and p.get('timestamp') and p.get('status') in {'confirmed','estimated'}
        if valid:
            part_ts=datetime.fromisoformat(p['timestamp'])
            valid=part_ts.tzinfo is not None and part_ts<=datetime.now(UTC)+timedelta(minutes=5)
        a=p.get('amount') if valid else None
        v,rate=eur(c,a,p.get('currency','EUR'))
        components.append(dict(name=key,amount=a,currency=p.get('currency','EUR'),eur=v,source=p.get('source'),timestamp=p.get('timestamp'),status=p.get('status','UNKNOWN'),fx=rate))
    complete=converted is not None and all(p['eur'] is not None for p in components)
    total=round(converted+sum(p['eur'] or 0 for p in components),2) if converted is not None else None
    risks=[]
    if converted is not None and converted<50: risks.append('Unusually low asking price; inspect listing carefully')
    if re.search(r'(no|without|sans|ohne)\s+(power|ac|adapter|chargeur|netzteil)',description.lower()): risks.append('Power adapter may be missing')
    if not complete: risks.append('Delivered total incomplete: unknown charges are not zero')
    tier=None
    if complete:
        for threshold in map(float,os.getenv('PRIORITY_THRESHOLDS','75,100,125,150,175').split(',')):
            if total<threshold: tier=f'Below EUR {threshold:g} (estimate)'; break
    return dict(id=ident,url=f'https://{u.hostname}{u.path}',country=r.get('country',u.hostname.split('.')[-1].upper()),title=title,description=description,cpu=cpu,ram_gb=ram,classification=cls,availability=availability,delivery=delivery,price=amount,currency=currency,asking_eur=converted,fx=fx,costs=components,delivered_eur=total,cost_complete=complete,tier=tier,risks=risks,source=source,evidence_source=r.get('evidence_source',source),observed_at=stamp,details_confirmed=bool(trusted),price_basis='MARKET_DISPLAY' if source.startswith('authorized_browser') else 'SELLER_SUPPLIED',seller_country=r.get('seller_country'),condition=r.get('condition','UNKNOWN'),model=r.get('model'),manufacturer=r.get('manufacturer'),storage=r.get('storage','UNKNOWN'),power_adapter=r.get('power_adapter','UNKNOWN'))

def in_buyer_scope(r):
    buyer=os.getenv('BUYER_MARKET','').strip().upper()
    if not buyer: return True
    allowed={v.strip().upper() for v in os.getenv('ALLOWED_SELLER_COUNTRIES','LT,PL,FI,LV,EE').split(',')}
    seller=r.get('seller_country') or (r.get('country') if r['source']=='manual_import' else None)
    if seller and seller.upper() not in allowed: return False
    # Foreign public catalogues expose routes unavailable to the Lithuanian account.
    # A source-domain country is NOT proof of the seller's physical location.
    if r['source']!='manual_import':
        return (urlsplit(r['url']).hostname or '').removeprefix('www.')=='vinted.'+buyer.lower()
    return True

def confirmed(r):
    fresh=(datetime.now(UTC)-datetime.fromisoformat(r['observed_at'])).total_seconds()<int(os.getenv('VERIFICATION_TTL_HOURS','24'))*3600
    return in_buyer_scope(r) and fresh and r['classification']=='VERIFIED_MATCH' and r['availability']=='AVAILABLE_CONFIRMED' and r['delivery'] in {'DIRECT_LT_CONFIRMED','FORWARDER_CONFIRMED'}

def observe(c,r,run_id):
    old=c.execute('SELECT * FROM listings WHERE id=?',(r['id'],)).fetchone()
    prev=json.loads(old['current_json']) if old else None
    if prev and datetime.fromisoformat(r['observed_at'])<datetime.fromisoformat(prev['observed_at']): return 'NO_CHANGE',None
    # Search cards/unknown status cannot revive a confirmed sold/reserved listing.
    if prev and prev['availability'] in DEAD and r['availability']=='UNKNOWN':
        r['availability']=prev['availability']
    body=json.dumps(r,sort_keys=True); digest=hashlib.sha256(body.encode()).hexdigest()
    if c.execute('SELECT 1 FROM listing_observations WHERE digest=?',(digest,)).fetchone(): return 'NO_CHANGE',None
    event='NO_CHANGE'
    if not prev: event='NEW_VERIFIED_MATCH' if confirmed(r) else 'NEW_UNVERIFIED_CANDIDATE'
    elif confirmed(r) and not confirmed(prev): event='NEW_VERIFIED_MATCH'
    elif r['source']==prev['source'] and r['price'] is not None and prev['price'] is not None and r['currency']==prev['currency']:
        if Decimal(r['price'])<Decimal(prev['price']): event='DISPLAY_PRICE_DECREASE_UNVERIFIED' if r.get('price_basis')=='MARKET_DISPLAY' or prev.get('price_basis')=='MARKET_DISPLAY' else 'PRICE_DROP'
        elif Decimal(r['price'])>Decimal(prev['price']): event='PRICE_INCREASE'
    if prev and prev['availability'] in DEAD and confirmed(r): event='RETURNED_TO_AVAILABLE'
    c.execute('INSERT INTO listings VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,current_json=excluded.current_json',(r['id'],r['url'],r['observed_at'],r['observed_at'],body))
    c.execute('INSERT INTO listing_observations(listing_id,observed_at,source,digest,body) VALUES(?,?,?,?,?)',(r['id'],r['observed_at'],r['source'],digest,body))
    if r['price'] is not None: c.execute('INSERT INTO price_history(listing_id,observed_at,amount,currency,eur,source) VALUES(?,?,?,?,?,?)',(r['id'],r['observed_at'],r['price'],r['currency'],r['asking_eur'],r['source']))
    if not prev or prev['availability']!=r['availability']: c.execute('INSERT INTO availability_history(listing_id,observed_at,state) VALUES(?,?,?)',(r['id'],r['observed_at'],r['availability']))
    c.execute('INSERT INTO shipping_estimates VALUES(?,?,?)',(r['id'],r['observed_at'],json.dumps(r['costs'])))
    eid=hashlib.sha256((r['id']+digest+event).encode()).hexdigest()
    eligible=in_buyer_scope(r) and r['classification']!='REJECTED' and r['availability'] not in DEAD
    if event!='NO_CHANGE' and eligible:
        c.execute('INSERT OR IGNORE INTO alerts_sent VALUES(?,?,?,?,NULL)',(eid,r['id'],event,run_id))
        return event,prev
    return 'NO_CHANGE',prev

def load_file(p):
    if p.suffix=='.json':
        v=json.loads(p.read_text()); return v if isinstance(v,list) else [v]
    if p.suffix=='.csv': return list(csv.DictReader(io.StringIO(p.read_text())))
    text=p.read_text(); urls=re.findall(r'https://(?:www\.)?vinted\.[a-z.]+/items/\d+[^\s]*',text)
    return [{'url':u,'description':text} for u in urls]

def health(c,source,state,detail):
    stamp=now()
    c.execute('INSERT INTO source_health VALUES(?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET last_attempt=excluded.last_attempt,last_success=COALESCE(excluded.last_success,source_health.last_success),state=excluded.state,detail=excluded.detail',(source,stamp,stamp if state=='OK' else None,state,detail))

QUERIES=['N100 mini PC','N100 16GB','N150 16GB','N97 16GB','Beelink N100','GMKtec N150','mini komputer N100','mini PC 16 Go N100','mini Rechner N100','mini ordinateur Intel N100','NiPoGi N97','Chuwi Larkbox','ACEMAGIC N150','MINISFORUM N100','Trigkey N100','Firebat N100','BMAX N100','Morefine N100','Topton N100','Kingnovy N100']

def sources(c):
    records=[]; statuses=[]; files=[]
    for p in sorted((ROOT/'inbox').glob('*')):
        if p.suffix not in {'.json','.csv','.txt'}: continue
        try:
            rows=load_file(p)
            normalized=[normalize(c,r,'manual_import') for r in rows]
            records+=normalized; files.append(p)
            statuses.append({'source':p.name,'state':'MANUAL_IMPORT','count':len(rows)})
        except Exception as e: statuses.append({'source':p.name,'state':'PARSING_FAILURE','error':type(e).__name__+': '+str(e)[:150]})
    health(c,'manual_import','PARSING_FAILURE' if any(s['state']=='PARSING_FAILURE' for s in statuses) else 'OK','Inbox read; '+str(len(records))+' observations')
    c.commit()
    key=os.getenv('BRAVE_API_KEY')
    if not key or not envbool('BRAVE_STORAGE_LICENSE_CONFIRMED'):
        statuses.append({'source':'brave','state':'DISABLED' if envbool('ENABLE_AUTHORIZED_DIRECT_CHECKS') else 'UNAVAILABLE','error':'API key and plan permitting result storage required'})
        health(c,'brave','DISABLED' if envbool('ENABLE_AUTHORIZED_DIRECT_CHECKS') else 'UNAVAILABLE','Not configured / storage license not confirmed')
    else:
        cfg=Path('/config/search.json')
        queries=json.loads(cfg.read_text()).get('queries',QUERIES) if cfg.exists() else QUERIES
        domains=[os.environ['BUYER_MARKET'].lower()] if os.getenv('BUYER_MARKET') else ['lt','pl','fi','lv','ee']
        for domain in domains:
            for query in queries:
                q=f'site:vinted.{domain}/items/ {query}'
                try:
                    result=request_json('https://api.search.brave.com/res/v1/web/search?'+urlencode({'q':q,'count':20}),{'X-Subscription-Token':key,'Accept':'application/json'})
                    count=0
                    for hit in result.get('web',{}).get('results',[]):
                        try:
                            records.append(normalize(c,{'url':hit['url'],'title':hit.get('title',''),'description':hit.get('description','')},'brave_index')); count+=1
                        except ValueError: pass
                    statuses.append({'source':'brave','query':q,'state':'INDEXED_DISCOVERY_ONLY','count':count}); health(c,'brave','OK',q)
                    time.sleep(float(os.getenv('SEARCH_INTERVAL_SECONDS','1.1')))
                except Exception as e:
                    code=getattr(e,'code',None)
                    state='RATE_LIMIT' if code==429 else 'ACCESS_BLOCKED' if code in {401,403} else 'SEARCH_PROVIDER_FAILURE'
                    statuses.append({'source':'brave','query':q,'state':state,'error':type(e).__name__}); health(c,'brave',state,type(e).__name__)
                    return records,statuses,files
    if envbool('ENABLE_AUTHORIZED_DIRECT_CHECKS'):
        c.commit()
        try:
            from browser_source import collect
            browser_records,browser_statuses=collect(ROOT,normalize,c)
            records+=browser_records; statuses+=browser_statuses
            failed=any(s['state'] in {'ACCESS_BLOCKED','LOGIN_REQUIRED','RATE_LIMIT','PARTIAL_CHECK','UNAVAILABLE','PARSING_FAILURE','SOURCE_UNAVAILABLE','SEARCH_PROVIDER_FAILURE'} for s in browser_statuses)
            health(c,'authorized_browser','PARTIAL_CHECK' if failed else 'OK',json.dumps(browser_statuses))
        except Exception as e:
            statuses.append({'source':'authorized_browser','state':'SEARCH_PROVIDER_FAILURE','error':type(e).__name__+': '+str(e)[:150]})
            health(c,'authorized_browser','FAILED',type(e).__name__)
    else:
        statuses.append({'source':'direct_vinted','state':'DISABLED','error':'Authorized browser access not enabled'})
    return records,statuses,files

def report(run_id,kind,statuses,records,events):
    counts={k:sum(r['classification']==k for r in records) for k in ['VERIFIED_MATCH','LIKELY_MATCH_UNVERIFIED','NEEDS_MANUAL_REVIEW','REJECTED']}
    states={s['state'] for s in statuses}
    outcome='PARTIAL_CHECK' if states & {'UNAVAILABLE','PARSING_FAILURE','RATE_LIMIT','ACCESS_BLOCKED','SEARCH_PROVIDER_FAILURE','LOGIN_REQUIRED','PARTIAL_CHECK','SOURCE_UNAVAILABLE'} else 'AUTHORIZED_BROWSER_CHECK' if 'AUTHORIZED_BROWSER_CHECK' in states else 'NO_USABLE_RESULTS' if 'NO_USABLE_RESULTS' in states else 'INDEXED_DISCOVERY_ONLY' if 'INDEXED_DISCOVERY_ONLY' in states else 'MANUAL_IMPORT'
    lines=[f'Vinted check — {datetime.now(zone()).isoformat(timespec="minutes")}',f'Run: {run_id} ({kind})',f'Outcome: {outcome}',f'Observed unique listings: {len(records)}; accepted specs: {counts["VERIFIED_MATCH"]}; likely: {counts["LIKELY_MATCH_UNVERIFIED"]}; manual review: {counts["NEEDS_MANUAL_REVIEW"]}; rejected: {counts["REJECTED"]}',f'Fully confirmed this run: {sum(confirmed(r) for r in records)}', ('Authorized public-browser access enabled; delivery unverified. Full live catalogue NOT searched.' if envbool('ENABLE_AUTHORIZED_DIRECT_CHECKS') else 'Direct Vinted verification: disabled. Full live catalogue NOT searched.')]
    if os.getenv('BUYER_MARKET'):
        lines.append('Buyer market: '+os.environ['BUYER_MARKET']+'; connected seller markets: '+os.getenv('ALLOWED_SELLER_COUNTRIES','LT,PL,FI,LV,EE')+' (mainland Finland). Delivery requires checkout verification.')
    groups={}
    for status in statuses:
        key=(status['source'],status['state']); group=groups.setdefault(key,{'count':0,'errors':set()})
        group['count']+=1
        if status.get('error'): group['errors'].add(status['error'])
    for (source,state),group in groups.items():
        lines.append(f'Source {source}: {state} ({group["count"]} checks)'+(' — '+'; '.join(sorted(group['errors'])) if group['errors'] else ''))
    if not events: lines.append('No new verified deals or comparable asking-price drops established. No fresh input does not mean no listings exist.')
    for section in (True,False):
        group=[(r,e,p) for r,e,p in events if confirmed(r)==section]
        if group: lines.append('\nCONFIRMED DEALS' if section else '\nUNVERIFIED CANDIDATES / EVENTS')
        for r,e,p in sorted(group,key=lambda x:(not x[0]['cost_complete'],x[0]['delivered_eur'] if x[0]['delivered_eur'] is not None else float('inf'))):
            lines += [f'{e}: {r["title"]}',f'{r["cpu"] or "CPU UNKNOWN"} / RAM {r["ram_gb"] or "UNKNOWN"} GB; source market {r["country"]}; {r["condition"]}',f'Asking: '+(f'EUR {r["asking_eur"]:.2f}' if r['asking_eur'] is not None else 'EUR UNKNOWN (conversion/price missing)'),f'Availability: {r["availability"]}; delivery: {r["delivery"]}']
            if r.get('price_basis')=='MARKET_DISPLAY': lines.append('Price shown by Vinted in this market; original seller currency unverified. FX changes may affect it.')
            if e=='DISPLAY_PRICE_DECREASE_UNVERIFIED': lines.append('Displayed price decreased; seller price reduction NOT established (currency conversion may have changed).')
            if e=='PRICE_DROP' and p:
                pct=(Decimal(p['price'])-Decimal(r['price']))/Decimal(p['price'])*100 if Decimal(p['price']) else 0
                lines.append(f'Comparable seller price decrease: {pct:.1f}% (same currency/source); previous EUR estimate {p["asking_eur"]}')
            for part in r['costs']: lines.append(f'{part["name"]}: '+(f'EUR {part["eur"]:.2f} ({part["status"]})' if part['eur'] is not None else 'UNKNOWN'))
            lines += [f'Delivered: EUR {r["delivered_eur"]} '+('estimate' if r['cost_complete'] else 'INCOMPLETE subtotal; unknown costs remain'),f'Evidence: {r["evidence_source"]}, {r["observed_at"]}', '; '.join(r['risks']),r['url']]
    lines += ['Telegram: '+('configured; delivery tracked in outbox' if envbool('ENABLE_TELEGRAM') and os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID') else 'UNAVAILABLE — report retained pending configuration'),f'Next scheduled: {next_run().isoformat()}']
    return '\n'.join(lines),counts,outcome

def flush(c):
    with (ROOT/'outbox.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return
        _flush(c)

def _flush(c):
    if not (envbool('ENABLE_TELEGRAM') and os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID')): return
    for row in c.execute("SELECT * FROM outbox WHERE state='PENDING' AND attempts<5 AND next_attempt<=?",(time.time(),)).fetchall():
        try:
            # Stable plain-text chunks; Telegram supports clickable raw URLs. Persist each confirmed part.
            chunks=[row['body'][i:i+3500] for i in range(0,len(row['body']),3500)]
            for i,chunk in enumerate(chunks):
                if c.execute('SELECT 1 FROM outbox_parts WHERE run_id=? AND part=?',(row['id'],i)).fetchone(): continue
                payload=json.dumps({'chat_id':os.environ['TELEGRAM_CHAT_ID'],'text':html.escape(chunk),'parse_mode':'HTML','link_preview_options':{'is_disabled':True}}).encode()
                url='https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/sendMessage'
                with urlopen(Request(url,data=payload,headers={'Content-Type':'application/json'}),timeout=20) as response: result=json.load(response)
                if not result.get('ok'): raise RuntimeError('Telegram rejected request')
                c.execute('INSERT INTO outbox_parts VALUES(?,?,?)',(row['id'],i,str(result['result']['message_id']))); c.commit()
            c.execute("UPDATE outbox SET state='DELIVERED',error=NULL WHERE id=?",(row['id'],))
            c.execute('UPDATE alerts_sent SET delivered_at=? WHERE run_id=?',(now(),row['id'])); c.commit()
        except Exception as e:
            # Never log request URLs: they contain the bot token.
            c.execute("UPDATE outbox SET state='PENDING',attempts=attempts+1,next_attempt=?,error=? WHERE id=?",(time.time()+min(3600,30*2**row['attempts']),type(e).__name__,row['id'])); c.commit()

def check(kind='manual',slot=None):
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/'execution.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return {'state':'BUSY'}
        c=db(); run_id=str(uuid.uuid4()); start=now()
        if slot and c.execute('SELECT 1 FROM search_runs WHERE slot=?',(slot,)).fetchone(): return {'state':'ALREADY_COMPLETED'}
        try: records,statuses,files=sources(c)
        except Exception as e:
            records,files=[],[]
            statuses=[{'source':'source_pipeline','state':'SEARCH_PROVIDER_FAILURE','error':type(e).__name__}]
        # Prefer manual evidence over indexed snippets for a shared identity.
        unique={}
        for r in records:
            if r['id'] not in unique or r['source']=='manual_import' or (r['source']=='authorized_browser_detail' and unique[r['id']]['source']!='manual_import'): unique[r['id']]=r
        records=list(unique.values()); events=[]
        with c:
            for r in records:
                old=c.execute('SELECT current_json FROM listings WHERE id=?',(r['id'],)).fetchone()
                if old and r['source']=='brave_index' and json.loads(old[0])['source']=='manual_import': continue
                e,p=observe(c,r,run_id)
                if e in {'NEW_VERIFIED_MATCH','NEW_UNVERIFIED_CANDIDATE','PRICE_DROP','DISPLAY_PRICE_DECREASE_UNVERIFIED','RETURNED_TO_AVAILABLE'}: events.append((r,e,p))
            body,counts,outcome=report(run_id,kind,statuses,records,events)
            c.execute('INSERT INTO search_runs VALUES(?,?,?,?,?,?,?,?,?)',(run_id,start,now(),kind,slot,outcome,json.dumps(counts),json.dumps(statuses),body))
            c.execute('INSERT INTO outbox(id,body,state) VALUES(?,?,?)',(run_id,body,'PENDING' if should_notify(events) else 'LOCAL_ONLY'))
        for p in files:
            target=ROOT/'processed'/f'{run_id}-{p.name}'; target.parent.mkdir(exist_ok=True); p.rename(target)
        flush(c)
        print(body,flush=True)
        c.close()
        return {'run_id':run_id,'outcome':outcome}

def daily_summary(c,slot):
    key='daily-summary:'+slot.isoformat()
    if c.execute('SELECT 1 FROM search_runs WHERE slot=?',(key,)).fetchone(): return {'state':'ALREADY_COMPLETED'}
    end=slot.astimezone(UTC)
    previous_date=slot.astimezone(zone()).date()-timedelta(days=1)
    h,m=map(int,os.getenv('DAILY_REPORT_TIME','19:00').split(':'))
    start=datetime(previous_date.year,previous_date.month,previous_date.day,h,m,tzinfo=zone()).astimezone(UTC)
    runs=c.execute("SELECT * FROM search_runs WHERE kind IN ('manual','scheduled','recovery') AND completed>=? AND completed<? ORDER BY completed",(start.isoformat(),end.isoformat())).fetchall()
    run_ids={r['id'] for r in runs}
    alerts=[dict(r) for r in c.execute('SELECT * FROM alerts_sent') if r['run_id'] in run_ids]
    new_ids={r['listing_id'] for r in alerts if r['event'] in {'NEW_VERIFIED_MATCH','NEW_UNVERIFIED_CANDIDATE'}}
    drops=sum(r['event']=='PRICE_DROP' for r in alerts)
    display_drops=sum(r['event']=='DISPLAY_PRICE_DECREASE_UNVERIFIED' for r in alerts)
    matches=[json.loads(r[0]) for r in c.execute('SELECT current_json FROM listings')]
    matches=[r for r in matches if in_buyer_scope(r) and r['classification']!='REJECTED' and r['availability'] not in DEAD]
    matches.sort(key=lambda r:(not confirmed(r),not r['cost_complete'],r['delivered_eur'] if r['delivered_eur'] is not None else float('inf')))
    last=c.execute("SELECT * FROM search_runs WHERE kind IN ('manual','scheduled','recovery') AND completed<? ORDER BY completed DESC LIMIT 1",(end.isoformat(),)).fetchone()
    sources=json.loads(last['sources']) if last else [{'source':'monitor','state':'UNAVAILABLE','error':'No completed checks before summary'}]
    run_id=str(uuid.uuid4())
    # A daily status report must not resend already alerted or stale listing details.
    events=[]
    details,counts,outcome=report(run_id,'daily_summary',sources,matches,events)
    body='\n'.join([f'DAILY MINI PC REPORT — {slot.astimezone(zone()).isoformat(timespec="minutes")}',f'Window: {start.astimezone(zone()).isoformat()} to {slot.isoformat()}',f'Checks completed: {len(runs)}; partial/failed: {sum(r["outcome"]=="PARTIAL_CHECK" for r in runs)}',f'New candidates: {len(new_ids)}; confirmed seller price drops: {drops}; unverified displayed-price decreases: {display_drops}',f'Current stored candidates: {len(matches)}; fully confirmed: {sum(confirmed(r) for r in matches)}','Stored candidate counts may be stale; unchanged listings are not sent again.','This summary uses completed checks before 19:00; the 19:00 check runs afterward.','',details])
    stamp=now()
    with c:
        c.execute('INSERT INTO search_runs VALUES(?,?,?,?,?,?,?,?,?)',(run_id,stamp,stamp,'daily_summary',key,outcome,json.dumps(counts),json.dumps(sources),body))
        c.execute('INSERT INTO outbox(id,body,state) VALUES(?,?,?)',(run_id,body,'PENDING'))
    flush(c)
    print(body,flush=True)
    return {'run_id':run_id}

def backup(c):
    dest=Path(os.getenv('BACKUP_DIR','/backups')); dest.mkdir(parents=True,exist_ok=True)
    p=dest/('watcher-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%S')+'.sqlite')
    target=sqlite3.connect(p); c.backup(target); result=target.execute('PRAGMA integrity_check').fetchone()[0]; target.close()
    if result!='ok': raise RuntimeError('Backup integrity failed')
    cutoff=time.time()-int(os.getenv('RETENTION_DAYS','180'))*86400
    for f in dest.glob('watcher-*.sqlite'):
        if f.stat().st_mtime<cutoff: f.unlink()
    return str(p)

def status(c):
    matches=[json.loads(r[0]) for r in c.execute('SELECT current_json FROM listings')]
    return dict(database_health=c.execute('PRAGMA quick_check').fetchone()[0],next_scheduled=next_run().isoformat(),last_scheduled=dict(r) if (r:=c.execute("SELECT id,started,completed,outcome,slot FROM search_runs WHERE kind='scheduled' ORDER BY started DESC LIMIT 1").fetchone()) else None,last_run=dict(r) if (r:=c.execute('SELECT id,started,completed,outcome FROM search_runs ORDER BY started DESC LIMIT 1').fetchone()) else None,sources=[dict(r) for r in c.execute('SELECT * FROM source_health')],last_telegram_report=dict(r) if (r:=c.execute("SELECT id FROM outbox WHERE state='DELIVERED' ORDER BY rowid DESC LIMIT 1").fetchone()) else None,outbox=[dict(r) for r in c.execute('SELECT id,state,attempts,error FROM outbox WHERE state="PENDING"')],notification_mode=os.getenv('NOTIFY_MODE','deals_and_daily'),telegram_enabled=envbool('ENABLE_TELEGRAM'),next_daily_report=next_daily_report().isoformat(),confirmed_deals=sum(confirmed(r) for r in matches),unverified_candidates=sum(in_buyer_scope(r) and r['classification']!='REJECTED' and not confirmed(r) and r['availability'] not in DEAD for r in matches),monitoring=not (ROOT/'disabled').exists(),heartbeat=(ROOT/'heartbeat').read_text() if (ROOT/'heartbeat').exists() else None)

def recover_hourly_gap(c,cursor,at):
    if os.getenv('SCHEDULE','hourly').lower() not in ('hourly','half_hourly'): return cursor
    first=next_run(cursor)
    if first.astimezone(UTC)>at: return cursor
    following=next_run(first.astimezone(UTC))
    if following.astimezone(UTC)>at: return cursor
    count=0; slot=first
    while slot.astimezone(UTC)<=at:
        count+=1; last=slot; slot=next_run(slot.astimezone(UTC))
    recovery={'from':cursor.isoformat(),'to':at.isoformat(),'missed_checks':count,'first_slot':first.isoformat(),'last_slot':last.isoformat(),'policy':'One fresh recovery check; missed scheduled browser checks are not replayed individually'}
    with c: c.execute("INSERT OR REPLACE INTO app_settings VALUES('last_schedule_recovery',?)",(json.dumps(recovery),))
    # Catch up at most the latest missed daily summary, then one fresh scan.
    summary=next_daily_report(cursor); latest=None
    while summary.astimezone(UTC)<=at:
        latest=summary; summary=next_daily_report(summary.astimezone(UTC))
    if latest: daily_summary(c,latest)
    (ROOT/'heartbeat').write_text(now())
    result=check('recovery')
    if result.get('state')=='BUSY': return cursor
    with c: c.execute("INSERT OR REPLACE INTO app_settings VALUES('scheduler_cursor',?)",(at.isoformat(),))
    print(json.dumps({'event':'missed_checks_coalesced',**recovery}),flush=True)
    return at

def daemon():
    # One scheduler leader per persistent state volume, even if a second container is started.
    leader=(ROOT/'scheduler.lock').open('a'); fcntl.flock(leader,fcntl.LOCK_EX|fcntl.LOCK_NB)
    c=db(); previous=c.execute("SELECT value FROM app_settings WHERE key='scheduler_cursor'").fetchone()
    cursor=datetime.fromisoformat(previous[0]) if previous else datetime.now(UTC)
    print(json.dumps({'event':'scheduler_start','cursor':cursor.isoformat(),'recovery':'missed scheduled checks coalesced; daily reports deduplicated; older gaps recorded'}),flush=True)
    if cursor<datetime.now(UTC)-timedelta(days=7):
        c.execute("INSERT OR REPLACE INTO app_settings VALUES('older_missed_gap',?)",(json.dumps({'from':cursor.isoformat(),'to':now()}),)); c.commit(); cursor=datetime.now(UTC)-timedelta(days=7)
    cursor=recover_hourly_gap(c,cursor,datetime.now(UTC))
    maintenance=None
    while True:
        at=datetime.now(UTC); (ROOT/'heartbeat').write_text(at.isoformat())
        if not (ROOT/'disabled').exists():
            due,check_due,summary_due=next_event(cursor)
            if due.astimezone(UTC)<=at:
                try:
                    if summary_due: daily_summary(c,due)
                    result=check('scheduled',due.isoformat()) if check_due else {'state':'SUMMARY_COMPLETED'}
                    if result.get('state')!='BUSY':
                        cursor=due.astimezone(UTC)
                        c.execute("INSERT OR REPLACE INTO app_settings VALUES('scheduler_cursor',?)",(cursor.isoformat(),)); c.commit()
                except Exception as e: print(json.dumps({'event':'run_failed','error':type(e).__name__}),flush=True)
            else:
                cursor=at; c.execute("INSERT OR REPLACE INTO app_settings VALUES('scheduler_cursor',?)",(cursor.isoformat(),)); c.commit()
        else:
            cursor=at; c.execute("INSERT OR REPLACE INTO app_settings VALUES('scheduler_cursor',?)",(cursor.isoformat(),)); c.commit()
        try:
            flush(c)
            if maintenance!=at.date():
                print(json.dumps({'backup':backup(c)}),flush=True)
                try: rates_refresh(c); health(c,'ecb','OK','Rates updated'); c.commit()
                except Exception as e: health(c,'ecb','FAILED',type(e).__name__); c.commit()
                maintenance=at.date()
        except Exception as e: print(json.dumps({'event':'maintenance_failed','error':type(e).__name__}),flush=True)
        time.sleep(15)

def main():
    p=argparse.ArgumentParser(); p.add_argument('command',choices=['daemon','check','status','matches','reports','history','backup','rates','retry','enable','disable','browser-resume','health']); p.add_argument('--id'); p.add_argument('--dry-run',action='store_true'); args=p.parse_args()
    if args.dry_run:
        if args.command!='check': p.error('--dry-run only applies to check')
        with tempfile.TemporaryDirectory() as tmp:
            global ROOT
            ROOT=Path(tmp); (ROOT/'inbox').mkdir()
            os.environ['DATABASE_PATH']=str(ROOT/'dryrun.sqlite'); os.environ['ENABLE_TELEGRAM']='false'; os.environ['BRAVE_STORAGE_LICENSE_CONFIRMED']='false'; os.environ['ENABLE_AUTHORIZED_DIRECT_CHECKS']='false'
            check('dry-run')
        return
    c=db()
    if args.command=='daemon': daemon()
    elif args.command=='check': check()
    elif args.command=='status': print(json.dumps(status(c),indent=2))
    elif args.command=='matches':
        matches=[json.loads(r[0]) for r in c.execute('SELECT current_json FROM listings')]
        matches=[r for r in matches if in_buyer_scope(r) and r['classification']!='REJECTED' and r['availability'] not in DEAD]
        matches.sort(key=lambda r:(not confirmed(r),not r['cost_complete'],r['delivered_eur'] if r['delivered_eur'] is not None else float('inf')))
        print(json.dumps(matches,indent=2))
    elif args.command=='reports':
        for row in c.execute('SELECT report FROM search_runs ORDER BY started DESC LIMIT 5'): print(row[0]+'\n')
    elif args.command=='history': print(json.dumps([dict(r) for r in c.execute('SELECT * FROM price_history WHERE listing_id=? ORDER BY observed_at',(args.id,))],indent=2))
    elif args.command=='backup': print(backup(c))
    elif args.command=='rates': rates_refresh(c)
    elif args.command=='retry':
        c.execute("UPDATE outbox SET attempts=0,next_attempt=0 WHERE state='PENDING'"); c.commit(); flush(c)
    elif args.command=='disable': (ROOT/'disabled').touch()
    elif args.command=='browser-resume': (ROOT/'browser-access-paused.json').unlink(missing_ok=True)
    elif args.command=='enable': (ROOT/'disabled').unlink(missing_ok=True)
    elif args.command=='health':
        age=(datetime.now(UTC)-datetime.fromisoformat((ROOT/'heartbeat').read_text())).total_seconds()
        sys.exit(0 if age<600 and c.execute('PRAGMA quick_check').fetchone()[0]=='ok' else 1)
if __name__=='__main__': main()
