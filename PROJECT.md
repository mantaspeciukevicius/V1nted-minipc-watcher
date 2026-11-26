# Mini PC Watcher — deployed project description

Updated: **27 November 2026**. Describes the LarkBox installation. See [DEPLOYMENT.md](DEPLOYMENT.md) for the distinction between deployed code and the GitHub source snapshot. Historical implementation reports describe their own dates, not current health.

## Purpose and deployment

Personal mini PC monitoring on an always-on CHUWI LarkBox N100. Python 3.13, Chromium/Playwright, Xvfb and SQLite run in Docker container `vinted-minipc-watcher` at `/opt/containers/vinted-minipc-watcher`. Monitoring runs independently of ChatGPT. No dashboard or public listening port is enabled.

The container runs as UID/GID 1000 with a read-only root filesystem, dropped capabilities, no-new-privileges, resource limits, temporary browser storage, and persistent data/backups. Docker restart policy is `unless-stopped`. Other applications are outside this project's scope.

## Schedule and notifications

One in-container scheduler checks at **:00 and :30**, Europe/Vilnius, with daylight-saving-aware times. Scheduler, check and outbox file locks prevent normal overlapping execution. Manual checks do not alter the schedule. Missed checks are recorded and coalesced; they are not replayed as a burst of historical searches.

Relevant new candidates, seller-price drops and qualifying displayed-price decreases generate Telegram reports. Displayed-price changes retain currency uncertainty. Price increases remain in history but no longer send deal alerts. Unchanged listings are not repeatedly reported as new. A daily summary is generated at **19:00**, with separate within-target and negotiation counts.

Telegram uses a persistent outbox with five bounded automatic attempts and confirmed message-part tracking. Exhausted deliveries remain available for explicit retry. A crash after Telegram accepts a message but before local confirmation can still cause a duplicate; delivery is not guaranteed exactly once. Missing credentials retain local reports rather than erasing results.

## Discovery and access

Active sources are **Vinted.lt** and **Skelbiu.lt**, using public rendered pages through the owner's explicitly authorized browser installation. No automatic login, account cookies, CAPTCHA bypass, proxy rotation, unofficial listing endpoint or stealth integration is used. Access restrictions stop/pause the affected source; other sources can continue.

Vinted uses frequent N100/N97/N150 queries and one rotating brand, generic or approved-CPU query. Skelbiu uses frequent N100 and two rotating queries. Adaptive search considers measured usefulness. Rotating discovery includes NiPoGi; model/brand-only discoveries still need CPU/RAM evidence.

Both adapters can follow one visible same-site next-page link, up to **two pages per query**, within existing deadlines. Actual pages checked are recorded. No link, exhausted time or a blocked page means limited coverage, not a complete catalogue search. Results are deduplicated by marketplace and numeric listing ID.

Current bounds: Vinted up to 12 detail checks, 300-second browser budget; Skelbiu up to five details, 150-second budget. Detail planning reserves capacity for discovery and uses cooldowns for known/expensive records. Both use at least approximately three seconds between relevant navigations. Broader search does not remove these limits.

Manual JSON/CSV/text imports operate through `data/inbox`. Brave Search is implemented but currently unconfigured; appropriately licensed API access is required. Indexed snippets are leads, not live availability proof. No email or Android-notification adapter is configured.

## Hardware and price policy

The deployed RAM minimum is **12 GB**, configurable through `MIN_RAM_GB`. This supersedes the original 16 GB requirement. CPU policy includes the original N100/N97/N150 plus approved low-power Intel/AMD alternatives; [CPU_RESEARCH.md](CPU_RESEARCH.md) and `config/cpu-policy.json` record their status and price ceilings. CPU nominal power is not measured wall or idle power.

Examples of asking-price targets: N100 €120; N97/N150 €130. The deployed **20% negotiation allowance** includes €140 N100 systems up to €144, labelled negotiation options rather than within-target deals. The existing absolute asking-price cap defaults to €175 and still applies. Unsupported/ambiguous CPUs require review.

Installed RAM is separated from supported maxima and optional upgrades. `16GB RAM+256GB M.2 SSD` parses as 16 GB installed RAM. Multiple memory modules and common language units are supported. Missing/conflicting RAM, multiple configurations, missing components and unsuitable form factors remain explicit blockers. Seller claims are not physical inspection.

## Verification and geography

Specification classifications are VERIFIED_MATCH, LIKELY_MATCH_UNVERIFIED, NEEDS_MANUAL_REVIEW and REJECTED. Availability is separately AVAILABLE_CONFIRMED, SOLD, RESERVED, PURCHASE_IN_PROGRESS, REMOVED, UNKNOWN or ACCESS_BLOCKED. Sold/reserved/removed/in-progress items are excluded from active recommendations. Search absence does not imply removal.

An item HTTP 404/410 plus an explicit rendered not-found message records REMOVED, preserves specification age and price history, clears the matching failure incident and avoids retrying that dead listing. A generic error or access challenge cannot establish removal. Ordinary item failures do not stop the remaining detail plan; access restrictions still stop the source.

Vinted discovery uses the Lithuanian buyer catalogue. Configured seller countries are LT/PL/FI/LV/EE, with mainland Finland and carrier/territorial exceptions requiring attention. Catalogue domain is not seller origin or shipping proof. Actual Lithuanian delivery remains UNKNOWN unless supported by listing/checkout evidence. Account-country changes and forwarding feasibility are not assumed.

## Fees and delivery evidence

All reports use EUR; supported foreign currencies use cached ECB reference rates with dates. Original/seller prices and Vinted's converted market display are distinguished for price-change events.

Costs are separate asking price, buyer fee, seller shipping, additional documented charges and, if applicable, forwarding/local delivery. Every usable component needs amount, currency, source, timestamp and confirmed/estimated status. Unknown charges are never free.

The browser can derive the displayed buyer fee only from an explicit fee-inclusive EUR total and a matching independently displayed asking-price line, in English or Lithuanian. Advertised shipping “from” prices are estimated lower bounds. Lower bounds cannot make delivered costs complete or verify delivery to Lithuania.

A `verification-template --id ...` command exports editable evidence fields without pre-confirming them. After manually reviewing hardware, availability and checkout for the actual destination, the owner supplies sources/timestamps and imports the result through the normal inbox. See [README.md](README.md). No automated checkout, purchase or forwarding tariff calculator is implemented.

## Persistence and maintenance

SQLite WAL database: `data/watcher.sqlite` on the host, `/state/watcher.sqlite` in the container. Tables store listings, observations, asking-price/availability history, runs, source health, cost evidence, rates, alert events, outbox parts/settings and migrations. Different platforms' numeric IDs do not collide. New IDs on relisted physical items may still be treated as new listings.

Startup/daily SQLite backups use the backup API and integrity checks; backups live in `backups/`. `RETENTION_DAYS` controls backup retention, not automatic deletion of price history. History is currently retained indefinitely. External backup copies are needed for disk-loss protection.

Diagnostic cleanup runs at startup/daily maintenance. Defaults: **30 days**, **512 MiB target** (`EVIDENCE_RETENTION_DAYS`, `EVIDENCE_MAX_MB`). The newest two days, unresolved detail-failure evidence and active access-pause directories are protected. Only recognized timestamped browser evidence directories are eligible; database, imports and backups are untouched. Protection can keep usage above the soft cap. Logs rotate at three 5 MB files.

## Source layout

- `app/monitor.py`: configuration, CLI, scheduler, SQLite, source orchestration, event detection and reports.
- `app/browser_source.py`, `app/skelbiu_source.py`, `app/skelbiu_html.py`: rendered-page collection and parsing.
- `app/cpu_policy.py`, `app/configuration.py`: CPU/RAM/configuration evidence and targets.
- `app/detail_policy.py`, `app/search_quality.py`: bounded detail planning and search rotation.
- `app/notifications.py`, `app/daily_reporting.py`: notifications and daily decision summaries.
- `app/recovery.py`: bounded navigation recovery and persistent incidents.
- `app/enhancements.py`: pagination, displayed fee evidence, verification templates and cleanup (deployed enhancement).

## Validation and limits

Latest deployed suite: **355 passing automated tests**, verified on the host and inside the image on 27 November 2026. Tests use mocks/fixtures rather than live Vinted requests. A controlled run completed successfully with second-page evidence from Vinted's three CPU queries and Skelbiu N100. It observed six listings, five needing review and one rejected; no fully confirmed deals were established. This is a dated result, not current inventory or a permanent uptime guarantee.

Future layout changes, access restrictions, incomplete descriptions, bounded pages and checkout-only evidence can cause gaps. Service health alone does not prove discovery completeness. No seller contact or automatic purchase is performed.
