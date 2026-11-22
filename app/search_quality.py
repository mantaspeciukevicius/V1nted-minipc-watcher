"""Measured search yield with bounded exploitation and guaranteed round-robin exploration.

History is stored in existing app_settings. Access failures are not zero-result searches.
"""
import json,math,os,re
from cpu_policy import policies, minimum_ram
from datetime import datetime,timezone

def key(term): return re.sub(r'\s+',' ',term.strip().casefold())
def load(c,market):
    row=c.execute('SELECT value FROM app_settings WHERE key=?',('search_quality:'+market,)).fetchone()
    return json.loads(row[0]) if row else {}

def setting(c,name):
    row=c.execute('SELECT value FROM app_settings WHERE key=?',(name,)).fetchone();return int(row[0]) if row else 0

def choose_terms(c,market,terms,count,cfg,cursor_key):
    pool=list({key(t):t for t in terms if t.strip()}.values());count=min(max(0,count),len(pool))
    if not count: return []
    if c is None: return pool[:count]
    cursor=setting(c,cursor_key);calls=setting(c,'adaptive_runs:'+market);stats=load(c,market)
    every=max(2,int(cfg.get('adaptive_every',4)));minimum=max(2,int(cfg.get('adaptive_min_successes',3)))
    eligible=[t for t in pool if stats.get(key(t),{}).get('successes',0)>=minimum and stats[key(t)].get('ema_yield',0)>0]
    exploit=bool(cfg.get('adaptive_search',True) and (calls+1)%every==0 and eligible)
    explore_count=count-1 if exploit else count
    chosen=[]
    for _ in range(explore_count):
        for _ in range(len(pool)):
            term=pool[cursor%len(pool)];cursor+=1
            if term not in chosen: chosen.append(term);break
    if exploit:
        # No reward survives indefinitely: stale successful measurements decay.
        def score(term):
            row=stats[key(term)];stamp=row.get('last_success')
            try: days=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds()/86400)
            except (TypeError,ValueError): days=365
            return row['ema_yield']*math.exp(-days/30)
        available=[t for t in eligible if t not in chosen]
        if available: chosen.append(max(available,key=lambda t:(score(t),-pool.index(t))))
        else:
            for _ in range(len(pool)):
                term=pool[cursor%len(pool)];cursor+=1
                if term not in chosen: chosen.append(term);break
    c.execute('INSERT OR REPLACE INTO app_settings VALUES(?,?)',(cursor_key,str(cursor)))
    c.execute('INSERT OR REPLACE INTO app_settings VALUES(?,?)',('adaptive_runs:'+market,str(calls+1)));c.commit()
    return chosen

def useful(r,at):
    if not r.get('details_confirmed') or r.get('classification') not in {'VERIFIED_MATCH','LIKELY_MATCH_UNVERIFIED'} or r.get('ram_gb',0) is None or r.get('ram_gb',0)<minimum_ram(): return False
    if policies().get(r.get('cpu'),{}).get('status')!='approved': return False
    if r.get('availability') in {'SOLD','RESERVED','PURCHASE_IN_PROGRESS','REMOVED','ACCESS_BLOCKED'}: return False
    try:
        stamp=datetime.fromisoformat(r.get('specs_observed_at') or r['observed_at'])
        return stamp.tzinfo is not None and 0<=(at-stamp).total_seconds()<int(os.getenv('VERIFICATION_TTL_HOURS','24'))*3600
    except (TypeError,ValueError,KeyError): return False

def record_run(c,statuses,records,known_ids,at=None):
    at=at or datetime.now(timezone.utc);by_id={r['id']:r for r in records};associations={};queries=[]
    for s in statuses:
        if s.get('marketplace') not in {'vinted','skelbiu'} or not s.get('search_term'): continue
        term=key(s['search_term']);queries.append((s['marketplace'],term,s))
        if s['state'] in {'AUTHORIZED_BROWSER_CHECK','NO_USABLE_RESULTS'}:
            for ident in set(s.get('listing_ids',[])): associations.setdefault(ident,set()).add((s['marketplace'],term))
    caches={}
    for market,term,s in queries:
        if market not in caches: caches[market]=load(c,market)
        stats=caches[market];old=stats.get(term,{})
        row=dict(old);row['term']=s['search_term'];row['checks']=row.get('checks',0)+1;row['last_checked']=at.isoformat();row['last_state']=s['state']
        success=s['state'] in {'AUTHORIZED_BROWSER_CHECK','NO_USABLE_RESULTS'}
        row['successes']=row.get('successes',0)+int(success);row['failures']=row.get('failures',0)+int(not success)
        if success:
            ids=set(s.get('listing_ids',[]));valid=[i for i in ids if i in by_id and useful(by_id[i],at)]
            qualifying=[i for i in valid if by_id[i].get('deal_state')=='WITHIN_CPU_TARGET']
            credit=lambda items:sum(1/len(associations[i]) for i in items)
            new_valid=credit([i for i in valid if i not in known_ids]);new_qualified=credit([i for i in qualifying if i not in known_ids])
            duration=max(0,float(s.get('duration_seconds',0)))
            measured=dict(raw_listings=max(0,int(s.get('raw_count',0))),candidate_hits=len(ids),duplicate_hits=max(0,int(s.get('duplicate_count',0))),new_candidates=sum(i not in known_ids for i in ids),useful_hits=len(valid),within_target_hits=len(qualifying),new_useful_credit=new_valid,new_within_target_credit=new_qualified,seconds=round(duration,3))
            for name,value in measured.items(): row[name]=row.get(name,0)+value
            # Useful means recent detail-backed hardware, not a visible card or confirmed delivery.
            reward=(4*new_qualified+2*new_valid+0.5*credit(valid)+0.1*credit([i for i in ids if i not in known_ids]))/max(duration,1)
            row['ema_yield']=round(0.75*row.get('ema_yield',0)+0.25*reward,8);row['last_success']=at.isoformat();row['last_measurement']=measured
        # Failure leaves the learned yield intact: blocked access is not an empty catalogue.
        stats[term]=row
    for market,stats in caches.items(): c.execute('INSERT OR REPLACE INTO app_settings VALUES(?,?)',('search_quality:'+market,json.dumps(stats,sort_keys=True)))
    return {market:len(stats) for market,stats in caches.items()}

def statistics(c,source='all'):
    rows=[]
    for market in ('vinted','skelbiu'):
        if source not in {'all',market}: continue
        rows += [dict(value,marketplace=market) for value in load(c,market).values()]
    return sorted(rows,key=lambda r:(r['marketplace'],-r.get('ema_yield',0),r['term']))

def summary(c):
    lines=[]
    for market in ('vinted','skelbiu'):
        rows=statistics(c,market)
        if not rows: lines.append(f'{market} search yield: collecting measurements');continue
        top=[r for r in rows if r.get('useful_hits',0)>0][:3]
        if top: lines.append(market+' lifetime productive terms: '+', '.join(f'{r["term"]} ({r.get("useful_hits",0)} detail-backed hits)' for r in top))
        else: lines.append(f'{market} search yield: {sum(r["successes"] for r in rows)} successful term checks since tracking began; no detail-backed matches recorded')
    return lines
