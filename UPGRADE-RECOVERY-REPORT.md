> Historical implementation/research record. Current deployment and later changes: [PROJECT.md](PROJECT.md) and [DEPLOYMENT.md](DEPLOYMENT.md). Test totals and publication statements below apply to the original report, not the latest version.

# Bounded recovery and persistent source alerts — 2026-11-22

Implemented and deployed in the existing watcher, with no additional scheduler, database or Telegram process.

## Recovery behavior

- One retry for temporary navigation timeouts, recognized network failures and server errors, after a five-second default delay. Retries use the original marketplace deadline; browser-operation timeouts are capped by remaining time.
- A crashed/closed browser can be closed and replaced once before retrying. Replacement closes the original browser first and uses the same ordinary public-page access settings.
- Access restrictions, login requirements and rate limits stop and pause the source. HTTP 401/403/429 stop before extracting a response body. CAPTCHA checks remain stop signals. No retries/bypasses are applied to these restrictions, parser errors, HTTP 404s or expired run budgets.
- `config/recovery.json`: navigation_retries 0–1 (hard cap 1), retry_delay_seconds default 5 (bounded 3–15), persistent_failure_checks default 3 (minimum 2).

## Incident notifications

SQLite `app_settings` persists per-marketplace query/detail failure state. Three failed checks of an affected scope generate one incident notification through the existing outbox. Access restrictions notify immediately because monitoring is paused. Continued failures do not repeat the alert during the same open incident. Recovery requires successful checks for pending query/detail scopes; unrelated searches or disabled adapters cannot falsely clear an incident. An isolated transient failure that recovered before an alert does not produce a recovery message.

Incident state and the notification outbox commit in the same transaction. Existing message-part receipts, Telegram retries and daily deduplication remain intact. The other marketplace continues independently. `status` includes `failure_watch`; per-run funnel metrics and daily reports expose retry/recovery/restart counts when nonzero.

After evidence/access review, `browser-resume --source vinted` or `--source skelbiu` clears the respective manual access gate. Clearing a gate does not itself claim recovery. Parser changes and database problems still require investigation; this update does not automatically rewrite parsers, overwrite databases or evade access restrictions.

## Tests and live verification

Baseline: 287 tests passed. Updated suite: **324 tests passed** on host, inside the rebuilt container and in the GitHub publication copy. New tests simulate timeout/network/server recovery, exhausted budgets, hard retry caps, crash restart, immediate access stops, state persistence, deduplication, exact-query/detail recovery, rollback and durable outbox insertion. Both actual adapter paths were exercised with fake browser objects to verify close-before-restart and no body extraction/retry on HTTP access blocks. Synthetic tests sent no real Telegram messages.

Live run `cf56c4a0-4d20-4336-9e1b-3894f3dc0a28` completed in 149.824 seconds with `AUTHORIZED_BROWSER_CHECK`: four Vinted searches and three Skelbiu searches succeeded; each source successfully extracted two detail pages. No live failure required retry, so real outage recovery was not claimed. Retry/restart counters remained zero, both incident states were healthy, and no incident/recovery notification was generated.

Container running and healthy. Database integrity `ok`, foreign-key violations zero. Baseline listing, observation, price, availability, report and outbox identities preserved. No pending Telegram messages. Next scheduled check at verification: 2026-11-23 00:00 Europe/Vilnius. RAM minimum remains 12 GB, CPU ceilings and the 30-minute schedule are unchanged.

Verified backup before deployment: `watcher-20261122T213832.sqlite`; verified afterward: `watcher-20261122T214126.sqlite`. Original code/config/tests are preserved in `backups/upgrade-recovery-original/`. Credentials and unrelated services were not modified. No database schema migration was needed.

## Publication

Repository: mantaspeciukevicius/V1nted-minipc-watcher, branch main.
Commit: `6556b7976d04c9d716e9dcaad69178c842a1416a`.
All eight published files match the reviewed copy; secret scan found zero issues. Runtime data, credentials, backups and operational logs were excluded.

Evidence: `logs/upgrade-recovery-tests.txt`, `logs/upgrade-recovery-container-tests.txt`, `logs/upgrade-recovery-live-check.txt`, `logs/upgrade-recovery-status.json`.
