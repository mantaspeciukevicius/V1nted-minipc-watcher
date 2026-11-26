> Historical implementation/research record. Current deployment and later changes: [PROJECT.md](PROJECT.md) and [DEPLOYMENT.md](DEPLOYMENT.md). Test totals and publication statements below apply to the original report, not the latest version.

# Daily decision reporting and 12 GB minimum — 2026-11-22

Implemented, regression-tested, deployed and published to the existing GitHub repository.

## Changes

- Installed RAM eligibility is now **12 GB or more**, configurable with `MIN_RAM_GB`. Parsing covers 12 GB variants, 12288 MB, paired modules and explicit 8 GB + 4 GB configurations, with broader valid capacities. Maximum supported RAM, optional upgrades and storage do not qualify. CPU purchase ceilings remain unchanged.
- The daily Telegram summary contains daily-only search counts, measured discovery/detail/hardware/price funnels, exclusive primary review blockers, suitable above-budget hardware and fresh/stale stored evidence. It no longer appends the duplicate technical report or disabled-source boilerplate. Full per-check reports remain local.
- Initial availability observations are separate from state transitions, including transition destinations. Source failures identify the affected term and require a later successful check of that same term to claim recovery.
- Lifetime search-quality statistics remain available separately. New per-check funnel counts are persisted in existing JSON fields; old windows reconstruct available measures from recorded observations and explicitly warn about incomplete historical attempt telemetry.
- Within-budget and near-budget hardware receives verification priority. Unsupported and far-above-target (>150% of CPU ceiling) known listings refresh at a configurable 24-hour interval. New-discovery reservations, normal candidate cooldowns and price-crossing overrides remain.
- `preview-daily [--at TIMESTAMP]` renders without recording a report or queuing/sending a notification. It uses evidence before the specified boundary, rather than later snapshots.

## Verification

Baseline: 248 tests passed. Updated suite: **287 tests pass**, including all prior tests and 39 new regressions, on host, inside the rebuilt image and in the publication copy. Tests cover RAM policy and storage distinction, priority/cooldowns, daily versus lifetime totals, review reasons, availability transitions/timezone offsets, source recovery, preview isolation and preserved daily deduplication/DST behavior.

Live run `bbba742d-6baa-480b-9f91-bbcd154937fd` completed in 169.635 seconds with `AUTHORIZED_BROWSER_CHECK`:

- Vinted: 4/4 searches successful, 430 raw card identities across terms, four successful detail checks.
- Skelbiu: 3/3 searches successful, 62 raw classified identities across terms, two successful detail checks.
- Both sources actually extracted listing data. Seven observations required review and two were rejected; no qualifying new deal or notification event occurred. No claim is made that a real 12 GB deal was found.

Container: running and healthy. Database integrity: `ok`, foreign-key violations zero. All baseline listing, observation, price-history, availability-history, report and outbox primary keys remain present. Outbox: no pending messages; Telegram remains enabled. Next scheduled check at verification: 23:30 Europe/Vilnius. The existing 19:00 summary was not resent.

Verified backups: `watcher-20261122T211531.sqlite` before deployment and `watcher-20261122T211901.sqlite` afterward. Original source/config/tests are preserved in `backups/upgrade-report-12gb-original/`. Only the non-secret `MIN_RAM_GB` setting changed in `.env`; all other environment bytes were compared and verified unchanged. No schema migration, unrelated service change or credential rotation was performed.

## Historical preview

The rewritten 2026-11-22 daily preview shows 189/190 successful Vinted and 141/142 successful Skelbiu term checks, replacing misleading lifetime totals of 394 and 294. It explains the 51 stored candidates with primary review reasons, reports 38 with fresh detail evidence and 13 stale/unverified, and distinguishes 10 first availability observations from five actual changes to unknown. Both source errors are shown as subsequently recovered.

Preview: `logs/upgrade-report-12gb-deployed-preview.txt` (rendered locally without Telegram).

Older records are not silently promoted or assigned fresh evidence by the RAM policy change. Revalidation on subsequent detail checks applies the new eligibility rule; immutable observations and prior notifications remain intact.

## GitHub

Published to `mantaspeciukevicius/V1nted-minipc-watcher`, branch `main`, commit `43a4bd6eae2e97cfb5f12f8b34eee911aa79cfae`. All 12 updated/added public files match the reviewed publication copy. Pre-publication secret scan: zero findings. Runtime state, credentials and operational backups were excluded.
