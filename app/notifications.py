"""Evidence-aware plain-text alerts and stable Telegram-safe message chunks."""
import os,re
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from cpu_policy import assessment

LABELS={'NEW_VERIFIED_MATCH':'NEW CANDIDATE','NEW_UNVERIFIED_CANDIDATE':'NEW CANDIDATE','PRICE_DROP':'PRICE DROP','DISPLAY_PRICE_DECREASE_UNVERIFIED':'DISPLAYED PRICE DROP','CROSSED_CPU_TARGET':'CPU PRICE TARGET CROSSED','RETURNED_TO_AVAILABLE':'AVAILABILITY CHANGED'}
FLAGS={'RAM_NOT_INSTALLED':'installed RAM missing','OPTIONAL_CONFIGURATION':'optional configuration/upgrade','STORAGE_MISSING':'storage missing','POWER_ADAPTER_MISSING':'power adapter missing','DEFECTIVE':'reported defect','MULTIPLE_CONFIGURATION_PRICES':'configuration price unclear','CARD_SPECIFICATION_CONFLICT':'search card conflicts with prior details'}
COST_NAMES={'buyer_fee':'buyer fee','seller_shipping':'seller shipping','additional_charges':'additional charges','forwarding':'forwarding','local_delivery':'local delivery'}

def short(value,limit=240):
    return re.sub(r'\s+',' ',str(value or 'UNKNOWN')).strip()[:limit]

def money(value,currency='EUR'):
    try:
        number=Decimal(str(value))
        if not number.is_finite(): return 'UNKNOWN'
    except (InvalidOperation,ValueError): return 'UNKNOWN'
    return ('€' if currency=='EUR' else currency+' ')+f'{number:.2f}'

def evidence_age(stamp,at):
    try:
        dt=datetime.fromisoformat(stamp)
        if dt.tzinfo is None: return None
        return max(0,(at-dt).total_seconds())
    except (TypeError,ValueError): return None

def age_text(seconds):
    if seconds is None: return 'not checked'
    if seconds<60: return 'less than 1 minute old'
    if seconds<3600: return f'{int(seconds//60)} minutes old'
    if seconds<86400: return f'{seconds/3600:.1f} hours old'
    return f'{seconds/86400:.1f} days old'

def format_alert(r,event,previous=None,at=None):
    at=at or datetime.now(timezone.utc)
    policy=assessment(r.get('cpu'),r.get('asking_eur'),r.get('classification','NEEDS_MANUAL_REVIEW'))
    stamp=r.get('specs_observed_at') or (r.get('observed_at') if r.get('details_confirmed') else None)
    age=evidence_age(stamp,at);stale=age is None or age>=int(os.getenv('VERIFICATION_TTL_HOURS','24'))*3600
    cpu=r.get('cpu') or 'UNKNOWN';ram=r.get('ram_gb');market=r.get('marketplace') or r.get('id','unknown:').split(':')[0]
    lines=['MINI PC WATCHER — '+LABELS.get(event,event.replace('_',' ')),f'Event: {event}',f'{short(r.get("title"))}',f'Marketplace: {market.title()}.lt',f'CPU: {cpu} | RAM: {str(ram)+" GB" if ram is not None else "UNKNOWN"} | Storage: {short(r.get("storage"),100)}',f'Asking: {money(r.get("asking_eur"))} | CPU maximum: {money(policy["cpu_max_asking_eur"])}']
    if r.get('currency','EUR')!='EUR': lines.append('Shown asking currency: '+money(r.get('price'),r['currency']))
    difference=policy['below_target_eur']
    if difference is not None: lines.append(f'Target comparison: {money(abs(difference))} '+('below target' if difference>0 else 'above target' if difference<0 else 'at target'))
    if policy['deal_state']=='WITHIN_CPU_TARGET':
        qualifier='Detail-supported' if r.get('details_confirmed') and not stale else 'Reported'
        lines.append(f'Why flagged: {qualifier} supported CPU and {ram} GB RAM; asking within this CPU’s ceiling.')
    else: lines.append('Why flagged: '+policy['deal_state'].replace('_',' ').lower()+'; verification required.')
    history=[]
    for key,label in [('original_asking_price','First observed'),('lowest_asking_price','Lowest observed')]:
        if r.get(key) is not None: history.append(label+' '+money(r[key],r.get('currency','EUR')))
    if history: lines.append('Price history: '+'; '.join(history))
    if previous and previous.get('price') is not None and r.get('price') is not None and previous.get('currency')==r.get('currency'):
        before=Decimal(str(previous['price']));after=Decimal(str(r['price']))
        if before>after:
            pct=(before-after)/before*100 if before else Decimal(0)
            lines.append(f'Observed decrease: {money(before-after,r.get("currency","EUR"))} ({pct:.1f}%), from {money(before,r.get("currency","EUR"))}')
    if r.get('price_basis')=='MARKET_DISPLAY': lines.append('Vinted market display; seller-price change and original seller currency unverified. FX may affect the display.')
    if event=='DISPLAY_PRICE_DECREASE_UNVERIFIED': lines.append('Displayed price decreased; seller price reduction NOT established.')
    lines.append(f'Specifications: {r.get("classification","UNKNOWN")} | Price assessment: {policy["deal_state"]}')
    lines.append(f'Availability: {r.get("availability","UNKNOWN")} | Delivery: {r.get("delivery","UNKNOWN")}')
    if r.get('cost_complete') and r.get('delivered_eur') is not None: lines.append('Delivered estimate: '+money(r['delivered_eur'])+' (recorded components; verify current charges)')
    else: lines.append('Delivered cost: INCOMPLETE — unknown charges are not zero.')
    lines.append('Seller location: '+short(r.get('seller_location'),100)+' | Condition: '+short(r.get('condition'),60))
    lines.append('Specs evidence: '+(short(stamp,60)+' — '+age_text(age)+' at alert creation' if stamp else 'detail page not checked'))
    lines.append('Latest observation: '+short(r.get('observed_at'),60))
    missing=[]
    if stale: missing.append('fresh detail specifications')
    if r.get('availability')!='AVAILABLE_CONFIRMED' or stale: missing.append('current availability')
    if r.get('delivery','UNKNOWN')=='UNKNOWN': missing.append('delivery route')
    missing += [COST_NAMES.get(p.get('name'),p.get('name','charges')) for p in r.get('costs',[]) if p.get('eur') is None]
    if not r.get('cost_complete') and not any(p.get('eur') is None for p in r.get('costs',[])): missing.append('complete delivered charges')
    if not r.get('seller_location'): missing.append('seller location')
    if not r.get('seller_country'): missing.append('seller country')
    if r.get('power_adapter') in (None,'UNKNOWN'): missing.append('included compatible power adapter')
    if r.get('storage') in (None,'UNKNOWN'): missing.append('storage configuration')
    if r.get('idle_power_w') is None: missing.append('measured device idle power')
    if r.get('ac_recovery') in (None,'UNKNOWN'): missing.append('automatic recovery after power loss')
    missing += [FLAGS.get(x,x.replace('_',' ').lower()) for x in r.get('configuration_flags',[])]
    if missing: lines.append('Needs checking: '+short('; '.join(dict.fromkeys(missing)),900))
    lines.append('Link: '+str(r.get('url') or 'UNKNOWN'))
    return '\n'.join(lines)

def notification_body(report,events):
    if not events: return report
    body='\n\n'.join(format_alert(r,event,old) for r,event,old in events)
    failures=[line for line in report.splitlines() if line.startswith('Source ') and any(state in line for state in ('FAILURE','BLOCKED','RATE_LIMIT','LOGIN_REQUIRED','UNAVAILABLE','PARTIAL_CHECK'))]
    return body+('\n\nSource limitations:\n'+'\n'.join(failures) if failures else '')

def utf16_units(text): return len(text.encode('utf-16-le'))//2

def message_chunks(text,limit=3500):
    """Prefer line boundaries, never split a Unicode code point or exceed Telegram units."""
    if limit<2: raise ValueError('Chunk limit must allow a Unicode code point')
    chunks=[];current='';units=0
    for line in text.splitlines(keepends=True):
        if current and units+utf16_units(line)>limit:
            chunks.append(current);current='';units=0
        for char in line:
            size=utf16_units(char)
            if units+size>limit: chunks.append(current);current='';units=0
            current+=char;units+=size
    if current: chunks.append(current)
    return chunks or ['']
