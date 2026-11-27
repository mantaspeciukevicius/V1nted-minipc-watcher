"""Bounded discovery, explicit fee evidence, and diagnostic retention."""
import json,re,os,shutil
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import urljoin,urlsplit,parse_qs

def next_page(links,current):
    base=urlsplit(current)
    for link in links:
        target=urljoin(current,link.get('href') or '')
        u=urlsplit(target);label=(link.get('label') or '').strip().lower()
        if u.scheme!='https' or u.hostname!=base.hostname:continue
        if not (u.path.startswith('/catalog') if 'vinted.' in base.hostname else u.path.startswith('/paieska/')):continue
        if target==current:continue
        if link.get('rel')=='next' or label in {'2','next','next page','kitas','kitas puslapis','toliau','›','»'}:
            return target
    return None

def page_link(page,current):
    links=page.locator('a[href]').evaluate_all("es=>es.filter(e=>e.getClientRects().length).map(e=>({href:e.href,label:e.getAttribute('aria-label')||e.innerText,rel:e.rel}))")
    return next_page(links,current)

def fee_evidence(text,asking,url,stamp):
    """Only the explicitly displayed fee-inclusive EUR total; shipping from is a lower bound."""
    costs={};notes=[]
    number=r'(\d+(?:[.,]\d{1,2})?)'
    total=re.search(number+r'\s*€\s*įsk\.?\s*Vinted mokestį|€\s*'+number+r'\s*incl\.?\s*Vinted fee',text,re.I)
    if total and asking is not None:
        from decimal import Decimal
        inclusive=Decimal((total[1] or total[2]).replace(',','.'));amount=inclusive-Decimal(str(asking))
        asking_lines=re.findall(r'(?m)^\s*(?:€\s*'+number+r'|'+number+r'\s*€)\s*$',text)
        asking_seen=any(Decimal((a or b).replace(',','.'))==Decimal(str(asking)) for a,b in asking_lines)
        if amount>=0 and asking_seen:
            costs['buyer_fee']=dict(amount=str(amount),currency='EUR',status='confirmed',source=url+' (displayed fee-inclusive total minus asking price)',timestamp=stamp)
    ship=re.search(r'(?:Siuntimas|Shipping)\s*\n\s*(?:nuo|from)\s*'+number+r'\s*€|Shipping\s*\n\s*from\s*€\s*'+number,text,re.I)
    if ship:
        costs['seller_shipping']=dict(amount=(ship[1] or ship[2]).replace(',','.'),currency='EUR',status='estimated',source=url+' (advertised starting price; checkout required)',timestamp=stamp,lower_bound=True)
        notes.append('Shipping starting price only; Lithuania destination, carrier and checkout total unverified.')
    return costs,notes

def cleanup(root,c,at=None,dry_run=False):
    at=at or datetime.now(timezone.utc);days=max(2,int(os.getenv('EVIDENCE_RETENTION_DAYS','30')))
    budget=max(1,int(os.getenv('EVIDENCE_MAX_MB','512')))*1024*1024
    protected_ids=set();protected_paths=[]
    for key,value in c.execute("SELECT key,value FROM app_settings WHERE key LIKE 'failure_watch:%'"):
        try:protected_ids.update(k.split(':',1)[1] for k in json.loads(value).get('issues',{}) if k.startswith('detail:'))
        except (ValueError,TypeError):pass
    for gate in root.glob('*access-paused.json'):
        try:protected_paths.append(Path(json.loads(gate.read_text()).get('evidence','')))
        except (ValueError,OSError):pass
    entries=[]
    for name in ['browser-evidence','skelbiu-evidence']:
        parent=root/name
        if not parent.exists() or parent.is_symlink():continue
        for folder in parent.iterdir():
            if folder.is_symlink() or not folder.is_dir() or not re.fullmatch(r'\d{8}T\d{6}',folder.name):continue
            stamp=datetime.strptime(folder.name,'%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
            files=list(folder.rglob('*'))
            size=sum(f.stat().st_size for f in files if f.is_file() and not f.is_symlink())
            protect=folder in protected_paths or any(any(ident in f.name for ident in protected_ids) for f in files)
            entries.append((stamp,folder,size,protect))
    total=sum(x[2] for x in entries);removed=[];freed=0
    for stamp,folder,size,protect in sorted(entries):
        if protect or stamp>at-timedelta(days=2):continue
        if stamp>at-timedelta(days=days) and total<=budget:continue
        removed.append(str(folder));freed+=size;total-=size
        if not dry_run:shutil.rmtree(folder)
    return dict(dry_run=dry_run,removed_directories=len(removed),freed_bytes=freed,remaining_bytes=total,protected_directories=sum(x[3] for x in entries),retention_days=days,max_mb=budget//1024//1024)

def verification_template(record):
    fields=['url','title','description','price','currency','condition','manufacturer','model','storage','power_adapter','seller_country','seller_location']
    result={key:record.get(key) for key in fields}
    result.update(observed_at=None,details_confirmed=False,evidence_source=None,availability='UNKNOWN',availability_evidence=None,delivery='UNKNOWN',delivery_evidence=None)
    result['costs']={key:dict(amount=None,currency='EUR',status='UNKNOWN',source=None,timestamp=None) for key in ['buyer_fee','seller_shipping','additional_charges']}
    return result
