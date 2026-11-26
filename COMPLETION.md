# Latest implementation verification

Documentation updated: 27 November 2026.

The deployed app includes half-hourly Vinted/Skelbiu checks, CPU-specific targets, 20% negotiation candidates, corrected compact RAM/M.2 parsing, removed-listing incident handling, quiet price-increase history, separate daily negotiation counts, two-page discovery, diagnostic retention and explicit checkout evidence templates.

Latest validation: **355 automated tests passed** on host and in the rebuilt container. A controlled live run completed with AUTHORIZED_BROWSER_CHECK: four Vinted queries and three Skelbiu queries, including second pages for all three frequent Vinted CPU terms and Skelbiu N100. Six unique observations were processed: five needed review and one was rejected; no fully confirmed deals were established. Saved rendered evidence successfully yielded buyer-fee and shipping-lower-bound fields using the latest parser.

The last checked service heartbeat/database were healthy and there were no pending Telegram reports. This is a dated observation, not a current status guarantee. No automatic checkout, purchase or complete catalogue verification is claimed.

See [PROJECT.md](PROJECT.md), [README.md](README.md) and [DEPLOYMENT.md](DEPLOYMENT.md). Older upgrade reports preserve their original test counts and scope.
