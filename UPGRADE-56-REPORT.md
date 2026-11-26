> Historical implementation/research record. Current deployment and later changes: [PROJECT.md](PROJECT.md) and [DEPLOYMENT.md](DEPLOYMENT.md). Test totals and publication statements below apply to the original report, not the latest version.

# Upgrade 5/6 — deployed 2026-11-20

Implemented clearer Telegram alerts and ongoing search validation in the existing application.

## Assessment and preservation
Baseline: 223 passing tests, healthy existing multi-marketplace service. Installation has no Git metadata, so no branch/commit is available and nothing was pushed. Existing credentials, CPU ceilings, scheduler and Docker hardening were preserved. Original files are in `backups/upgrade-56-original/`.

## Changes
- Evidence-aware event alerts: CPU ceiling and difference, first/lowest observed asking price, observed decrease amount/percentage, specification evidence timestamp/age, availability/delivery and explicit verification gaps. Vinted display/FX caveats remain explicit. Event notifications retain source failure summaries; full check reports remain local.
- Unicode-safe Telegram chunks for new reports. Legacy pending messages keep original boundaries and persisted part receipts. Existing outbox delivery/retry and quiet-check/daily-summary policy remain.
- Per-term persistent metrics: successful/failed checks, raw listings, candidate/duplicate hits, fresh detail-backed useful hits, new qualifying credit and duration. Duplicate discoveries share credit. Failed access is not learned as an empty result. Fresh approved CPU/RAM evidence is required for useful-hit credit.
- Bounded adaptive rotation: after three successful measurements, one rotating slot every fourth run can favor productive terms. Other slots continue round-robin coverage; measurements decay over time. Existing query/detail/time budgets remain.
- `search-stats [--source all|vinted|skelbiu]` command and daily productive-term summaries. Configuration switches are documented in README. Metrics use existing SQLite app_settings; no schema migration or history rewrite.
- Expanded captured Skelbiu HTML and Vinted card fixtures, with provenance. Offline edge cases are explicitly synthetic.

## Validation
248 automated tests pass on host and inside the rebuilt image; no failed or skipped tests. New tests cover price-target differences, evidence gaps/age, price/FX messaging, Unicode splitting, source-error retention, access-failure learning, duplicate credit, stale/unverified/unsupported hardware, source isolation, round-robin coverage and captured fixture replay.

Live run `5e145383-cb18-4ced-92cc-d4928bc66759` completed in 133.646 seconds, outcome `AUTHORIZED_BROWSER_CHECK`. Four Vinted searches extracted 402 raw card identities across terms; three Skelbiu searches extracted 52 classified identities across terms. These are per-term counts, not unique deals. Five normalized observations were recorded (two Vinted, three Skelbiu); four needed manual review and one was rejected. No qualifying new deal or notification event occurred. Both sources actually extracted data, with no access restriction reported this run. Seven query metrics were persisted.

## Deployment and recovery
Existing Docker service rebuilt and recreated; health check passes. Database integrity is `ok`, foreign-key violations zero. Backup integrity verified before and after deployment; post-deployment backup: `watcher-20261120T151736.sqlite`. Baseline listing/history/report/outbox primary keys remain present. Telegram remains enabled, with zero pending outbox entries; no synthetic Telegram preview was sent. Next scheduled check at verification: `2026-11-20T17:30:00+02:00`; daily summary remains 19:00 Europe/Vilnius.

## Limits
Search learning is starting with real measurements; no term has sufficient productive history for preferential selection yet. A useful hit is a fresh hardware-evidence metric, not proof of availability or delivery. Vinted fixtures replay extracted cards rather than a full page; Skelbiu fixtures retain actual classified anchor markup. Website changes can still require parser updates. Live checking did not exercise a new real Telegram event; formatting and retry behavior are tested with offline mocks. All existing access restrictions and bounded public-browser behavior remain.

Evidence: `logs/upgrade-56-tests.txt`, `logs/upgrade-56-container-tests.txt`, `logs/upgrade-56-live-check.txt`, `logs/upgrade-56-search-stats.json`, `logs/upgrade-56-status.json`.
