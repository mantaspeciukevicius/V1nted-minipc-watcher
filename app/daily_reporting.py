"""Daily decision summary, measured funnels and conservative verification reasons.

No browser activity, notification sending or historic evidence mutation occurs here.
"""
import collections,json,re
from datetime import datetime,timezone,timedelta
from cpu_policy import assessment,policies,minimum_ram,cpu_models
from search_quality import useful

FAILURES={'ACCESS_BLOCKED','PARSING_FAILURE','PARTIAL_CHECK','SEARCH_PROVIDER_FAILURE','RATE_LIMIT','SOURCE_UNAVAILABLE','LOGIN_REQUIRED','UNAVAILABLE'}
SUCCESS={'AUTHORIZED_BROWSER_CHECK','NO_USABLE_RESULTS'}
DEAD={'SOLD','RESERVED','PURCHASE_IN_PROGRESS','REMOVED'}
REASONS={'CPU_CONFLICT':'conflicting CPUs','CPU_UNKNOWN':'CPU unidentified','CPU_UNSUPPORTED':'CPU awaiting approval','RAM_UNKNOWN':'installed RAM unclear','RAM_LOW':'RAM below minimum','INCOMPLETE':'incomplete/defective system','MULTIPLE_CONFIGURATIONS':'configuration price unclear','STALE':'stale/missing detail evidence','OTHER_REVIEW':'form factor/configuration review','QUALIFIED':'hardware requirements met'}

def market_of(s):
    if s.get('marketplace') in {'vinted','skelbiu'}: return s['marketplace']
    source=s.get('source','')
    return 'vinted' if source.startswith('authorized_browser') else 'skelbiu' if source=='skelbiu' else None

def fresh(r,at):
    if not r.get('details_confirmed'):return False
    try:
        stamp=datetime.fromisoformat(r.get('specs_observed_at') or r['observed_at'])
        import os
        return stamp.tzinfo is not None and 0<=(at-stamp).total_seconds()<int(os.getenv('VERIFICATION_TTL_HOURS','24'))*3600
    except (TypeError,ValueError,KeyError):return False

def reason(r,at):
    models=cpu_models(r.get('title','')+'\n'+r.get('description',''))
    if len(models)>1:return 'CPU_CONFLICT'
    if not r.get('cpu'):return 'CPU_UNKNOWN'
    if policies().get(r['cpu'],{}).get('status')!='approved':return 'CPU_UNSUPPORTED'
    if r.get('ram_gb') is None:return 'RAM_UNKNOWN'
    if r['ram_gb']<minimum_ram():return 'RAM_LOW'
    flags=set(r.get('configuration_flags',[]))
    if flags & {'RAM_NOT_INSTALLED','OPTIONAL_CONFIGURATION','STORAGE_MISSING','POWER_ADAPTER_MISSING','DEFECTIVE'}:return 'INCOMPLETE'
    if 'MULTIPLE_CONFIGURATION_PRICES' in flags:return 'MULTIPLE_CONFIGURATIONS'
    if not fresh(r,at):return 'STALE'
    if r.get('classification') not in {'VERIFIED_MATCH','LIKELY_MATCH_UNVERIFIED'}:return 'OTHER_REVIEW'
    return 'QUALIFIED'

def funnel(statuses,records,at=None):
    at=at or datetime.now(timezone.utc);result={}
    for market in ('vinted','skelbiu'):
        selected=[s for s in statuses if market_of(s)==market];queries=[s for s in selected if s.get('search_term')]
        rs={r['id']:r for r in records if r['id'].startswith(market+':')};ids={i for s in queries for i in s.get('listing_ids',[])}
        detailed=[r for r in rs.values() if r.get('source') in {'authorized_browser_detail','skelbiu_detail','manual_import'} and r.get('details_confirmed')]
        hardware=[r for r in detailed if useful(r,at)]
        result[market]={'term_attempts':len(queries),'term_successes':sum(s['state'] in SUCCESS for s in queries),'term_failures':sum(s['state'] in FAILURES for s in queries),'raw_cards':sum(s.get('raw_count',0) for s in queries),'relevant_candidates':len(ids),'duplicate_hits':sum(s.get('duplicate_count',0) for s in queries),'detail_attempts':sum(s.get('details_attempted',0) for s in selected),'detail_successes':len(detailed),'hardware_matches':len(hardware),'navigation_retries':sum(len(s.get('navigation_retry_events',[])) for s in selected),'retry_recoveries':sum(bool(e.get('recovered')) for s in selected for e in s.get('navigation_retry_events',[])),'browser_restarts':sum(e.get('action')=='restart browser' for s in selected for e in s.get('navigation_retry_events',[])),'within_target':sum(assessment(r.get('cpu'),r.get('asking_eur'),r['classification'])['deal_state']=='WITHIN_CPU_TARGET' for r in hardware)}
    return result

def availability_counts(c,start,end):
    previous={};counts=collections.Counter(initial=0,transitions=0,unchanged=0);destinations=collections.Counter()
    rows=c.execute('SELECT listing_id,observed_at,state,id FROM availability_history').fetchall()
    for r in sorted(rows,key=lambda r:(datetime.fromisoformat(r[1]),r[3])):
        ident,stamp,state,_=r;when=datetime.fromisoformat(stamp)
        if when>=end:continue
        if start<=when<end:
            category='initial' if ident not in previous else 'transitions' if previous[ident]!=state else 'unchanged';counts[category]+=1
            if category=='transitions':destinations[state]+=1
        previous[ident]=state
    return dict(counts),dict(destinations)

def failure_lines(runs):
    events=[];issues=collections.defaultdict(list)
    for run in runs:
        for s in json.loads(run['sources'] or '[]'):
            market=market_of(s)
            if not market and s['state'] in FAILURES: market=s.get('source','pipeline')
            if not market:continue
            events.append((run['completed'],s,market))
    for index,(stamp,s,market) in enumerate(events):
        if s['state'] not in FAILURES:continue
        term=s.get('search_term');recovered=any(m==market and newer>stamp and x['state'] in SUCCESS and (not term or x.get('search_term')==term) for newer,x,m in events[index+1:])
        # Only a compact diagnostic class is sent; raw errors can contain URLs/data.
        error=s.get('error','');kind='navigation timeout' if 'timeout' in error.lower() else s['state'].lower().replace('_',' ')
        safe_term=re.sub(r'[^\w -]','',str(term or 'source'))[:32]
        issues[(market,safe_term,kind)].append(recovered)
    return [f'{m} / {term}: {kind} ({len(states)}); '+('recovered in a later check' if all(states) else 'not yet confirmed recovered' if not any(states) else 'some recovered; latest recovery unconfirmed') for (m,term,kind),states in sorted(issues.items())]

def build(c,slot,start,end,runs,matches,alerts,confirmed):
    at=end;lines=[f'DAILY MINI PC REPORT — {slot.isoformat()}',f'Window: {start.astimezone(slot.tzinfo).isoformat()} → {slot.isoformat()}',f'Installed RAM minimum: {minimum_ram()} GB; CPU price ceilings unchanged.']
    bad=sum(run['outcome']=='PARTIAL_CHECK' for run in runs)
    lines.append(f'Check cycles completed: {len(runs)}; partial/failed: {bad}.')
    new={a['listing_id'] for a in alerts if a['event'] in {'NEW_VERIFIED_MATCH','NEW_UNVERIFIED_CANDIDATE'}}
    lines.append(f'New qualifying candidates: {len(new)}; seller price drops: {sum(a["event"]=="PRICE_DROP" for a in alerts)}; unverified displayed decreases: {sum(a["event"]=="DISPLAY_PRICE_DECREASE_UNVERIFIED" for a in alerts)}.')
    totals={market:collections.Counter() for market in ('vinted','skelbiu')};unique={market:set() for market in totals};legacy=0
    for run in runs:
        counts=json.loads(run['counts'] or '{}');per_run=counts.get('funnel');sources=json.loads(run['sources'] or '[]')
        if per_run is None:
            legacy+=1
            # Historical fallback uses recorded observations, never current snapshots.
            observations=[json.loads(x[0]) for x in c.execute('SELECT body FROM listing_observations WHERE observed_at>=? AND observed_at<=?',(run['started'],run['completed']))]
            per_run=funnel(sources,observations,datetime.fromisoformat(run['completed']))
        for market in totals:
            totals[market].update(per_run.get(market,{}));unique[market].update(i for s in sources if market_of(s)==market for i in s.get('listing_ids',[]))
    current={};review={};watch={};fresh_candidates=0
    for market in totals:
        rs=[r for r in matches if r['id'].startswith(market+':')];current[market]=rs;t=totals[market]
        lines.append(f'{market}: searches {t["term_successes"]}/{t["term_attempts"]} successful; cards {t["raw_cards"]}; relevant {len(unique[market])} unique; details {t["detail_successes"]} successful / {t["detail_attempts"]} attempted; hardware matches {t["hardware_matches"]}; within budget {t["within_target"]}.')
        if t['navigation_retries']:lines.append(f'{market} recovery: {t["navigation_retries"]} bounded retries; {t["retry_recoveries"]} recovered; browser restarts {t["browser_restarts"]}.')
        reasons=collections.Counter(reason(r,at) for r in rs);review[market]=dict(reasons)
        summary=[f'{REASONS[k]} {v}' for k,v in reasons.items() if k!='QUALIFIED']
        if summary:lines.append(market+' review — '+'; '.join(summary)+'.')
        suitable=[r for r in rs if reason(r,at)=='QUALIFIED'];within=[r for r in suitable if assessment(r.get('cpu'),r.get('asking_eur'),r['classification'])['deal_state']=='WITHIN_CPU_TARGET'];above=[r for r in suitable if assessment(r.get('cpu'),r.get('asking_eur'),r['classification'])['deal_state'] in {'ABOVE_CPU_TARGET','ABOVE_HARD_LIMIT'}];watch[market]=len(above)
        all_above=sum(assessment(r.get('cpu'),r.get('asking_eur'),r['classification'])['below_target_eur'] is not None and assessment(r.get('cpu'),r.get('asking_eur'),r['classification'])['below_target_eur']<0 for r in rs)
        lines.append(f'{market} current: fresh qualifying hardware within budget {len(within)}; suitable above-budget watchlist {len(above)}; above CPU ceiling including unresolved configurations {all_above}.')
        fresh_candidates+=sum(fresh(r,at) for r in rs)
    lines.append('Cards count across terms; hardware/detail counts are observations, not unique deals. Review reasons are exclusive primary blockers.')
    if legacy:lines.append(f'Historical funnel reconstructed for {legacy} checks; unavailable detail-attempt counters may be incomplete.')
    changes,dest=availability_counts(c,start,end)
    lines.append(f'Availability: {changes["initial"]} first observations; {changes["transitions"]} actual changes'+(' ('+', '.join(f'{k.lower()} {v}' for k,v in sorted(dest.items()))+')' if dest else '')+'.')
    lines.append(f'Stored candidates: {len(matches)}; fresh detail evidence: {fresh_candidates}; stale/unverified: {len(matches)-fresh_candidates}; fully confirmed: {sum(confirmed(r) for r in matches)}.')
    errors=failure_lines(runs)
    lines.extend(['Source issues: '+str(len(errors))+' affected query/error groups.']+errors if errors else ['Source issues: none in this window.'])
    lines.append(f'Uses checks completed before {slot.strftime("%H:%M")}; that slot’s browser check runs afterward. Missing delivery/cost evidence remains unknown.')
    metrics={'notification_format':2,'report_version':3,'funnel':{k:dict(v) for k,v in totals.items()},'review_reasons':review,'watchlist':watch,'availability':changes,'availability_destinations':dest,'legacy_funnel_runs':legacy,'source_issue_groups':len(errors),'stored_candidates':len(matches),'fresh_detail_candidates':fresh_candidates}
    return '\n'.join(lines),metrics,'PARTIAL_CHECK' if bad or errors else 'AUTHORIZED_BROWSER_CHECK' if runs else 'NO_USABLE_RESULTS'
