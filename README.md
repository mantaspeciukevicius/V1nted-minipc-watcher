# Vinted Mini PC Watcher

A small Python and SQLite application for monitoring mini PC candidates, retaining price history and sending Telegram notifications. Designed for an always-on Ubuntu home server with Docker Compose.

- Intel **N100, N97 or N150**, with at least **16 GB installed RAM**.
- **Hourly checks** in Europe/Vilnius; notifications for new candidates and price-drop events.
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
