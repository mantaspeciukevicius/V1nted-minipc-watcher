> Historical implementation/research record. Current deployment and later changes: [PROJECT.md](PROJECT.md) and [DEPLOYMENT.md](DEPLOYMENT.md). Test totals and publication statements below apply to the original report, not the latest version.

# Upgrade 1–3: deployment report

Verified 2026-11-20T15:00:03.078531+00:00.

## Implemented

1. **Prioritized detail checks.** Both adapters gather their bounded search pages before ranking detail candidates. CPU-specific price/value and supported hardware guide selection. At least 60% of slots are reserved for new discovery when sufficient candidates are present; known rechecks are capped (Vinted 3, Skelbiu 2). Ordinary above-target detail openings are capped at one per source/run. Existing request pauses, sequential Chromium execution and time/detail budgets remain.
2. **Stronger configuration parsing.** Added Lithuanian/Polish installed-vs-supported RAM and optional-upgrade wording, missing RAM/storage/power-adapter evidence, multiple configuration prices, and defective-unit rejection. Shipping-price lines alone no longer imply multiple computers. Flags are stored and reported. Search cards preserve dated detail evidence and explicitly retain contradictory fresh claims rather than renewing old verification or assuming delivered charges remain valid. Legacy detail evidence can be recovered from history without rewriting it. A known card that first becomes a qualifying configuration after detail verification now produces a candidate event once.
3. **Price-drop watchlists.** Known candidates normally wait two hours between detail attempts; above-target recognized CPUs wait six hours. Attempts persist across restarts. Fresh target crossings and newly conflicting/missing-component claims can request earlier detail verification; failed override attempts back off for one hour. Actual same-currency asking-price decreases trigger target-crossing alerts; policy/FX-only changes do not become seller-price drops. History remains intact and routine checks remain quiet.

Watchlist commands:

```sh
docker exec vinted-minipc-watcher python /app/monitor.py watchlist
docker exec vinted-minipc-watcher python /app/monitor.py watchlist --source skelbiu
```

`detail_eligible_after` is eligibility for a later bounded run, not a guaranteed check appointment. Current suitable above-target watchlist count: 0. Incomplete configurations remain stored but are excluded from this suitable-hardware view.

## Validation

- Baseline: **187 tests passing**. Final: **223 tests passing**, including in the deployed container; no failures or skips.
- Added 36 offline regressions covering selection/reservations, restart-safe cooldowns, threshold crossings and duplicate suppression, configuration languages, card conflicts/evidence age, legacy history recovery, monetary evidence and delayed RAM verification.
- Isolated real checks succeeded for both sources using a database copy and disabled Telegram. Vinted correctly deferred known records; a separate bounded check explicitly exercised one Vinted detail page. Skelbiu opened two selected detail pages.
- Production post-deployment check: **AUTHORIZED_BROWSER_CHECK**. Vinted completed four search-page checks, deferred 12 known records and opened zero details under cooldown. Skelbiu completed three searches, deferred seven known records and opened two selected details. Four unique observations were stored; no qualifying new deal or price-drop event was established. Both source-health states are OK.
- Production check duration: 112.985 seconds; container CPU: 95.54 seconds; container-lifetime peak memory: 1126850560 bytes, within the existing 1.5 GiB limit. This is resource telemetry, not wall-power consumption.

## Deployment and data

- Existing service rebuilt and recreated in place. Container: **running healthy**. Image: `sha256:bc519d05afc4c3be91370110df0575793d0c27b5c22a4748875f7b09356161cf`.
- SQLite integrity **ok**; foreign-key errors **0**. Across listings, observations, prices, availability, reports, alerts and outbox records: **0 original rows lost**.
- CPU policy byte-for-byte unchanged: **True**. Compose/security/resource configuration byte-for-byte unchanged: **True**. Credentials were not edited or printed.
- Schedule remains HH:00/HH:30 Europe/Vilnius. Next check from status: **2026-11-20T17:30:00+02:00**; daily summary **2026-11-20T19:00:00+02:00**. No second scheduler or persistent service was created.
- Existing Telegram enabled; pending outbox **0**. No synthetic test message was sent.
- Original verified database backup: `backups/watcher-20261120T144349.sqlite`; latest: `backups/watcher-20261120T150002.sqlite` (integrity **ok**). Original code/config: `backups/upgrade-123-original/`.
- No schema migration was needed: attempt timestamps use existing `app_settings`; extra evidence uses existing JSON observations. No historical observations were rewritten.
- Installed tree has no Git metadata; no branch/commit was created or pushed.

## Limits and operations

Discovery remains first-page and bounded. Language heuristics remain conservative and may require manual review; unknown specifications, availability, delivery and idle power remain unknown. Cooldowns reduce detail requests, while fresh price cards can still discover a crossing earlier. Rechecks are subject to source access and available run capacity. Existing access restrictions and independent source failure handling are preserved; no CAPTCHA solving, proxy rotation, login bypass or paid scraping service was added.

Configuration and operating details are in [README.md](README.md). Verification data and captured run summaries are under `logs/upgrade-123-*`.
