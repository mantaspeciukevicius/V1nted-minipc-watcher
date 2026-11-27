# Mini PC Watcher

Personal Vinted.lt and Skelbiu.lt mini PC monitoring on LarkBox, with persistent history and Telegram reports.

**Documentation updated 27 November 2026.** The repository now includes the latest deployed source and tests, with safe configuration examples. See [DEPLOYMENT.md](DEPLOYMENT.md) for deployment boundaries and required local setup.

## Current behavior

- Checks every **30 minutes** in **Europe/Vilnius**; daily Telegram summary at **19:00**.
- Minimum **12 GB installed RAM**, approved CPU-specific asking-price ceilings and **20% negotiation allowance**.
- Frequent CPU searches plus rotating brand/model/generic terms, including NiPoGi.
- Up to **two visibly linked results pages** per query, within bounded source deadlines.
- New-candidate/drop notifications; unchanged listings and price increases do not send deal alerts.
- SQLite history, persistent Telegram outbox, safe backups, failure/recovery alerts and diagnostic retention.
- Explicit unknown availability/delivery/costs; no automatic login or purchase.

Detailed behavior, limitations and architecture: [PROJECT.md](PROJECT.md). Access and browser operations: [BROWSER.md](BROWSER.md). CPU evidence: [CPU_RESEARCH.md](CPU_RESEARCH.md).

## Operating the existing installation

Commands below run on the LarkBox. Installation: `/opt/containers/vinted-minipc-watcher`; container: `vinted-minipc-watcher`.

```bash
# Health/status and next scheduled check
docker exec vinted-minipc-watcher python /app/monitor.py status
# Immediate real check (updates history and may notify)
docker exec vinted-minipc-watcher python /app/monitor.py check
# Restrict manual check to one source
docker exec vinted-minipc-watcher python /app/monitor.py check --source skelbiu
# Recent logs / follow logs
docker logs --tail 100 vinted-minipc-watcher
docker logs --follow --tail 100 vinted-minipc-watcher
# Matches, recent reports and above-target watchlist
docker exec vinted-minipc-watcher python /app/monitor.py matches
docker exec vinted-minipc-watcher python /app/monitor.py reports
docker exec vinted-minipc-watcher python /app/monitor.py watchlist
# Replace ID with an actual stored identity
docker exec vinted-minipc-watcher python /app/monitor.py history --id 'skelbiu:88410680'
# Preview the daily summary without sending it
docker exec vinted-minipc-watcher python /app/monitor.py preview-daily
# Explicitly retry retained pending Telegram reports
docker exec vinted-minipc-watcher python /app/monitor.py retry
# Pause/resume monitoring; manual checks remain explicit actions
docker exec vinted-minipc-watcher python /app/monitor.py disable
docker exec vinted-minipc-watcher python /app/monitor.py enable
# Restart only this container
docker restart vinted-minipc-watcher
```

Manual checks do not move recurring slots. Docker resumes the service after reboot when Docker starts, unless deliberately stopped.

## Settings

Secrets stay in the live `.env` file (never commit it). Read-only configuration is mounted from `config/`. Preserve existing settings when updating.

| Setting | Deployed value/purpose |
| --- | --- |
| `TIMEZONE` | `Europe/Vilnius` |
| `SCHEDULE` | `half_hourly` |
| `NOTIFY_MODE` | `deals_and_daily` |
| `DAILY_REPORT_TIME` | `19:00` |
| `MIN_RAM_GB` | `12` |
| `NEGOTIATION_MARGIN_PERCENT` | `20` |
| `MAX_ASKING_PRICE_EUR` | Default absolute cap `175` |
| `BUYER_MARKET` | `LT` |
| `ALLOWED_SELLER_COUNTRIES` | `LT,PL,FI,LV,EE` |
| `EVIDENCE_RETENTION_DAYS` | `30` |
| `EVIDENCE_MAX_MB` | `512`, soft diagnostic size target |
| `RETENTION_DAYS` | Backup retention; price history is not pruned |
| `ENABLE_TELEGRAM` | Enabled with locally configured token/chat |

CPU ceilings and approval: `config/cpu-policy.json`. Browser query/budget/pagination bounds: `config/browser.json`, `config/skelbiu.json`. Bounded retry/incident thresholds: `config/recovery.json`. Brave remains unconfigured. Access authorization is a private local record; do not publish it.

After `.env` changes:

```bash
cd /opt/containers/vinted-minipc-watcher
docker compose up -d --force-recreate watcher
```

## Manual checkout verification

Public-page shipping prices do not prove delivery to your Lithuanian address. The browser records explicit displayed buyer fees and shipping starting prices where available. Starting prices remain lower bounds, with the delivered estimate incomplete.

Export an editable template for a real stored listing:

```bash
cd /opt/containers/vinted-minipc-watcher
docker exec vinted-minipc-watcher python /app/monitor.py verification-template --id 'vinted:LISTING_ID' > data/verification.json
nano data/verification.json
```

Manually open the listing and checkout for the actual destination. Recheck hardware, current asking price and availability too. Fill `observed_at` with the actual review time and UTC offset, `evidence_source` with a clear source note, and `details_confirmed: true` only after checking the supplied hardware details. Availability and delivery need their own explicit evidence. Use `DIRECT_LT_CONFIRMED` only if checkout offers the Lithuanian destination.

Each known cost requires `amount`, `currency`, `status` (`confirmed` or `estimated`), `source` and `timestamp`. Unknowns stay null/UNKNOWN. Zero additional charges require evidence too. A forwarding route needs explicit feasibility plus separate forwarding/local delivery components. Do not treat a checkout-only review as fresh hardware verification.

Import the reviewed file:

```bash
cp data/verification.json data/inbox/checkout-verification.json
docker exec vinted-minipc-watcher python /app/monitor.py check
```

## Tests

Latest deployed version: **355 tests passed** on host and in container. Ordinary tests do not make live marketplace requests. Run with strict-target defaults for the historical policy regressions; dedicated tests separately exercise the 20% negotiation setting:

```bash
docker exec -e NEGOTIATION_MARGIN_PERCENT=0 vinted-minipc-watcher python -m unittest discover -s /tests -q
```

An isolated smoke run uses a temporary database with external sources and Telegram disabled; it is not a live search:

```bash
docker exec vinted-minipc-watcher python /app/monitor.py check --dry-run
```

## Backups and diagnostic cleanup

```bash
docker exec vinted-minipc-watcher python /app/monitor.py backup
docker exec vinted-minipc-watcher python /app/monitor.py cleanup
```

Backups are in `backups/`; copy them off-device. Cleanup removes eligible old timestamped browser-evidence directories, while preserving two recent days and active incidents. Its size target can be exceeded by protected evidence. It does not prune SQLite history, backups or manual imports.

Restore a selected backup with monitoring stopped, preserving the current database first:

```bash
cd /opt/containers/vinted-minipc-watcher
docker compose stop watcher
mkdir -p data/pre-restore-$(date +%Y%m%dT%H%M%S)
# Move watcher.sqlite plus any -wal/-shm files into the new directory.
# Copy the selected known-good backup to data/watcher.sqlite.
# Keep ownership accessible to container UID 1000, then:
docker compose up -d watcher
docker exec vinted-minipc-watcher python /app/monitor.py status
```

## Updates and removal

Back up first. Review the selected code revision, tests and configuration before rebuilding. The live directory is not a Git checkout: `git pull` there is not an update procedure. Do not replace the live `.env`, private authorization, persistent data or backups with repository examples. Consult [DEPLOYMENT.md](DEPLOYMENT.md) for snapshot differences.

```bash
cd /opt/containers/vinted-minipc-watcher
docker compose build watcher
docker compose up -d watcher
```

Stop/remove only this Compose project with `docker compose down` from that directory. Data/backups remain until deliberately archived or removed. Do not use global Docker cleanup commands or alter unrelated services.

## Limits and privacy

No full-catalogue coverage, automatic purchase, authenticated checkout, guaranteed relist deduplication or live shipping guarantee is claimed. Source errors are not zero stock. Listing IDs are stable within each marketplace, while new IDs on relisted products may create new candidates. Seller claims may be incorrect. Telegram retries reduce duplicates but cannot guarantee exactly-once delivery.

Repository content excludes `.env`, credentials, private authorization, databases, imports, browser captures and logs. Historical reports are dated records, not current status. Previously reviewed Vinted/ECB/PirkEU sources are references, not a fresh certification of current terms or tariffs.
