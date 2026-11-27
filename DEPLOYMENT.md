# Deployment and repository snapshots

Updated 27 November 2026.

The repository now includes the latest deployed application source, regression tests, Docker Compose/browser build, and safe configuration examples. This includes negotiation alerts, compact RAM/M.2 parsing, missing-item handling, quiet price-increase history, daily negotiation counts, two-page discovery, displayed fee evidence, checkout templates and diagnostic retention.

The live installation is `/opt/containers/vinted-minipc-watcher` and is not a Git checkout. Container: `vinted-minipc-watcher`. The separate Git checkout publishes to https://github.com/mantaspeciukevicius/V1nted-minipc-watcher . Source files were copied from that installation; the example environment was aligned with half-hourly Lithuanian-buyer monitoring while leaving credentials and direct access disabled.

The latest synchronized suite contains **355 tests**. Deployed policy changes, source credentials and authorization are intentionally not imported into a fresh clone automatically. Existing policy regressions use a zero negotiation margin by default; dedicated negotiation tests exercise the configured 20% allowance.

Not published: live `.env` or editor copies, bot tokens/chat destination, API keys, private authorization, database, imports, logs, browser evidence or backups. `config/market-policy.json` is a public-source policy note, not a private authorization record.

A fresh installation needs its own local `.env`, writable data/inbox/backups directories for container UID 1000, and explicit access authorization before enabling browser sources. Never overwrite existing deployment settings or persistent state from repository examples. Review source access rules before enabling any adapter. See [README.md](README.md) and [BROWSER.md](BROWSER.md).

This publication updates the repository; it does not restart, replace or reconfigure the running service.
