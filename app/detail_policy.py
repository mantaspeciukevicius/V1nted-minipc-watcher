"""Shared bounded detail planning and persistent watchlist cooldowns."""
import json, math
from datetime import datetime, timezone, timedelta
from cpu_policy import assessment, parse
DEAD={'SOLD','RESERVED','PURCHASE_IN_PROGRESS','REMOVED'}

def reassess(record):
    from configuration import evidence
    result=dict(record);cpu,ram,cls=parse(record.get('title','')+'\n'+record.get('description',''))
    result.update(cpu=cpu,ram_gb=ram)
    if result['classification']!='REJECTED' and cls in {'REJECTED','NEEDS_MANUAL_REVIEW'}: result['classification']=cls
    result['configuration_flags']=list(dict.fromkeys(record.get('configuration_flags',[])+evidence(record.get('title','')+'\n'+record.get('description',''))))
    result.update(assessment(cpu,result.get('asking_eur'),result['classification']))
    return result

def with_history(c,record):
    record=reassess(record)
    if record.get('details_confirmed') or record.get('source') not in {'authorized_browser_card','skelbiu_card'}: return record
    row=c.execute("SELECT body FROM listing_observations WHERE listing_id=? AND source IN ('authorized_browser_detail','skelbiu_detail','manual_import') ORDER BY observed_at DESC,id DESC LIMIT 1",(record['id'],)).fetchone()
    if not row: return record
    detail=json.loads(row[0])
    if not detail.get('details_confirmed'): return record
    merged=dict(detail)
    for key in ('price','currency','asking_eur','fx','observed_at','source','price_basis'):
        if key in record: merged[key]=record[key]
    merged['specs_observed_at']=detail.get('specs_observed_at') or detail['observed_at']
    if record['classification']=='REJECTED': merged['classification']='REJECTED'
    merged.update(assessment(merged.get('cpu'),merged.get('asking_eur'),merged['classification']))
    return reassess(merged)

def previous(c,marketplace):
    return {r['id']:with_history(c,r) for row in c.execute('SELECT current_json FROM listings WHERE id LIKE ?', (marketplace+':%',)) for r in [json.loads(row[0])]}

def last_attempt(c,record):
    row=c.execute('SELECT value FROM app_settings WHERE key=?',('detail_attempt:'+record['id'],)).fetchone()
    if row: return datetime.fromisoformat(row[0])
    if record.get('details_confirmed'): return datetime.fromisoformat(record.get('specs_observed_at') or record['observed_at'])
    return None

def mark_attempt(c,record,at=None):
    at=at or datetime.now(timezone.utc)
    c.execute('INSERT OR REPLACE INTO app_settings VALUES(?,?)',('detail_attempt:'+record['id'],at.isoformat()));c.commit()

def price_crossed(card,old):
    ceiling=assessment(old.get('cpu'),old.get('asking_eur'),old['classification'])['cpu_max_asking_eur']
    return (ceiling is not None and card.get('asking_eur') is not None and old.get('asking_eur') is not None
            and old['asking_eur']>ceiling>=card['asking_eur'] and card.get('currency')==old.get('currency'))

def changed_specs(card,old):
    if not card: return False
    changed=any(card.get(k) is not None and old.get(k) is not None and card[k]!=old[k] for k in ('cpu','ram_gb'))
    flags=set(card.get('configuration_flags',[]))-set(old.get('configuration_flags',[]))
    return changed or bool(flags & {'RAM_NOT_INSTALLED','OPTIONAL_CONFIGURATION','STORAGE_MISSING','POWER_ADAPTER_MISSING','DEFECTIVE'})

def due(c,record,cfg,at=None,card=None):
    at=at or datetime.now(timezone.utc)
    last=last_attempt(c,record)
    # A newly observed threshold crossing overrides the long watchlist cooldown,
    # but failed attempts are still backed off for one hour.
    if card and (price_crossed(card,record) or changed_specs(card,record)):
        detail_stamp=record.get('specs_observed_at') or (record.get('observed_at') if record.get('details_confirmed') else None)
        successful=detail_stamp and last and datetime.fromisoformat(detail_stamp)>=last
        return last is None or bool(successful) or at-last>=timedelta(hours=1)
    state=assessment(record.get('cpu'),record.get('asking_eur'),record['classification'])['deal_state']
    hours=cfg.get('above_target_recheck_hours',6) if above_target(record) else cfg.get('candidate_recheck_hours',2)
    return last is None or at-last>=timedelta(hours=max(1,float(hours)))

def above_target(record):
    ceiling=assessment(record.get('cpu'),record.get('asking_eur'),record['classification'])['cpu_max_asking_eur']
    return ceiling is not None and record.get('asking_eur') is not None and record['asking_eur']>ceiling

def priority(record,old=None):
    hardware=old if old and old.get('details_confirmed') else record
    policy=assessment(hardware.get('cpu'),record.get('asking_eur'),hardware['classification'])
    ceiling=policy['cpu_max_asking_eur'];price=record.get('asking_eur')
    ratio=price/ceiling if price is not None and ceiling else float('inf')
    crossing=bool(old and price_crossed(record,old))
    return (not (crossing or (old and changed_specs(record,old))),hardware['classification']=='REJECTED',ceiling is None,ratio>1,ratio>1.5,
            hardware.get('ram_gb') is not None and hardware['ram_gb']<16,ratio,record['id'])

def plan(c,discovered,tracked,cfg,at=None):
    at=at or datetime.now(timezone.utc);limit=int(cfg.get('max_details',5))
    fresh=[];known=[];deferred=0
    for ident,r in discovered.items():
        old=tracked.get(ident)
        if r['classification']=='REJECTED' or (old and old['availability'] in DEAD): continue
        if old and not due(c,old,cfg,at,r): deferred+=1;continue
        (known if old else fresh).append((r,old))
    for ident,r in tracked.items():
        if ident in discovered or r['classification']=='REJECTED' or r['availability'] in DEAD: continue
        if due(c,r,cfg,at): known.append((r,r))
        else: deferred+=1
    fresh.sort(key=lambda x:priority(*x));known.sort(key=lambda x:priority(*x))
    # Known listings can never consume the slots reserved for new discovery.
    known_limit=max(0,min(int(cfg.get('max_rechecks',max(1,limit//3))),limit))
    new_reserve=min(len(fresh),math.ceil(limit*0.6))
    selected=[];watch_count=0
    def watch(item):
        r,old=item;hardware=dict(old or r,asking_eur=r.get('asking_eur'))
        return above_target(hardware) and not (old and price_crossed(r,old))
    watch_limit=max(0,int(cfg.get('max_above_target_details',1)))
    for item in fresh:
        if len(selected)>=new_reserve: break
        if watch(item) and watch_count>=watch_limit: continue
        selected.append(item);watch_count+=watch(item)
    selected_ids={r['id'] for r,_ in selected}
    rest=sorted([x for x in fresh+known if x[0]['id'] not in selected_ids],key=lambda x:priority(*x));known_count=0
    for item in rest:
        if len(selected)>=limit: break
        r,old=item
        if old and known_count>=known_limit: continue
        state=assessment((old or r).get('cpu'),r.get('asking_eur'),(old or r)['classification'])['deal_state']
        is_watch=watch(item)
        if is_watch and watch_count>=watch_limit: continue
        selected.append(item);known_count+=bool(old);watch_count+=is_watch
    # Promising new listings are ordered first; crossing alerts outrank ordinary rechecks.
    selected.sort(key=lambda x:priority(*x))
    return [r for r,_ in selected],dict(detail_candidates=len(fresh)+len(known),selected_details=len(selected),cooldown_deferred=deferred,new_selected=sum(r['id'] not in tracked for r,_ in selected),known_selected=sum(r['id'] in tracked for r,_ in selected))
