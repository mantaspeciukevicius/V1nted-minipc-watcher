"""Bounded public rendered classified adapter. No login or challenge bypass."""
import json, re, time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote
from browser_source import display, access_problem, price_from_text, availability, candidate_hint

def listing_id(url):
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname not in {'www.skelbiu.lt','skelbiu.lt'}: raise ValueError('Not a Skelbiu classified')
    m=re.fullmatch(r'/skelbimai/[^/]+-(\d+)\.html',u.path)
    if not m: raise ValueError('Not a classified identity')
    return 'skelbiu:'+m[1]

def detail_raw(url,title,description,price_text,location='',header=''):
    listing_id(url)
    price,currency=price_from_text(price_text)
    state=availability(header)
    if re.search(r'(?im)^parduota(?:s)?(?:\s+per\s+.+)?[.!]?$',header): state='SOLD'
    if re.search(r'(?im)^rezervuota(?:s)?[.!]?$',header): state='RESERVED'
    if re.search(r'(?im)^skelbimas\s+(?:neaktyvus|pašalintas)',header): state='REMOVED'
    condition=re.search(r'Būklė:\s*(Naudota|Nauja)',header,re.I)
    updated=re.search(r'Atnaujintas[^\n]*',header)
    delivery='UNKNOWN'; delivery_evidence=None
    if re.search(r'nesiunči(?:u|ame)|tik\s+(?:atsiėmimas|atsiimti)',description,re.I): delivery='COLLECTION_ONLY';delivery_evidence='Seller description: collection only'
    elif re.search(r'(?:siunči(?:u|ame)|siuntimas)\s+(?:į\s+(?:visą\s+)?lietuvą|visoje\s+lietuvoje)',description,re.I): delivery='DIRECT_LT_CONFIRMED';delivery_evidence='Seller explicitly offers domestic shipping; cost unknown'
    elif re.search(r'galima\s+atsiimti|atsiėmimas',description,re.I): delivery='COLLECTION_AVAILABLE';delivery_evidence='Seller description: collection offered'
    storage=re.findall(r'\b\d+\s*(?:gb|tb)\s*(?:ssd|nvme|hdd|emmc)\b',description,re.I)
    warranty=re.search(r'(?:garantija|warranty)[^\n.]{0,100}',description,re.I)
    adapter='UNKNOWN'
    if re.search(r'be\s+maitinimo|without\s+(?:power\s+)?adapter',description,re.I): adapter='MISSING'
    elif re.search(r'(?:komplekte|pridedam(?:as|a)|su)\s+(?:maitinimo|adapter)|maitinimo\s+šaltinis\s+su',description,re.I): adapter='INCLUDED_SELLER_CLAIM'
    raw=dict(url=url,title=title,description=description,price=price,currency=currency or 'EUR',country='LT',seller_country=None,seller_location=location or None,availability=state,availability_evidence='Explicit listing header state',delivery=delivery,delivery_evidence=delivery_evidence,storage=storage[0] if len(set(storage))==1 else 'UNKNOWN',warranty=warranty[0] if warranty else 'UNKNOWN',power_adapter=adapter,evidence_source=url+' (rendered classified details)',details_confirmed=True,condition=condition[1] if condition else 'UNKNOWN',refreshed_at=updated[0] if updated else None)
    return raw

def search_plan(cfg,c):
    terms=cfg.get('rotating_queries',['mini-pc','5600u','5500u','beelink','gmktec','nuc','mini-kompiuteris','n95','n97','n150','5300u','4300u','7330u','7430u','5700u','minisforum','geekom','chuwi','lenovo-tiny','hp-mini','dell-micro','n200','n250','n300','n305','n350','n355','5425u','4500u','4600u','5625u','7520u','7530u','5800u','5825u'])
    from search_quality import choose_terms
    frequent=cfg.get('frequent_queries',['n100'])
    terms=[t for t in terms if t.casefold() not in {x.casefold() for x in frequent}]
    selected=choose_terms(c,'skelbiu',terms,2,cfg,'skelbiu_rotation')
    return list(dict.fromkeys(frequent+selected))[:4]

def empty_search(text):
    return bool(re.search(r'Pagal Jūsų paiešką nieko neradome|Visi skelbimai\s*\(\s*0\s*\)|skelbimų nėra',text,re.I))

def collect(root,normalize,c,config_dir=Path('/config')):
    from playwright.sync_api import sync_playwright
    cfgpath=config_dir/'skelbiu.json'; cfg=json.loads(cfgpath.read_text()) if cfgpath.exists() else {}
    if not cfg.get('enabled',True): return [],[dict(source='skelbiu',state='DISABLED')]
    gate=root/'skelbiu-access-paused.json'
    if gate.exists(): return [],[dict(source='skelbiu',state='ACCESS_BLOCKED',error='Paused after access restriction; inspect evidence before clearing source gate')]
    started=time.monotonic(); budget=min(240,max(30,float(cfg.get('run_timeout_seconds',150)))); pause=max(3,float(cfg.get('pause_seconds',3))); limit=min(12,max(0,int(cfg.get('max_details',5))))
    evidence=root/'skelbiu-evidence'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'); evidence.mkdir(parents=True,exist_ok=True)
    from detail_policy import previous, plan, mark_attempt
    tracked=previous(c,'skelbiu')
    records={}; statuses=[]; detail_count=0; visited=set(); active_search_term=None; query_tick=started
    def navigate(page,url):
        if time.monotonic()-started>budget: raise TimeoutError('Skelbiu run budget exhausted')
        time.sleep(pause); response=page.goto(url,wait_until='domcontentloaded',timeout=min(30000,max(1000,int((budget-(time.monotonic()-started))*1000))))
        page.wait_for_timeout(1500); text=page.locator('body').inner_text(timeout=5000)
        problem=access_problem(response.status if response else None,text,page.url)
        frames=page.locator('iframe[src*="captcha"], iframe[title*="challenge" i]')
        if any(frames.nth(i).is_visible() for i in range(frames.count())): problem='ACCESS_BLOCKED'
        (evidence/(str(len(visited))+'.txt')).write_text(text); visited.add(url)
        if problem:
            if problem in {'ACCESS_BLOCKED','RATE_LIMIT','LOGIN_REQUIRED'}: gate.write_text(json.dumps(dict(url=url,state=problem,evidence=str(evidence))))
            statuses.append(dict(source='skelbiu',state=problem,query=url,error='Stopped at access restriction')); return None
        return text
    def read(page,url):
        nonlocal detail_count
        detail_count+=1
        text=navigate(page,url)
        if text is None: return False
        title=page.locator('h1'); desc=page.locator('.item-description .description'); price=page.locator('.item-title-container .price'); loc=page.locator('.item-title-container .cities-name'); head=page.locator('.item-title-container')
        if not title.count() or not desc.count():
            statuses.append(dict(source='skelbiu',state='PARSING_FAILURE',query=url,error='Listing title/description missing')); return True
        raw=detail_raw(url,title.first.inner_text(),desc.first.inner_text(),price.first.inner_text() if price.count() else '',loc.first.inner_text() if loc.count() else '',head.first.inner_text() if head.count() else '')
        records[listing_id(url)]=normalize(c,raw,'skelbiu_detail'); return True
    with display(),sync_playwright() as p:
        browser=p.chromium.launch(headless=False,executable_path=__import__('os').getenv('BROWSER_EXECUTABLE')); page=browser.new_page()
        try:
            queries=search_plan(cfg,c)
            # Discovery gets the first detail slots; one old candidate is rechecked afterward.
            for term in queries:
                active_search_term=term;query_tick=time.monotonic();query_ids=set();query_raw_ids=set();duplicate_count=0
                url='https://www.skelbiu.lt/paieska/'+quote(term.strip().replace(' ','-'))+'/'
                text=navigate(page,url)
                if text is None:
                    statuses[-1].update(marketplace='skelbiu',search_term=term,duration_seconds=round(time.monotonic()-query_tick,3));break
                from skelbiu_html import search_cards
                cards=search_cards(page.content())
                (evidence/(term+'.json')).write_text(json.dumps(cards,ensure_ascii=False))
                if not cards:
                    statuses.append(dict(source='skelbiu',state='NO_USABLE_RESULTS' if empty_search(text) else 'PARSING_FAILURE',query=url,count=0,marketplace='skelbiu',search_term=term,raw_count=0,listing_ids=[],duration_seconds=round(time.monotonic()-query_tick,3))); continue
                count=0
                for card in cards:
                    try: ident=listing_id(card['url'])
                    except ValueError: continue
                    query_raw_ids.add(ident)
                    if ident in records:
                        query_ids.add(ident);duplicate_count+=1;continue
                    if not candidate_hint(card['title']): continue
                    amount,currency=price_from_text(card['price']); raw=dict(url=card['url'],title=card['title'],price=amount,currency=currency or 'EUR')
                    record=normalize(c,raw,'skelbiu_card'); records[ident]=record; count+=1;query_ids.add(ident)
                statuses.append(dict(source='skelbiu',state='AUTHORIZED_BROWSER_CHECK',query=url,count=count,marketplace='skelbiu',search_term=term,raw_count=len(query_raw_ids),duplicate_count=duplicate_count,listing_ids=sorted(query_ids),duration_seconds=round(time.monotonic()-query_tick,3),pages=1,details=detail_count,evidence=str(evidence),elapsed_seconds=round(time.monotonic()-started,2)))
            active_search_term=None
            selected,metrics=plan(c,records,tracked,dict(cfg,max_details=limit))
            for record in selected:
                if time.monotonic()-started>budget:
                    statuses.append(dict(source='skelbiu',state='PARTIAL_CHECK',error='Detail time budget exhausted'));break
                mark_attempt(c,record)
                if not read(page,record['url']): return list(records.values()),statuses
            if statuses: statuses[-1].update(detail_plan=metrics,details_attempted=detail_count)
        except Exception as e:
            statuses.append(dict(source='skelbiu',state='PARTIAL_CHECK' if isinstance(e,TimeoutError) else 'SEARCH_PROVIDER_FAILURE',error=type(e).__name__,details=detail_count))
            if active_search_term: statuses[-1].update(marketplace='skelbiu',search_term=active_search_term,duration_seconds=round(time.monotonic()-query_tick,3))
        finally: browser.close()
    return list(records.values()),statuses
