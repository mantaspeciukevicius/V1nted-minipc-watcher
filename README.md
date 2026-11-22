# Vinted Mini PC Watcher

A small Python and SQLite application for monitoring mini PC candidates, retaining price history and sending Telegram notifications. Designed for an always-on Ubuntu home server with Docker Compose.

- Vinted.lt and Skelbiu.lt; configured low-power Intel/AMD CPUs with at least **12 GB installed RAM**.
- **Checks every 30 minutes** in Europe/Vilnius; notifications for new candidates and price-drop events.
- Quiet hours stay local; one **daily summary at 19:00**.
- User-supplied JSON/CSV/text, optional licensed Brave Search discovery and explicitly authorized public-browser access.
- Persistent history, duplicate suppression, notification outbox, backups and integrity checks.
- No exposed network ports or required dashboard.

Read **[PROJECT.md](PROJECT.md)** for the complete project document, architecture, operating commands, setup and limitations.

## Quick start

Use an account that can run Docker. The provided container runs as UID/GID 1000; make the persistent directories writable by that identity.

```bash
mkdir -p data/inbox data/processed backups logs
cp .env.example .env
chmod 600 .env
# Edit settings; secrets belong only in .env.
nano .env
docker compose build
docker compose up -d watcher
docker compose exec -T watcher python monitor.py status
```

The defaults do not enable Telegram, Brave or direct browser access. Configure at least one permitted source or import real listing information. For browser monitoring, first establish authorization for that access, create your local `config/direct-authorization.json` using the example, then enable `ENABLE_AUTHORIZED_DIRECT_CHECKS`. Copying an example is not authorization.

## Tests

```bash
make test
# Or, without make:
PYTHONPATH=app python3 -m unittest discover -s tests -v
```

The ordinary test suite uses temporary databases and mocked network calls. It makes no live Vinted requests. The packaged source snapshot passed **106 tests** on 2026-11-15.

## Important limits

Browser checks cover a bounded first page of newest-first results, not the entire catalogue. Newly discovered means new to this database, not necessarily newly posted. Delivery eligibility is not established merely by a country domain. Unknown RAM, fees, availability and shipping remain unknown. Market-displayed prices may already include currency conversion; their decreases are not automatically confirmed seller price drops.

Runtime credentials, authorization records, databases, browser captures, logs and screenshots are excluded from Git. No software license has been selected for this repository.

Schedule update (2026-11-15): set `SCHEDULE=half_hourly` for checks at :00 and :30 in Europe/Vilnius. Deal alerts and the daily 19:00 summary remain enabled. Missed checks are coalesced on recovery. Test suite: 107 passing tests.

Alert update (2026-11-15): daily reports show counts without repeating stored listing details. Previously eligible browser candidates are directly rechecked within the existing run budget, even if absent from search. Unknown search-card status cannot revive a confirmed sold/reserved listing. Regression suite: 110 passing tests.

Market policy update (2026-11-15): `BUYER_MARKET=LT` routes browser and optional search-provider queries through vinted.lt only. Vinted's Lithuanian shipping page explicitly connects Lithuania with Latvia, Estonia, Poland and mainland Finland: https://www.vinted.lt/help/313/234-siuntimo-budai . Broader regional groups do not prove bilateral shipping. Foreign-domain historical observations stay in SQLite but are excluded from alerts, matches and candidate counts; new Lithuanian-market observations of the same ID can update them. `ALLOWED_SELLER_COUNTRIES=LT,PL,FI,LV,EE` rejects known seller origins outside this group. Source market is not seller country: unknown origin/delivery remains unverified, and checkout, seller carrier settings and territory restrictions still apply. No account-country changes or forwarding routes are assumed. Regression suite: 115 tests passing.

## Multi-marketplace expansion (20 November 2026)

The existing watcher now coordinates Vinted.lt and Skelbiu.lt sequentially through the same half-hour scheduler, SQLite database, event engine, persistent Telegram outbox and daily 19:00 Europe/Vilnius report. Manual checks do not move scheduled slots. Existing restart recovery, execution locking, backups and Compose hardening remain in place. No public port or second service was added.

### Configuration

- `config/cpu-policy.json`: exact approved CPU names, maximum asking prices, nominal CPU power, user reference estimates and sourced research metadata. The original eleven ceilings are unchanged. Twelve researched alternatives are additionally approved with documented €130–€150 ceilings; see [CPU_RESEARCH.md](CPU_RESEARCH.md). N200/N250 remain under manual review after benchmark evaluation. `CPU_POLICY_PATH` can override the path.
- `config/browser.json`: three frequent Vinted queries plus one rotating generic/brand/CPU query. Existing candidate detail rechecks use at most three slots, preserving discovery capacity. Twelve total detail checks and a 300-second browser budget.
- `config/skelbiu.json`: one frequent N100 search plus two rotating CPU/brand/generic searches; first page only; at most five details; 150-second budget; at least three seconds between navigations. Rotation cursors persist in existing `app_settings`.
- `SCHEDULE=half_hourly`, `TIMEZONE=Europe/Vilnius`, `DAILY_REPORT_TIME=19:00` are the deployed settings. Existing credentials are not changed.

### Identity, specifications and prices

Vinted identities remain `vinted:ID`; classifieds use `skelbiu:ID`. Existing SQLite tables and JSON observation bodies already support the extension, so no destructive migration or table rewrite is needed. Added JSON fields are backward compatible. Existing history is retained; current CPU policy is applied when reading and ranking legacy records.

Specification classification remains separate from `deal_state`: `WITHIN_CPU_TARGET`, `ABOVE_CPU_TARGET`, `ABOVE_HARD_LIMIT`, `PRICE_UNKNOWN`, `CONFIGURATION_REVIEW`, `CPU_RESEARCH_REQUIRED`, `UNSUITABLE`. The €175 hard limit caps deal qualification. Suitable computers above either limit are stored for later reductions instead of being discarded. A same-source asking-price reduction crossing a CPU target produces `CROSSED_CPU_TARGET`. Original and lowest comparable asking prices and the most recent decrease are retained alongside the existing full price history. Vinted market-display changes remain unverified seller-price changes.

RAM capacity claims and optional/barebone offers cannot establish installed RAM. Conflicting CPUs, multiple configurations and uncertain relevant prices require review. Unknown CPU models never gain an automatic price ceiling. CPU nominal power is distinct from sourced device idle power. Storage, adapter, Linux compatibility and BIOS recovery remain unknown unless evidence is provided; none is inferred from a CPU name.

Skelbiu cards are restricted to numeric classified URLs and `standard-list-item[data-item-id]` markup. Store advertisements do not qualify as classifieds. Detail extraction scopes description, asking price and city to the listing containers; related listings and finance offers are excluded. Explicit inactive/sold states are distinct from access failures. Visibility alone does not establish availability. Seller location does not establish delivery. Collection-only Skelbiu offers can remain hardware candidates; fully confirmed delivered deals still require route and cost evidence. A refresh date does not change listing identity or generate a new-listing event.

No cross-marketplace listings are silently merged. Automated duplicate suggestions are deferred until reliable seller/model/image evidence is available.

### Commands

All existing commands remain supported. Optional selectors:

```sh
docker exec vinted-minipc-watcher python /app/monitor.py check --source all
docker exec vinted-minipc-watcher python /app/monitor.py check --source vinted
docker exec vinted-minipc-watcher python /app/monitor.py check --source skelbiu
docker exec vinted-minipc-watcher python /app/monitor.py matches --source skelbiu
docker exec vinted-minipc-watcher python /app/monitor.py history --id skelbiu:LISTING_ID
```

`check --dry-run` intentionally disables browser/network discovery and Telegram and uses a temporary database. It is an isolation smoke test, not a live-source validation. Live validation must use explicitly isolated state and disabled Telegram, or an authorized ordinary check. Source selectors filter browser adapters and match output; manual inbox ingestion remains shared.

### Tests and operations

```sh
docker exec vinted-minipc-watcher python -m unittest discover -s /tests
docker exec vinted-minipc-watcher python /app/monitor.py backup
docker exec vinted-minipc-watcher python /app/monitor.py status
docker compose build
docker compose up -d --no-deps watcher
```

Tests are offline, use temporary databases, mocks and captured classified card markup, and disable real Telegram. Two baseline tests were corrected to avoid production buyer-market environment leakage / validate configured markets before scope override. The over-budget regression now verifies separate price state rather than hardware rejection.

Each adapter reports restrictions independently. A Vinted challenge latches `data/browser-access-paused.json`; inspect evidence before using the existing `browser-resume` command. Skelbiu uses the separate `data/skelbiu-access-paused.json`; inspect the source evidence and restore legitimate access before explicitly clearing that file. Neither source attempts CAPTCHA solving, session extraction, proxy rotation, stealth or account login. Firecrawl is not used or required.

For restore: stop only the watcher; retain a copy of current state; integrity-check the selected SQLite backup; restore it to `data/watcher.sqlite` with matching ownership, removing stale SQLite WAL/SHM files only while stopped; restore source/configuration from the assessment backup if rolling back; rebuild and start the watcher. Never delete the state volume. The assessment source/config backup is `backups/v2-assessment-20261120/`.

To add another marketplace, implement `collect(root, normalize, connection, config_dir)` returning normalized observations and truthful source statuses, validate its URL identity namespace in `normalize`, then register it sequentially in `sources`. Reuse shared classification, event/history handling and outbox; add offline fixtures and independent-failure tests before activation.

Known limitations: first-page rotating discovery is incomplete; CPU/RAM language parsing is conservative; multi-product offers need manual review; refresh timestamps are not original publication dates; device idle power and AC-loss recovery are usually unknown; remaining research CPUs are not auto-approved. No measured data is invented to fill gaps.

Per-check `search_runs.counts` now also records elapsed seconds, cgroup CPU seconds when available, memory after the check, the container-lifetime peak memory (explicitly not a per-check peak), process count, and observations/new candidates by marketplace. Unavailable cgroup counters remain null. These are resource counters, not electricity measurements.

## Upgrade: detail priority, configuration evidence and watchlists

Both adapters now collect their bounded search pages before spending detail slots. The shared `app/detail_policy.py` planner ranks supported CPUs and prices relative to their own ceilings, prioritizes newly observed target crossings, and reserves 60% of the available slots for new discovery when enough suitable new records exist. Known-listing rechecks are capped separately. At most one above-target detail is normally opened per source/run. Discovery and rechecks still share the existing overall detail/time budgets; requests remain sequential.

Configurable keys in both `config/browser.json` and `config/skelbiu.json`:

| Key | Default | Purpose |
|---|---:|---|
| `candidate_recheck_hours` | 2 | Minimum elapsed time between ordinary known-candidate detail attempts |
| `above_target_recheck_hours` | 6 | Slower detail attempts for recognized CPUs currently above their own ceiling |
| `max_rechecks` | Vinted 3 / Skelbiu 2 | Maximum known-listing detail slots per run |
| `max_above_target_details` | 1 | Maximum ordinary above-target detail slots per run |

A freshly observed asking-price crossing can override the long cooldown following a successful detail check. For those overrides, a failed attempt is backed off for one hour; ordinary cooldowns still apply otherwise. New missing-hardware or conflicting specification claims also request earlier verification. Attempt times persist in the existing `app_settings` table under namespaced `detail_attempt:` keys, so a restart or repeated search term does not reset the cooldown. No SQL schema migration is required.

Search-card observations retain the original timestamp of existing detail evidence in `specs_observed_at`. They do not renew specification or availability verification, invent installed RAM, or claim complete delivered costs. Conflicting current card claims are retained separately in `latest_card`, downgrade confidence and require verification. For older installations where a card overwrote the current detail JSON, the latest trustworthy detail observation can be recovered from existing history without rewriting historical observations. Previously stored descriptions are reassessed against the stricter parser before watchlist planning.

`app/configuration.py` adds Lithuanian and Polish supported-memory, optional-upgrade and missing-component wording, including `palaiko iki`, `obsługuje do`, `maksymalnie`, `be operatyviosios atminties`, `bez RAM`, `za dopłatą`, `bez dysku` and `bez zasilacza`. Missing RAM never qualifies as installed memory. Missing storage/adapter and multiple configuration prices require review; explicitly defective units are rejected. Shipping-price lines alone no longer count as a second computer configuration. The extracted flags are stored with each observation and included in risks. These are conservative language rules, not a guarantee that every seller sentence is understood.

View the suitable above-target watchlist:

```sh
docker exec vinted-minipc-watcher python /app/monitor.py watchlist
docker exec vinted-minipc-watcher python /app/monitor.py watchlist --source skelbiu
```

The output shows asking price, CPU ceiling, excess above target, last detail attempt and `detail_eligible_after`. That timestamp means eligible for a later bounded run, not a guaranteed appointment. Listings with insufficient RAM, unresolved configurations or terminal availability are excluded from this suitable-hardware view. Above-target records and all price history remain stored regardless.

Target-crossing notifications require an actual same-currency asking-price decrease. Merely changing a policy ceiling or ECB conversion does not become a seller-price-drop alert. Vinted market-display prices continue to carry their existing unverified seller-currency warning. Routine unchanged observations remain quiet, and existing Telegram/outbox handling and scheduling are preserved.

### Evidence-aware alerts and measured search rotation (upgrade 5/6)

Telegram event alerts now explain the CPU-specific asking-price ceiling, price history,
observed decrease, specification evidence age at alert creation, availability,
delivery and exact missing evidence. Unknown delivery charges remain unknown;
Vinted displayed-price changes retain the currency-conversion caveat. Full check
reports remain local, and event alerts retain source failure summaries. Existing
quiet-check and daily-summary policies remain in place. New outbox messages use
UTF-16-aware chunks; already queued messages retain their original chunk boundaries
so persisted part receipts remain valid across an upgrade.

Each completed search records its term, raw classified/card count, candidate IDs,
duplicates, duration, access state, fresh detail-backed useful hits and new qualifying
hits. Repeated terms share fractional credit for the same listing. Access failures
increase failure counts without being learned as empty catalogues. Above-target
hardware remains measurable, while fresh below-target hardware gets higher weight.
These are discovery metrics, not proof of shipping or availability.

Run `docker exec vinted-minipc-watcher python /app/monitor.py search-stats`
(optionally `--source vinted` or `--source skelbiu`) to inspect measurements.
Data persists in existing SQLite `app_settings`; no schema migration was required.
Daily summaries include productive-term measurements. History begins with this
upgrade; previous checks were not assigned invented query-level results.

Both marketplace JSON configurations support `adaptive_search` (default true),
`adaptive_every` (default 4) and `adaptive_min_successes` (default 3). At most one
rotating slot every fourth run favors a measured productive term after three
successful checks. Other slots continue round-robin coverage, including when
one source has only one rotating slot. Old measurements decay over 30 days.
Frequent searches, query/detail limits, pauses and scheduling are unchanged.
Set `adaptive_search` false to retain plain round-robin selection.

Offline captured-fixture provenance is in `tests/fixtures/upgrade-56-provenance.json`.
The additional Skelbiu fixture retains genuine classified anchors from a captured
search page; Vinted fixtures replay captured rendered cards, including unrelated
N97 results that must not qualify. Constructed edge cases are explicitly synthetic.
Run `PYTHONPATH=app python3 -m unittest discover -s tests`; live access remains
separate and may truthfully report restrictions or parser failures.


### Daily decisions report and 12 GB minimum (2026-11-22)

The installed RAM minimum is now 12 GB (`MIN_RAM_GB=12` in `.env`; restart the
service after changing it). CPU-specific price ceilings remain unchanged. Parsing
recognizes 12 GB, 12288 MB, paired modules and explicit 8 GB + 4 GB configurations.
Maximum capacities, optional upgrades and SSD/NVMe capacity do not qualify as RAM.
Older records gain eligibility through fresh detail verification; historical
observations and alerts are not rewritten.

Daily Telegram reports use only the stated daily window. They show the discovery
funnel (search attempts, cards across terms, unique relevant IDs, successful
details/attempts, hardware matches and within-budget observations), exclusive
primary review reasons, above-budget suitable hardware, fresh/stale evidence and
initial availability observations separately from actual transitions. Card counts
may include the same listing across terms; hardware/detail totals are observations,
not distinct deals. Old run funnels are reconstructed from recorded observations
and explicitly marked when detail-attempt counters may be incomplete.

Source errors identify affected queries and whether the same query succeeded in a
later check. Disabled sources and the duplicate technical footer stay out of the
daily Telegram message. Full per-check diagnostics remain in local reports. Search
quality statistics from `search-stats` are lifetime measurements, never daily totals.

Known expensive (>150% of the CPU ceiling) or unsupported processors refresh every
24 hours (`low_priority_recheck_hours` in each marketplace JSON). Near-target
hardware keeps its configured above-target cooldown; within-budget candidates keep
the faster normal cooldown. Price threshold crossings retain earlier verification,
and new discovery keeps its reserved detail slots.

Preview without queuing a notification or recording a report:

```bash
docker exec vinted-minipc-watcher python /app/monitor.py preview-daily
docker exec vinted-minipc-watcher python /app/monitor.py preview-daily --at 2026-11-22T19:00:00+02:00
```

Previews use observations before the boundary, not later stored snapshots. Daily
summaries remain deduplicated; the 19:00 browser check runs afterward.


### Bounded failure recovery and lifecycle alerts (2026-11-22)

Both marketplace adapters retry an ordinary public-page navigation once for
timeouts, recognized temporary network errors or server errors. A crashed/closed
browser is closed before one replacement is launched. Retries share the original
marketplace run deadline, with each browser timeout capped by remaining time.
Selectors, parser errors, 404s, access restrictions and exhausted run budgets are
not repeatedly retried. A 401/403/429 stops before attempting page extraction;
CAPTCHA/login/access/rate-limit gates remain paused until operator review. No
automatic bypass, proxy rotation or account workflow is introduced.

`config/recovery.json` configures `navigation_retries` (0 or 1; hard cap 1),
`retry_delay_seconds` (default 5; bounded 3–15), and
`persistent_failure_checks` (default 3; minimum 2). A failing query/detail scope
is tracked in SQLite `app_settings` (`failure_watch:MARKETPLACE`). After three
failed checks of that scope, one Telegram incident alert is added to the existing
outbox. Access restrictions alert immediately because the source is paused.
Further failures do not repeat the alert. A recovery notification is emitted only
when all previously pending scopes have actually succeeded: another rotating term
or a disabled adapter cannot clear the incident. Detail failures need successful
extraction of the same listing. State and notification insertion commit together
so crashes cannot silently consume an alert. This state survives container restart.

Successful retry counts and browser restarts are stored in run funnel metrics and
appear in daily reports when nonzero. Local reports retain full diagnostics;
Telegram health alerts use safe diagnostic categories and affected scopes.
`status` includes the persistent `failure_watch` state, including issues that have
not yet reached the alert threshold. The other marketplace continues independently.

After inspecting saved evidence and resolving authorization/access, manually clear
only the affected source gate with `python /app/monitor.py browser-resume --source
vinted` or `--source skelbiu` inside the existing container. Resuming does not itself
claim recovery; a later successful check must establish it. No recovery notification
is sent for an isolated transient failure that never triggered an incident alert.
Existing Telegram retry/part receipts, 12 GB RAM minimum, CPU ceilings, scheduling,
quiet routine checks and daily summaries remain in effect. Database corruption and
parser changes require investigation; this feature does not overwrite databases or
automatically alter parsers to manufacture matches.
