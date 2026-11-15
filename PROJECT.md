# Vinted Mini PC Watcher — project document

Documented: **2026-11-15**. This describes the implemented application and its current LarkBox deployment. Historical setup reports are not current health reports.

## Purpose

Discover potential mini PC deals accessible to a buyer in Lithuania, conservatively interpret their specifications, preserve listing/price history and notify the owner through Telegram. Monitoring runs independently of ChatGPT on the LarkBox server.

The project targets Intel N100, N97 and N150 systems with at least 16 GB physically installed RAM. The default asking-price ceiling is €175. A complete delivered-price estimate may receive a configured budget tier; an incomplete subtotal never proves that a delivered price is below a threshold.

## Current deployment

| Item | Configuration |
| --- | --- |
| Installation directory | `/opt/containers/vinted-minipc-watcher` |
| Platform | CHUWI LarkBox N100, Ubuntu Server 26.04.1 LTS |
| Container / Compose project | `vinted-minipc-watcher` |
| Runtime | Python 3.13, Chromium, Playwright 1.64.1, Xvfb |
| Persistence | SQLite WAL in `data/watcher.sqlite` |
| Checks | Hourly at `:00` |
| Daily summary | 19:00 Europe/Vilnius |
| Telegram policy | New candidates, price decreases with uncertainty labels, returned availability; no hourly no-match messages |
| Network exposure | No published ports; no dashboard |
| Container limits | 1.5 GiB RAM, 1 CPU, 256 PIDs, 256 MiB shared memory |
| Isolation | UID/GID 1000, read-only root filesystem, dropped capabilities, no-new-privileges |
| Recovery | Docker `unless-stopped`, persistent cursor and execution/scheduler locks |

At documentation time the service and database were healthy and Telegram was enabled for a private chat verified by a unique user-sent message. The latest scheduled source check at **2026-11-15 09:00 Europe/Vilnius** was **PARTIAL_CHECK** because Chromium reported `ERR_NAME_NOT_RESOLVED` for the Vinted hostname. That is a source/network failure, not evidence that no listings exist. Check current status and logs before relying on this snapshot.

An earlier controlled live check on 2026-11-14 completed 27 browser searches across the nine configured country domains. After validation, all 28 observed potential candidates were rejected and no qualifying deal was established. This does not describe the complete live catalogue or guarantee current reachability.

## Architecture

```text
Single scheduler / manual check
             |
             v
  Imports | Brave API | Authorized browser
             |
             v
  Normalize and classify specifications
             |
             v
  SQLite observations, prices, availability, events
             |
             +--> Every check: local report and logs
             |
             +--> New candidate/drop: pending Telegram report
             |
             +--> 19:00: daily summary from completed checks
                              |
                              v
                  Persistent outbox + bounded retries
```

The implementation uses Python's standard library for storage, scheduling, logging output, HTTP requests, XML rates and CLI operations. Playwright is the browser adapter's additional Python dependency. Chromium and Xvfb live inside the project container; no host browser installation is required.

### Source files

| File | Responsibility |
| --- | --- |
| `app/monitor.py` | Configuration, CLI, scheduler, normalization, SQLite schema, event detection, cost components, ECB rates, reports, Telegram and backups |
| `app/browser_source.py` | Authorized public-page browser navigation, rendered DOM extraction, candidate hints, access checks and evidence |
| `tests/test_monitor.py` | Parsing, state, history, currency, imports, restart behavior and notification tests |
| `tests/test_browser_source.py` | Browser extraction helpers, irrelevant-product rejection and access-stop behavior |
| `tests/test_hourly_reporting.py` | Hourly/DST behavior, daily summaries, quiet checks and recovery |
| `config/browser.json` | Countries, search terms, detail count and timing bounds |
| `config/direct-authorization.example.json` | Non-operational template for the operator's own local authorization record |
| `config/set-telegram-token.py` | Hidden-input token helper for the default LarkBox installation path |
| `Dockerfile.browser` | Default Compose image, with Chromium and Playwright |
| `Dockerfile` | Smaller import/API-only image; not the default Compose build |
| `.env.example` | Safe configuration template; no credentials |

Temporary browser inspection scripts and original setup transcripts are intentionally omitted from the repository. Runtime logs, captures and actual authorization records stay on the server.

## Data sources and authorization

### Manual imports

The application reads `.json`, `.csv` and `.txt` files from `data/inbox/`. JSON supports one object or an array. CSV supports scalar fields. Pasted text supports listing URLs and descriptions; it does not invent missing prices or verification.

The complete file is validated before its rows are processed. Valid files are archived under `data/processed/`; malformed files stay in the inbox and appear as parsing failures in reports. Write a file outside the inbox first, then rename it into the inbox to avoid reading a partial upload.

Example **schema only**, with an intentionally invalid placeholder URL:

```json
{
  "url": "https://www.vinted.lt/items/REPLACE_WITH_REAL_NUMERIC_ID",
  "title": "Paste the actual listing title",
  "description": "Paste the actual description",
  "price": "125.00",
  "currency": "EUR",
  "country": "LT"
}
```

Replace all placeholders with actual user-supplied information. Do not import illustrative fixtures into production.

### Optional Brave Search

The official Brave Search API adapter discovers publicly indexed listing URLs and preserves their provenance. A subscription/key with appropriate result-storage rights and `BRAVE_STORAGE_LICENSE_CONFIRMED=true` are required. Indexed results remain unverified leads and are not proof of current availability. The deployed installation uses browser access instead; Brave is disabled.

Optional Brave defaults comprise 20 queries across nine markets. With hourly checks this could mean up to 4,320 API calls per day. Check the provider's quota/costs before enabling it; use `config/search.json` to set a smaller `queries` array if needed.

### Explicitly authorized browser access

The deployed owner stated that they were officially authorized and subsequently requested hourly checks. That statement is recorded locally; this document does not independently certify permission or grant it to other installations.

For a separate deployment, establish authorization covering the proposed method and scope before enabling direct browser access. Defaults keep it disabled. Do not distribute or reuse another operator's permission record.

The adapter visits ordinary public catalogue and item pages through headed Chromium in Xvfb. It reads rendered DOM, without importing login cookies or using unofficial endpoints, stealth, user-agent spoofing, proxy rotation, CAPTCHA solving or access-control bypasses.

Default browser scope:

- Countries: Lithuania, Poland, Germany, France, Netherlands, Latvia, Italy, Spain and Czech Republic.
- Search terms: N100, N97, N150, sorted newest-first through the public catalogue route.
- First result page per term/market; duplicate numeric listing IDs are combined.
- Up to 12 detail-page checks per run.
- Three-second pauses and an approximate eight-minute run budget. An in-progress navigation/cleanup can extend the elapsed time beyond that budget.

The country domain is a discovery market, not proof of seller location, account connectivity, direct Lithuanian shipping or forwarding eligibility. A first-page check can miss listings, especially when result volume is high or promoted/recommended items are present.

A visible challenge, login redirect or HTTP 401/403/429 stops the run and writes `data/browser-access-paused.json`. Later hourly checks still record/report that limitation but do not make browser requests while paused. Other HTTP/network failures are reported separately. Resolve the underlying issue legitimately before using `browser-resume`; removing the application's flag cannot bypass a website restriction.

There is no automatic email login, Android notification ingestion, Vinted login or checkout automation.

## Classification and verification

Hardware extraction recognizes eligible CPU text and common RAM units including GB, Go and ГБ, plus configurations such as 2 × 8 GB. Common supported-maximum claims are separated from installed capacity. Known phones, chargers, helmets and laptop models using N100/N97/N150 as product names are filtered or rejected.

Classification states:

- `VERIFIED_MATCH`: current trusted detail evidence supports CPU and installed RAM.
- `LIKELY_MATCH_UNVERIFIED`: plausible specs without sufficient confirmation.
- `NEEDS_MANUAL_REVIEW`: missing or conflicting CPU/RAM evidence.
- `REJECTED`: confirmed insufficient RAM, unrelated device, ineligible delivery or price above the configured maximum.

Natural language and changing site markup can still be ambiguous. Model names alone do not establish configuration. Source detail evidence represents observed seller claims, not a physical inspection of the device.

Availability states include `AVAILABLE_CONFIRMED`, `SOLD`, `RESERVED`, `PURCHASE_IN_PROGRESS`, `REMOVED`, `UNKNOWN` and `ACCESS_BLOCKED`. A fresh rendered purchase button may establish public-page availability; explicit sold/reserved labels override it. A loading page or indexed snippet alone does not establish availability. Missing search results do not mark a listing removed.

Only a match with fresh hardware evidence, confirmed availability and confirmed direct/forwarded delivery is fully confirmed. Verification expires after 24 hours by default. Delivery remains unverified in automated browser observations because the adapter does not enter checkout or inspect a personal account's shipping choices.

For structured manual verification, provide `details_confirmed`, `evidence_source`, `availability_evidence` and `delivery_evidence`, with timezone-aware `observed_at`. Delivery states are `DIRECT_LT_CONFIRMED`, `FORWARDER_CONFIRMED`, `COLLECTION_ONLY`, `INELIGIBLE` and `UNKNOWN`.

## Prices, currency and shipping

Each price observation retains amount, currency, EUR equivalent, timestamp and source. ECB reference rates are refreshed daily, cached with their publication date/source and rejected for conversion when more than seven days old. Missing conversions remain unknown.

Delivered cost components are stored separately:

1. Asking price.
2. Buyer-protection fee.
3. Seller-to-destination shipping.
4. Forwarding and Lithuanian delivery/collection, when relevant.
5. Additional documented charges.

A component requires amount, currency, source, timestamp and `confirmed` or `estimated` status. Unknown charges are not free. No undocumented fixed buyer-protection percentage is used. A complete total may still be an estimate; an incomplete subtotal never receives a confirmed budget tier.

JSON `costs` keys are `buyer_fee`, `seller_shipping`, `additional_charges`, and for forwarding routes `forwarding` and `local_delivery`. Use `route: "forwarder"` for an unverified forwarding plan too. Exact zero charges also require evidence.

PirkEU quotes must currently be entered manually using its official prices/calculator, documenting origin, packed weight/dimensions and selected delivery method. No automatic tariff/weight calculator or automatic warehouse eligibility check is implemented. The forwarding warehouse's existence does not establish that a Vinted purchase can legitimately be sent there. Public PirkEU guidance requires appropriate courier delivery to the warehouse, rather than an arbitrary pickup locker.

Vinted sometimes converts asking prices and fees into the viewing market's currency. Browser observations therefore use `MARKET_DISPLAY` price basis. Their decreases are labelled `DISPLAY_PRICE_DECREASE_UNVERIFIED`; they are not asserted as confirmed seller price drops. Comparable user-supplied seller amounts in the same currency/source support ordinary `PRICE_DROP` detection. ECB changes alone never establish a seller price reduction.

Candidates are sorted by confirmation, complete versus incomplete cost, and estimated delivered price. Advanced weighted scoring, automatic model resolution and relist recognition across different IDs are not implemented.

## SQLite history and reliability

Main tables: `listings`, `listing_observations`, `price_history`, `availability_history`, `search_runs`, `source_health`, `alerts_sent`, `outbox`, `outbox_parts`, `currency_rates`, `shipping_estimates`, `app_settings` and `migrations`.

Stable identity is `vinted:<numeric listing ID>`, shared across country-domain aliases. Observations have content digests. Runs use unique IDs; scheduled slots are unique. A listing absent from a search remains in history.

Run results and notification intent are committed together. Quiet runs use `LOCAL_ONLY`, not a pending Telegram message. Notification records are marked `DELIVERED` only after Telegram confirms acceptance. Each confirmed message part has a persisted Telegram message ID. Failed sends receive five bounded retries with backoff and remain available for an explicit retry afterward. A timeout after Telegram accepted a message can still cause a duplicate: the API has no transaction key shared with SQLite.

Three file locks protect scheduler leadership, overlapping checks and notification flushing. Multiple missed hourly checks are recorded and coalesced into one fresh recovery scan, rather than replaying a large batch of historical browser searches. A single missed slot can be recovered normally. The most recent missed daily summary can be caught up once. Long gaps are recorded separately. Explicitly disabled periods are skipped.

The daily summary has a stable date/slot identity and is queued once at 19:00 before that hour's browser scan. It summarizes completed checks from the prior daily window and current stored candidates. This avoids delaying the summary until a long browser check finishes. DST follows Europe/Vilnius using real UTC minutes; skipped hours are skipped and both instances of an autumn repeated hour execute with distinct offsets.

## Configuration

All values belong in local `.env` unless stated otherwise. The repository includes only `.env.example`.

| Setting | Default / meaning |
| --- | --- |
| `TIMEZONE` | `Europe/Vilnius` |
| `SCHEDULE` | `hourly`; custom comma-separated `HH:MM` slots also supported |
| `NOTIFY_MODE` | `deals_and_daily`; `every_check` restores all-check notifications |
| `DAILY_REPORT_TIME` | `19:00` |
| `MIN_RAM_GB` | `16` |
| `ALLOWED_CPUS` | `N100,N150,N97` |
| `TARGET_PRICE_EUR` / `MAX_ASKING_PRICE_EUR` | `175`; raise the maximum for secondary candidates |
| `PRIORITY_THRESHOLDS` | `75,100,125,150,175` |
| `DATABASE_PATH` | `/state/watcher.sqlite` inside the container |
| `ENABLE_TELEGRAM` | `false` in the template; enable only for a verified destination |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Local secrets/destination; never commit |
| `BRAVE_API_KEY` | Optional local credential |
| `BRAVE_STORAGE_LICENSE_CONFIRMED` | `false` until appropriate rights are established |
| `ENABLE_AUTHORIZED_DIRECT_CHECKS` | `false` in the template |
| `VERIFICATION_TTL_HOURS` | `24` |
| `RETENTION_DAYS` | `180`, for local backup retention |
| `ENABLE_DASHBOARD` | Reserved; dashboard not implemented |
| `LOG_LEVEL` / `DEFAULT_CURRENCY` | Compatibility settings; log output is not level-filtered and missing imported currency defaults to EUR in the current code |

Edit `config/browser.json` for browser markets, terms, pause, detail cap and time budget. JSON changes are read on the next check. Environment changes require container recreation; a simple `restart` does not reload `.env`.

## Install and operate

The provided Compose file expects writable persistent directories owned by the container's UID/GID 1000. Choose the installation path and permissions deliberately; do not change unrelated service directories.

```bash
cd /opt/containers/vinted-minipc-watcher
mkdir -p data/inbox data/processed backups logs
cp .env.example .env
chmod 600 .env
nano .env
docker compose build
docker compose up -d watcher
```

For a separately authorized browser installation:

```bash
cp config/direct-authorization.example.json config/direct-authorization.json
# Fill in the actual authorization, person, date and scope before enabling.
nano config/direct-authorization.json
nano .env
# Set ENABLE_AUTHORIZED_DIRECT_CHECKS=true only within that authorization.
docker compose up -d --force-recreate watcher
```

Routine commands:

```bash
cd /opt/containers/vinted-minipc-watcher
# Service and application status, including next check and daily summary
docker compose ps
docker compose exec -T watcher python monitor.py status
# Recent logs
docker compose logs --tail 100 -f watcher
# Manual check; recurring times stay unchanged
docker compose exec -T watcher python monitor.py check
# Isolated dry-run: no production writes, browser calls or Telegram messages
docker compose exec -T watcher python monitor.py check --dry-run
# Recent local reports and non-rejected candidates
docker compose exec -T watcher python monitor.py reports
docker compose exec -T watcher python monitor.py matches
# Replace the example identity with a real listing ID
docker compose exec -T watcher python monitor.py history --id vinted:123456
# Monitoring controls
docker compose exec -T watcher python monitor.py disable
docker compose exec -T watcher python monitor.py enable
docker compose restart watcher
# Only after legitimate access resolution, clear the application's browser pause
docker compose exec -T watcher python monitor.py browser-resume
```

There is only one scheduler, inside this container. No host cron job or systemd timer is required. The project does not create a task in ChatGPT's Scheduled UI. The existing Docker boot service and `unless-stopped` restart policy resume it after reboot unless intentionally stopped.

## Telegram setup

Create a dedicated bot using Telegram's official BotFather, open the bot and send a message. Enter its token locally in `.env`; the optional hidden-input helper targets the standard LarkBox installation path:

```bash
python3 /opt/containers/vinted-minipc-watcher/config/set-telegram-token.py
```

Verify the chat with a unique message that you personally send to the intended bot. The chat ID must come from that exact message; do not select an arbitrary `/start` from another account. Enter the verified `TELEGRAM_CHAT_ID`, set `ENABLE_TELEGRAM=true`, and recreate this project's container. Never share the token in Git, screenshots, issue reports or shell history.

```bash
cd /opt/containers/vinted-minipc-watcher
nano .env
docker compose up -d --force-recreate watcher
# Retry retained PENDING reports only; LOCAL_ONLY reports remain local
docker compose exec -T watcher python monitor.py retry
```

Telegram acceptance proves that Telegram accepted the message for a chat, not that the intended phone displayed it. Confirm a test message on the phone before considering end-to-end delivery verified. No token, chat ID or account session is included in this repository.

## Tests and validation

```bash
make test
# Or:
PYTHONPATH=app python3 -m unittest discover -s tests -v
# Container test run, without live sources:
docker compose run --rm --no-deps -e ENABLE_AUTHORIZED_DIRECT_CHECKS=false \
  watcher python -m unittest discover -s /tests -v
```

The source snapshot passes 106 automated tests. Tests cover accepted/rejected CPU/RAM cases, supported maxima, multiple RAM modules, unrelated products, sold/reserved/collection-only items, missing delivery, first discovery, unchanged observations, same-currency price changes, conversion-only changes, persistence/restarts, Telegram success/failure, source failure, empty reports, daily-summary deduplication, quiet reports, hourly DST transitions and recovery coalescing.

Ordinary tests use mock data, temporary databases and mocked network calls; they make no live Vinted requests. Separate controlled browser checks established actual public-page access during deployment. They do not guarantee future site availability, DOM compatibility or delivery eligibility.

## Backups, update, restore and uninstall

The daemon creates and integrity-checks a local SQLite backup daily and on startup. `RETENTION_DAYS` controls backup retention. Observation, price and run history remain indefinite; automatic history pruning is not implemented. Browser evidence is not automatically pruned either. Docker logs rotate at three files of 5 MB. Copy backups to your external backup storage to protect against device/disk loss.

```bash
cd /opt/containers/vinted-minipc-watcher
# Safe online backup
docker compose exec -T watcher python monitor.py backup
# Update code only after reviewing the changes and preserving local configuration
git pull --ff-only
docker compose build
docker compose up -d watcher
docker compose exec -T watcher python monitor.py status
```

The live installation must first be initialized/cloned as a Git checkout before `git pull` applies; preparing the separate repository does not automatically convert or replace the running installation.

Restore a selected known-good backup while the service is stopped:

```bash
cd /opt/containers/vinted-minipc-watcher
docker compose stop watcher
# Choose a new directory name on each restore attempt.
mkdir -p data/pre-restore
mv data/watcher.sqlite* data/pre-restore/
# Replace the placeholder with a real backup filename.
cp backups/BACKUP_FILENAME.sqlite data/watcher.sqlite
docker compose up -d watcher
docker compose exec -T watcher python monitor.py status
```

Stop/uninstall this project's container with `docker compose down` from its own directory. Data, credentials and backups remain until explicitly archived or removed. Do not use global Docker prune commands or touch other service directories.

## Repository boundaries

Only application code, tests, safe examples, Docker files and documentation are versioned. `.gitignore` and `.dockerignore` exclude `.env` and editor backups such as `.env.save`, databases, data directories, private authorization records, logs, captures and conversation attachments. Existing deployment credentials are not overwritten when preparing or updating the repository.

## Reference pages reviewed during implementation

- Vinted terms: https://www.vinted.lt/terms_and_conditions
- Official English EU terms reviewed: https://legal-assets.vinted.com/legal/terms/se/en-SE/terms-and-conditions-v10.pdf
- PirkEU prices: https://www.pirkeu.lt/en/prices
- PirkEU calculator: https://www.pirkeu.lt/en/price-calculator
- ECB reference rates used by the code: https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml
- Brave Search API: https://api-dashboard.search.brave.com/app/documentation/web-search/get-started
- Playwright Docker guidance: https://playwright.dev/python/docs/docker

These links document the implementation's sources and are not a guarantee that terms, tariffs or access permission remain unchanged. Re-check relevant conditions before expanding access or shipping assumptions.

Schedule update (2026-11-15): set `SCHEDULE=half_hourly` for checks at :00 and :30 in Europe/Vilnius. Deal alerts and the daily 19:00 summary remain enabled. Missed checks are coalesced on recovery. Test suite: 107 passing tests.

Alert update (2026-11-15): daily reports show counts without repeating stored listing details. Previously eligible browser candidates are directly rechecked within the existing run budget, even if absent from search. Unknown search-card status cannot revive a confirmed sold/reserved listing. Regression suite: 110 passing tests.

Market policy update (2026-11-15): `BUYER_MARKET=LT` routes browser and optional search-provider queries through vinted.lt only. Vinted's Lithuanian shipping page explicitly connects Lithuania with Latvia, Estonia, Poland and mainland Finland: https://www.vinted.lt/help/313/234-siuntimo-budai . Broader regional groups do not prove bilateral shipping. Foreign-domain historical observations stay in SQLite but are excluded from alerts, matches and candidate counts; new Lithuanian-market observations of the same ID can update them. `ALLOWED_SELLER_COUNTRIES=LT,PL,FI,LV,EE` rejects known seller origins outside this group. Source market is not seller country: unknown origin/delivery remains unverified, and checkout, seller carrier settings and territory restrictions still apply. No account-country changes or forwarding routes are assumed. Regression suite: 115 tests passing.
