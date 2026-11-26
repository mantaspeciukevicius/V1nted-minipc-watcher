> Historical implementation/research record. Current deployment and later changes: [PROJECT.md](PROJECT.md) and [DEPLOYMENT.md](DEPLOYMENT.md). Test totals and publication statements below apply to the original report, not the latest version.

# Vinted Tracker v2 — implementation and deployment report

Verified 2026-11-20T08:29:30.419595+00:00 UTC on the live LarkBox installation.

## Assessment

The application was already running and Docker-healthy, with the expected Python/Chromium/Playwright implementation, SQLite history, persistent outbox, timezone-aware scheduling and daily summary. It consists chiefly of `app/monitor.py` and `app/browser_source.py`; Compose retains a non-root, read-only container with writable state, dropped capabilities, resource limits and no public ports. The actual installation has no Git metadata; there is no branch or commit to report, and nothing was pushed.

The documented 115-test suite existed, but initially produced **113 passes and 2 failures** under production environment variables. These were buyer-market test isolation and validation-before-market-override issues. Both are corrected. The running configuration already used half-hourly checks, despite older hourly documentation.

## Implemented

- Added `skelbiu_source.py` and a fixture-tested classified-card parser. Both marketplaces feed the original normalization, SQLite history, event generation, reports and outbox. Chromium runs sequentially; no independent scheduler or second persistent service was created.
- Added namespaced Skelbiu identities; existing Vinted identities are unchanged. All original historical rows are retained. Existing JSON bodies and `app_settings` support the extension without SQL schema changes or a destructive migration. Fresh databases are covered by the tests.
- Added configurable policies for **23 approved CPUs**, preserving all eleven original ceilings and user-supplied comparison estimates. Additional ceilings: N300: €130; N305: €140; N350: €130; N355: €150; 5425U: €140; 4500U: €140; 4600U: €150; 5625U: €150; 7520U: €130; 7530U: €150; 5800U: €150; 5825U: €150. Evidence and rationale are in [CPU_RESEARCH.md](CPU_RESEARCH.md). N200/N250 remain searchable manual-review candidates after evaluation, with no automatic purchase ceiling. No new N100-relative performance percentages were invented.
- Separated hardware classification from price/deal state. N100 at €150 is above its €120 target; 5600U at €150 with 16 GB can qualify against its €150 ceiling. Above-target and above-hard-limit hardware is retained for later reductions; €175 remains the global qualification cap.
- Extended CPU aliases, Ryzen model recognition, installed-memory parsing (including paired modules and MB), capacity-only claims, optional upgrades, incomplete offers, contradictory CPUs, multi-configuration offers and unrelated-product rejection.
- Added rotating brand/CPU/generic searches. Vinted retains three frequent queries plus one rotating query, up to twelve details, with three reserved rechecks at most and a 300-second browser budget. Skelbiu uses N100 plus two rotating queries, up to five details and 150 seconds. Both use first pages and conservative pauses.
- Skelbiu detail parsing scopes description, price and location to listing containers; store placements are excluded. Explicit sold/inactive states, collection-only/collection-available evidence and explicit domestic shipping claims are distinguished. Unknown charges remain unknown. Refresh dates do not create new identities or alerts. Missing hardware metadata, idle consumption and BIOS recovery stay unknown without evidence.
- Added CPU-target crossing events, original/lowest comparable asking prices and last-decrease details while keeping the full price/availability histories. Vinted display changes remain unverified seller-price changes.
- Added marketplace/CPU-target information to notifications and per-marketplace daily counters. Existing retries, outbox parts, unchanged-listing suppression and 19:00 summary remain in place. No Telegram test message was forced.
- Added source selectors for `check` and `matches`; all old commands remain supported. Added per-check duration, cgroup CPU/memory/process counters and marketplace counts to stored run counts. Container-lifetime memory peak is explicitly labelled and never treated as electricity consumption.

## Tests and live verification

**187 automated tests pass, zero failed or skipped**, including inside the final installed container using the documented unittest command. Tests are offline and cover policies, parsing, captured real classified card markup, source identity, external adverts, threshold transitions, history, backups, independent adapter failures, outbox/retries and existing schedule/recovery cases. Final isolated dry-run and application health command succeed.

Live evidence:

- Initial isolated check: Vinted extracted 17 records and one detail observation; Skelbiu extracted 11 records and five detail observations.
- A production check found an optional Vinted cookie-dialog click timeout. The failure was recorded, Skelbiu continued, and the optional click was made non-fatal. A subsequent real Vinted-only check succeeded with 2 records and four successful search-page checks.
- The later combined check successfully extracted Vinted data and Skelbiu data, but exposed an empty brand search being conservatively labelled a parsing failure. Its explicit zero-results markers are now recognized; external store products remain excluded. The final Skelbiu-only check succeeded with **12 records**, three successful search pages, and no source error.
- Current source health: Vinted **OK**, Skelbiu **OK**, ECB **OK**; Brave remains intentionally disabled. No CAPTCHA, login, stealth, proxy, restriction bypass or Firecrawl usage was introduced.
- No fully confirmed deal was established. Current observations still require configuration and availability verification; the report does not represent visible listings as available delivered-price deals.

The historical partial checks remain in the database rather than being rewritten as successes. Browser budgets and first-page coverage are limits, not an assertion that the full catalogues were searched.

## Deployment and preservation

- Existing service rebuilt and recreated in place; persistent volumes, credentials, restart policy and Compose hardening preserved.
- Installed image: `sha256:1aca82ebab206b2e3129da646a78d261bbf7220b49508c45b4607ec9de8f9ef8`.
- SQLite integrity: **ok**; foreign-key violations: **0**.
- Original listing IDs retained: **31 of 31**. Current listing count: **59**. Across original observations, price/availability history, runs, alerts, outbox and sent parts: **zero lost original rows**. See `logs/v2-final-verification.json`.
- Monitoring enabled. Next scheduled check: **2026-11-20T10:30:00+02:00**. Daily summary: **2026-11-20T19:00:00+02:00**. Manual runs did not move the schedule.
- Telegram enabled with existing credentials; pending outbox: **0**. No new message was sent because no qualifying event was established. Retry and persistence behavior passed regression tests.
- Original integrity-checked backup: `backups/watcher-20261120T080414.sqlite`. Latest backup: `backups/watcher-20261120T082813.sqlite`, integrity **ok**. Original application/configuration tree: `backups/v2-assessment-20261120/`. Configuration credentials were not overwritten or printed.
- Latest measured Skelbiu check: elapsed 50.064 seconds, container CPU 33.813 seconds; post-check memory 82452480 bytes; container-lifetime peak 787292160 bytes. A separate active-browser sample reached 1.351 GiB within the existing 1.5 GiB limit; see `logs/v2-resource-sample.txt`.

## Remaining limitations

- CPU/nominal-power research does not prove a particular mini PC's idle consumption, Linux reliability, cooling, storage expandability or AC-loss recovery. Those fields require model-specific evidence.
- First-page rotating discovery is intentionally incomplete. Human-language and multi-product parsing remains conservative; uncertain configurations/prices require review. Platform-supplied shipping adverts do not establish seller shipping or its cost.
- Cross-marketplace listings remain separate. Automatic duplicate suggestions are deferred until reliable seller/model/image evidence is available; matching CPU/RAM never merges physical units.
- Source markup can change or access can be restricted. Each adapter reports failures independently, retains evidence, and stops at challenges rather than bypassing them.
- Cgroup counters can be unavailable on a different host; missing measurements remain null. No exact per-request CPU/memory attribution or device wall-power measurement is claimed.

Operations, backup/restore, adapters and configuration are documented in [README.md](README.md). No purchases, seller contacts, GitHub pushes or unrelated service changes were made.
