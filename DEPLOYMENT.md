# Deployment and repository snapshots

Updated 27 November 2026.

The live installation is `/opt/containers/vinted-minipc-watcher`, a deployment directory without Git metadata. Its Docker container is `vinted-minipc-watcher`. The working Git checkout is separate. GitHub repository: https://github.com/mantaspeciukevicius/V1nted-minipc-watcher .

This publication updates **Markdown documentation only**. The repository code baseline before this documentation commit is `6556b79` (bounded recovery/source incidents). Subsequent deployed changes include negotiation alerts, the RAM/M.2 parser fix, missing-item 404 handling, daily negotiation counts, price-increase alert suppression, expanded pagination, fee evidence, verification templates and retention. Those deployed code/config/test changes are **not included in this documentation-only commit**.

Consequently, **355 tests** and commands such as `cleanup` and `verification-template` refer to the deployed installation. A fresh checkout of the current repository code does not yet contain all these capabilities. Do not treat these documents as proof that the repository source matches the running container. A separate reviewed source synchronization is needed for a complete redeployable latest-version snapshot.

Only Markdown copies were synchronized by this update. Live credentials, local authorization records, imports, database, browser evidence, backups and unrelated files were not uploaded. Historical report statements about publication are retained as historical statements; this manifest explains the current publication scope.
