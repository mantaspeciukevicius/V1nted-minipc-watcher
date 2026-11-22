"""Explicitly authorized public-UI browser access, without sessions or bypasses.

Only rendered DOM is read. No API calls, cookie import, stealth, or CAPTCHA handling.
"""
import json
import subprocess
import select
from contextlib import contextmanager
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

MARKETS=('lt','pl','fi','ee','de','fr','nl','lv','it','es','cz')
BLOCK_TEXT=re.compile(r'verify (?:that )?you are human|checking your browser|access denied|unusual (?:traffic|activity)|captcha|patvirtinkite.{0,30}(?:žmogus|robot)|too many requests|request (?:was )?blocked|you have been blocked',re.I)

def access_problem(status,text,url):
    if status==429: return 'RATE_LIMIT'
    if status in (401,403): return 'ACCESS_BLOCKED'
    if status and status>=500: return 'SEARCH_PROVIDER_FAILURE'
    if status and status>=400: return 'SOURCE_UNAVAILABLE'
    if BLOCK_TEXT.search(text): return 'ACCESS_BLOCKED'
    if re.search(r'/(?:login|member/signup|auth)(?:[/?]|$)',url): return 'LOGIN_REQUIRED'
    return None

def price_from_text(text):
    """Read only explicit currency-bearing amounts; ambiguous card totals stay unknown."""
    pattern=r'(?:(€|EUR|PLN|zł|CZK|Kč)\s*(\d[\d\s\u00a0]*(?:[.,]\d{1,2})?)|(\d[\d\s\u00a0]*(?:[.,]\d{1,2})?)\s*(€|EUR|PLN|zł|CZK|Kč))'
    hits=[]
    for m in re.finditer(pattern,text,re.I):
        symbol=m[1] or m[4]; number=m[2] or m[3]
        value=re.sub(r'\s','',number).replace(',','.')
        currency={'€':'EUR','eur':'EUR','pln':'PLN','zł':'PLN','czk':'CZK','kč':'CZK'}[symbol.lower()]
        hits.append((value,currency))
    distinct=list(dict.fromkeys(hits))
    return distinct[0] if len(distinct)==1 else (None,None)

def candidate_hint(title):
    t=title.lower()
    from cpu_policy import parse
    cpu,_,_=parse(title)
    if re.search(r'\b(laptop|notebook|ideapad|gemibook|chromebook|macbook|vivobook|thinkpad|ideapad|aspire|latitude|elitebook|probook|netbook|portable|nokia|oneplus|smartfon|smartphone|nolan|helmet|kask|buty|quechua|bluesound|gps|charger|ladegerät|chargeur)\b',t): return False
    if re.search(r'\b(ram module|sodimm|motininė|motherboard|tv box|korpusas|docking|stotelė)\b',t): return False
    if cpu and re.search(r'\b(mini|nuc|tiny|micro)\b',t): return True
    if re.search(r'\b(beelink|gmktec|acemagic|minisforum|trigkey|nipogi|firebat|bmax|morefine|topton|kingnovy|larkbox|nucbox)\b',t): return True
    if re.search(r'(?:samsung\s+n150|lenovo\s+3000)',t): return False
    if re.search(r'\bmini[ -]?(pc|computer|komputer|rechner|ordinateur)\b',t): return True
    return bool(re.search(r'\bn[ -]?(100|97|150)\b',t) and re.search(r'\b(pc|computer|komputer|rechner|ordinateur|ram|intel|(?:12|16|20|24|32|48|64|96|128)\s*gb)\b',t))

def listing_section(text,title):
    start=text.find(title)
    if start<0: return ''
    text=text[start+len(title):]
    end=re.search(r'(?im)^(Siuntimas|Shipping|Wysyłka|Versand|Livraison|Spedizione|Envío|Verzending|Doprava|Nario prekės|Member.s items|Panašios prekės)\s*$',text)
    return text[:end.start()] if end else ''

def availability(text,buy_enabled=False):
    # Explicit labels only; no inference from a page merely loading.
    for pattern,state in [(r'^(?:(?:item|artikel|articolo|artículo|article|przedmiot|prekė)\s+)?(sold|parduota|sprzedane|verkauft|vendu|venduto|vendido|verkocht|prodáno)(?:\s+(?:item|artikel|articolo|artículo|article))?[.!]?$', 'SOLD'),(r'^(reserved|rezervuota|zarezerwowane|reserviert|réservé|gereserveerd|riservato|reservado|rezervováno)[.!]?$', 'RESERVED'),(r'^(purchase in progress|pirkimas vykdomas)$','PURCHASE_IN_PROGRESS')]:
        if any(re.match(pattern,line.strip(),re.I) for line in text.splitlines()): return state
    return 'AVAILABLE_CONFIRMED' if buy_enabled else 'UNKNOWN'

def empty_search(text):
    return bool(re.search(r'no (?:items|results) found|nerasta (?:prekių|rezultatų)|prekių nerasta|nieko neradome|brak wyników|nie znaleziono',text,re.I))

def source_config(path):
    defaults={'markets':['lt'],'queries':['N100','N97','N150'],'max_details':12,'pause_seconds':3,'run_timeout_seconds':480}
    if path.exists(): defaults.update(json.loads(path.read_text()))
    if not defaults['markets'] or any(m not in MARKETS for m in defaults['markets']): raise ValueError('Unsupported browser market')
    if os.getenv('BUYER_MARKET'): defaults['markets']=[os.environ['BUYER_MARKET'].lower()]
    if not 1<=len(defaults['queries'])<=12: raise ValueError('Use 1–12 browser queries')
    if not 0<=int(defaults['max_details'])<=30: raise ValueError('max_details must be between 0 and 30')
    defaults['pause_seconds']=max(2,float(defaults['pause_seconds']))
    defaults['run_timeout_seconds']=min(900,max(30,float(defaults['run_timeout_seconds'])))
    return defaults

@contextmanager
def display():
    if os.getenv('DISPLAY'):
        yield
        return
    proc=subprocess.Popen(['Xvfb','-displayfd','1','-screen','0','1280x900x24','-nolisten','tcp'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    try:
        if not select.select([proc.stdout],[],[],10)[0]: raise RuntimeError('Virtual display failed to start')
        number=proc.stdout.readline().strip()
        if not number.isdigit(): raise RuntimeError('Invalid virtual display response')
        os.environ['DISPLAY']=':'+number
        yield
    finally:
        os.environ.pop('DISPLAY',None)
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()

def collect(root,normalize,c,config_dir=Path('/config')):
    statuses=[]; records={}; raws={}
    authorization=config_dir/'direct-authorization.json'
    if not authorization.exists(): return [],[{'source':'authorized_browser','state':'UNAVAILABLE','error':'Explicit authorization record missing'}]
    from detail_policy import previous, plan, mark_attempt
    tracked=previous(c,'vinted') if c is not None else {}
    cfg=source_config(config_dir/'browser.json')
    from cpu_policy import policies
    from search_quality import choose_terms
    rotating=cfg.get('rotating_queries',['mini PC','Beelink','GMKtec','Minisforum']+[cpu for cpu in policies() if cpu not in cfg['queries']])
    gate=root/'browser-access-paused.json'
    if gate.exists(): return [],[{'source':'authorized_browser','state':'ACCESS_BLOCKED','error':'Browser paused after access challenge; inspect browser-evidence and use browser-resume after resolving authorization/access'}]
    cfg['queries']=list(dict.fromkeys(cfg['queries']+choose_terms(c,'vinted',rotating,1,cfg,'vinted_rotation')))
    from playwright.sync_api import sync_playwright
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    evidence=root/'browser-evidence'/stamp; evidence.mkdir(parents=True,exist_ok=True)
    started=time.monotonic(); seen=set(); detail_count=0; active_search_term=None; query_tick=started
    def save(page,name,text):
        (evidence/(name+'.txt')).write_text(text)
        try:
            if name.startswith('item-') and page.locator('h1').count(): page.locator('h1').first.scroll_into_view_if_needed(timeout=remaining_ms(deadline,3000))
            page.screenshot(path=str(evidence/(name+'.png')),full_page=False,timeout=remaining_ms(deadline,10000))
        except Exception: pass
    from recovery import fetch,settings as recovery_settings,remaining_ms,RunBudgetExceeded
    recovery_cfg=recovery_settings(config_dir);deadline=started+cfg['run_timeout_seconds'];retry_events=[];successful_details=[];active_url=None
    def restart_browser():
        nonlocal browser,page
        try: browser.close()
        except Exception: pass
        browser=p.chromium.launch(headless=False,executable_path=os.getenv('BROWSER_EXECUTABLE'));page=browser.new_page()
    def navigate(_page,url,name):
        nonlocal active_url
        active_url=url
        def operation():
            response=page.goto(url,wait_until='domcontentloaded',timeout=remaining_ms(deadline,40000))
            http_problem=access_problem(response.status if response else None,'',page.url)
            if http_problem in {'ACCESS_BLOCKED','RATE_LIMIT','LOGIN_REQUIRED','SOURCE_UNAVAILABLE'}:return {'problem':http_problem,'text':'HTTP access restriction or unavailable response; no listing evidence inferred'}
            if deadline-time.monotonic()<2.5:raise RunBudgetExceeded('Browser run time budget exhausted')
            page.wait_for_timeout(2500)
            text=page.locator('body').inner_text(timeout=remaining_ms(deadline,10000))
            status=response.status if response else None
            problem=access_problem(status,text,page.url)
            frames=page.locator('iframe[src*="captcha"], iframe[title*="challenge" i]')
            if any(frames.nth(i).is_visible() for i in range(frames.count())):problem='ACCESS_BLOCKED'
            return {'problem':problem,'text':text}
        result=fetch(operation,deadline,recovery_cfg,restart_browser,retry_events)
        text=result['text'];problem=result['problem']
        save(page,name,text)
        if problem:
            if problem in {'ACCESS_BLOCKED','RATE_LIMIT','LOGIN_REQUIRED'}:
                gate.write_text(json.dumps({'at':stamp,'url':url,'state':problem,'evidence':str(evidence)}))
            statuses.append({'source':'authorized_browser','query':url,'state':problem,'error':'HTTP/access failure after permitted recovery; no bypass attempted'})
            return None
        return text
    def read_detail(page,raw,record,text):
        h1=page.locator('h1'); title=h1.first.inner_text() if h1.count() else raw['title']
        description=''
        for selector in ('[class*="item-description__text"]','[class*="item-description"]','[data-testid="item-description"]','[data-testid="item-description-text"]','[itemprop="description"]'):
            loc=page.locator(selector)
            if loc.count(): description=loc.first.inner_text(); break
        if not description: description=listing_section(text,title)
        price,currency=None,None
        for selector in ('[data-testid="item-price"]','[data-testid="item-price-text"]','[itemprop="price"]'):
            loc=page.locator(selector)
            if loc.count(): price,currency=price_from_text(loc.first.inner_text())
            if price is not None: break
        # Do not read the whole page as specs or price: related products can contaminate it.
        buy=page.get_by_role('button',name=re.compile(r'^(Buy now|Pirkti|Kup teraz|Acheter|Kaufen|Comprar|Acquista|Kopen|Koupit)$',re.I))
        buy_enabled=any(buy.nth(i).is_visible() and buy.nth(i).is_enabled() for i in range(buy.count()))
        state=availability(text,buy_enabled)
        raw.update(title=title,description=description,availability=state,availability_evidence='Rendered enabled purchase button' if buy_enabled else 'Rendered explicit state label',details_confirmed=True,evidence_source=raw['url']+' (rendered listing details)')
        if price is not None: raw.update(price=price,currency=currency)
        detail=normalize(c,raw,'authorized_browser_detail')
        if detail.get('details_confirmed'): successful_details.append(detail['id'])
        return detail
    with display(), sync_playwright() as p:
        browser=p.chromium.launch(headless=False,executable_path=__import__('os').getenv('BROWSER_EXECUTABLE'))
        page=browser.new_page()
        try:
            for market in cfg['markets']:
                for query in cfg['queries']:
                    active_search_term=query;query_tick=time.monotonic();query_ids=set();query_raw_ids=set();duplicate_count=0
                    if time.monotonic()-started>cfg['run_timeout_seconds']:
                        statuses.append({'source':'authorized_browser','state':'PARTIAL_CHECK','error':'Bounded run time exhausted'}); return list(records.values()),statuses
                    url='https://www.vinted.'+market+'/catalog?'+urlencode({'search_text':query,'order':'newest_first'})
                    text=navigate(page,url,market+'-'+re.sub(r'\W','_',query))
                    if text is None:
                        statuses[-1].update(marketplace='vinted',search_term=query,duration_seconds=round(time.monotonic()-query_tick,3))
                        return list(records.values()),statuses
                    # Dismiss only an ordinary cookie-consent dialog if present.
                    for label in ('Reject all','Reject optional cookies','Atmesti visus','Tik būtini slapukai','Palikti būtinuosius','Pasirinkti būtinuosius','Nur notwendige Cookies','Tout refuser','Odrzuć wszystkie'):
                        button=page.get_by_role('button',name=label,exact=True)
                        if button.count() and button.first.is_visible():
                            try: button.first.click(timeout=3000)
                            except Exception: pass  # Consent UI may be obscured; rendered cards remain readable.
                            break
                    page.wait_for_timeout(1000)
                    cards=page.locator('a[href*="/items/"][data-testid$="--overlay-link"]').evaluate_all("""els=>els.map(e=>{const card=e.closest('[data-testid^="product-item-id-"][class*="new-item-box__container"]'); return {url:e.href,title:e.getAttribute('title')||e.getAttribute('aria-label')||e.innerText,price:card?.querySelector('[data-testid$="--price-text"]')?.innerText||'',card:card?.innerText||''};})""")
                    (evidence/(market+'-'+re.sub(r'\W','_',query)+'-cards.json')).write_text(json.dumps(cards,ensure_ascii=False,indent=2))
                    valid=[]
                    for card in cards:
                        u=urlsplit(card['url'])
                        if u.hostname not in ('www.vinted.'+market,'vinted.'+market) or not re.match(r'/items/\d+',u.path): continue
                        ident=re.match(r'/items/(\d+)',u.path)[1]
                        query_raw_ids.add(ident)
                        if ident in seen:
                            duplicate_count+=1
                            if 'vinted:'+ident in records: query_ids.add('vinted:'+ident)
                            continue
                        seen.add(ident)
                        price,currency=price_from_text(card['price'])
                        title=re.split(r', (?:Brand|Prekių ženklas|Prekės ženklas|Marke|Marque|Marka|Merk|Marca):',card['title'])[0]
                        if not candidate_hint(title): continue
                        raw={'url':card['url'],'title':title,'country':market.upper(),'price':price,'currency':currency or 'EUR','description':'','evidence_source':url+' (public rendered search card)'}
                        try: record=normalize(c,raw,'authorized_browser_card')
                        except ValueError: continue
                        records[record['id']]=record; raws[record['id']]=raw; valid.append((raw,record));query_ids.add(record['id'])
                    status='AUTHORIZED_BROWSER_CHECK' if cards else 'NO_USABLE_RESULTS' if empty_search(text) else 'PARSING_FAILURE'
                    statuses.append({'source':'authorized_browser','query':url,'state':status,'count':len(valid),'marketplace':'vinted','search_term':query,'raw_count':len(query_raw_ids),'duplicate_count':duplicate_count,'listing_ids':sorted(query_ids),'duration_seconds':round(time.monotonic()-query_tick,3),'coverage':'First newest-first results page only; market connectivity not established','evidence':str(evidence)})
                    time.sleep(cfg['pause_seconds'])
            active_search_term=None
            if os.getenv('BUYER_MARKET'):
                tracked={k:r for k,r in tracked.items() if (urlsplit(r['url']).hostname or '').removeprefix('www.')=='vinted.'+os.environ['BUYER_MARKET'].lower()}
            selected,metrics=plan(c,records,tracked,cfg)
            for record in selected:
                if time.monotonic()-started>cfg['run_timeout_seconds']:
                    statuses.append({'source':'authorized_browser','state':'PARTIAL_CHECK','error':'Detail time budget exhausted'});break
                mark_attempt(c,record);time.sleep(cfg['pause_seconds']);detail_count+=1
                text=navigate(page,record['url'],'item-'+record['id'].split(':')[1])
                if text is None: return list(records.values()),statuses
                raw=raws.get(record['id'],{'url':record['url'],'title':record['title'],'country':record['country'],'currency':record['currency'],'price':None})
                records[record['id']]=read_detail(page,raw,record,text)
            if statuses: statuses[-1].update(detail_plan=metrics,details_attempted=detail_count)
        except Exception as e:
            statuses.append({'source':'authorized_browser','state':'PARTIAL_CHECK' if isinstance(e,RunBudgetExceeded) else 'SEARCH_PROVIDER_FAILURE','query':active_url,'error':type(e).__name__+': '+str(e)[:160]})
            if active_search_term: statuses[-1].update(marketplace='vinted',search_term=active_search_term,duration_seconds=round(time.monotonic()-query_tick,3))
        finally:
            if statuses: statuses[-1].update(details_attempted=detail_count,detail_success_ids=successful_details,navigation_retry_events=retry_events)
            browser.close()
    return list(records.values()),statuses
