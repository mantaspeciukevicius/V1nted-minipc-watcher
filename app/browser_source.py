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

MARKETS=('lt','pl','de','fr','nl','lv','it','es','cz')
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
    if re.search(r'\b(laptop|notebook|ideapad|gemibook|chromebook|macbook|vivobook|thinkpad|ideapad|aspire|latitude|elitebook|probook|netbook|portable|nokia|oneplus|smartfon|smartphone|nolan|helmet|kask|buty|quechua|bluesound|gps|charger|ladegerät|chargeur)\b',t): return False
    if re.search(r'\b(beelink|gmktec|acemagic|minisforum|trigkey|nipogi|firebat|bmax|morefine|topton|kingnovy|larkbox|nucbox)\b',t): return True
    if re.search(r'(?:samsung\s+n150|lenovo\s+3000)',t): return False
    if re.search(r'\bmini[ -]?(pc|computer|komputer|rechner|ordinateur)\b',t): return True
    return bool(re.search(r'\bn[ -]?(100|97|150)\b',t) and re.search(r'\b(pc|computer|komputer|rechner|ordinateur|ram|intel|16\s*gb|32\s*gb)\b',t))

def listing_section(text,title):
    start=text.find(title)
    if start<0: return ''
    text=text[start+len(title):]
    end=re.search(r'(?im)^(Siuntimas|Shipping|Wysyłka|Versand|Livraison|Spedizione|Envío|Verzending|Doprava|Nario prekės|Member.s items|Panašios prekės)\s*$',text)
    return text[:end.start()] if end else ''

def availability(text,buy_enabled=False):
    # Explicit labels only; no inference from a page merely loading.
    for pattern,state in [(r'^(sold|parduota|sprzedane|verkauft|vendu|venduto|vendido|verkocht|prodáno)[.!]?$', 'SOLD'),(r'^(reserved|rezervuota|zarezerwowane|reserviert|réservé|gereserveerd|riservato|reservado|rezervováno)[.!]?$', 'RESERVED'),(r'^(purchase in progress|pirkimas vykdomas)$','PURCHASE_IN_PROGRESS')]:
        if any(re.match(pattern,line.strip(),re.I) for line in text.splitlines()): return state
    return 'AVAILABLE_CONFIRMED' if buy_enabled else 'UNKNOWN'

def source_config(path):
    defaults={'markets':['lt'],'queries':['N100','N97','N150'],'max_details':12,'pause_seconds':3,'run_timeout_seconds':480}
    if path.exists(): defaults.update(json.loads(path.read_text()))
    if not defaults['markets'] or any(m not in MARKETS for m in defaults['markets']): raise ValueError('Unsupported browser market')
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
    statuses=[]; records=[]
    authorization=config_dir/'direct-authorization.json'
    if not authorization.exists(): return [],[{'source':'authorized_browser','state':'UNAVAILABLE','error':'Explicit authorization record missing'}]
    cfg=source_config(config_dir/'browser.json')
    gate=root/'browser-access-paused.json'
    if gate.exists(): return [],[{'source':'authorized_browser','state':'ACCESS_BLOCKED','error':'Browser paused after access challenge; inspect browser-evidence and use browser-resume after resolving authorization/access'}]
    from playwright.sync_api import sync_playwright
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    evidence=root/'browser-evidence'/stamp; evidence.mkdir(parents=True,exist_ok=True)
    started=time.monotonic(); seen=set(); detail_count=0
    def save(page,name,text):
        (evidence/(name+'.txt')).write_text(text)
        try:
            if name.startswith('item-') and page.locator('h1').count(): page.locator('h1').first.scroll_into_view_if_needed(timeout=3000)
            page.screenshot(path=str(evidence/(name+'.png')),full_page=False,timeout=10000)
        except Exception: pass
    def navigate(page,url,name):
        response=page.goto(url,wait_until='domcontentloaded',timeout=40000)
        page.wait_for_timeout(2500)
        text=page.locator('body').inner_text(timeout=10000)
        status=response.status if response else None
        problem=access_problem(status,text,page.url)
        # A visible CAPTCHA frame is a stop signal; never interact with it.
        if not problem:
            frames=page.locator('iframe[src*="captcha"], iframe[title*="challenge" i]')
            if any(frames.nth(i).is_visible() for i in range(frames.count())): problem='ACCESS_BLOCKED'
        if problem:
            save(page,name,text)
            if problem in {'ACCESS_BLOCKED','RATE_LIMIT','LOGIN_REQUIRED'}:
                gate.write_text(json.dumps({'at':stamp,'url':url,'state':problem,'evidence':str(evidence)}))
            statuses.append({'source':'authorized_browser','query':url,'state':problem,'error':'Stopped at HTTP/access failure; no bypass attempted'})
            return None
        save(page,name,text)
        return text
    with display(), sync_playwright() as p:
        browser=p.chromium.launch(headless=False,executable_path=__import__('os').getenv('BROWSER_EXECUTABLE'))
        page=browser.new_page()
        try:
            for market in cfg['markets']:
                for query in cfg['queries']:
                    if time.monotonic()-started>cfg['run_timeout_seconds']:
                        statuses.append({'source':'authorized_browser','state':'PARTIAL_CHECK','error':'Bounded run time exhausted'}); return records,statuses
                    url='https://www.vinted.'+market+'/catalog?'+urlencode({'search_text':query,'order':'newest_first'})
                    text=navigate(page,url,market+'-'+re.sub(r'\W','_',query))
                    if text is None: return records,statuses
                    # Dismiss only an ordinary cookie-consent dialog if present.
                    for label in ('Reject all','Reject optional cookies','Atmesti visus','Tik būtini slapukai','Palikti būtinuosius','Pasirinkti būtinuosius','Nur notwendige Cookies','Tout refuser','Odrzuć wszystkie'):
                        button=page.get_by_role('button',name=label,exact=True)
                        if button.count() and button.first.is_visible(): button.first.click(timeout=3000); break
                    page.wait_for_timeout(1000)
                    cards=page.locator('a[href*="/items/"][data-testid$="--overlay-link"]').evaluate_all("""els=>els.map(e=>{const card=e.closest('[data-testid^="product-item-id-"][class*="new-item-box__container"]'); return {url:e.href,title:e.getAttribute('title')||e.getAttribute('aria-label')||e.innerText,price:card?.querySelector('[data-testid$="--price-text"]')?.innerText||'',card:card?.innerText||''};})""")
                    (evidence/(market+'-'+re.sub(r'\W','_',query)+'-cards.json')).write_text(json.dumps(cards,ensure_ascii=False,indent=2))
                    valid=[]
                    for card in cards:
                        u=urlsplit(card['url'])
                        if u.hostname not in ('www.vinted.'+market,'vinted.'+market) or not re.match(r'/items/\d+',u.path): continue
                        ident=re.match(r'/items/(\d+)',u.path)[1]
                        if ident in seen: continue
                        seen.add(ident)
                        price,currency=price_from_text(card['price'])
                        title=re.split(r', (?:Brand|Prekių ženklas|Prekės ženklas|Marke|Marque|Marka|Merk|Marca):',card['title'])[0]
                        if not candidate_hint(title): continue
                        raw={'url':card['url'],'title':title,'country':market.upper(),'price':price,'currency':currency or 'EUR','description':'','evidence_source':url+' (public rendered search card)'}
                        try: record=normalize(c,raw,'authorized_browser_card')
                        except ValueError: continue
                        records.append(record); valid.append((raw,record))
                    status='AUTHORIZED_BROWSER_CHECK' if cards else 'NO_USABLE_RESULTS'
                    statuses.append({'source':'authorized_browser','query':url,'state':status,'count':len(valid),'coverage':'First newest-first results page only; market connectivity not established','evidence':str(evidence)})
                    for raw,record in valid:
                        if detail_count>=cfg['max_details'] or time.monotonic()-started>cfg['run_timeout_seconds']: break
                        if record['classification']=='REJECTED': continue
                        time.sleep(cfg['pause_seconds']); detail_count+=1
                        text=navigate(page,raw['url'],'item-'+record['id'].split(':')[1])
                        if text is None: return records,statuses
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
                        records[records.index(record)]=detail
                    time.sleep(cfg['pause_seconds'])
        except Exception as e:
            statuses.append({'source':'authorized_browser','state':'SEARCH_PROVIDER_FAILURE','error':type(e).__name__+': '+str(e)[:160]})
        finally: browser.close()
    return records,statuses
