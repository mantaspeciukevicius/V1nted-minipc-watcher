# Public-browser source operation

Updated 27 November 2026; deployed behavior, subject to [DEPLOYMENT.md](DEPLOYMENT.md).

Vinted.lt and Skelbiu.lt use ordinary Chromium/Playwright navigation and rendered page content. The owner supplied explicit authorization locally. No login/session import, private API, stealth plugin, CAPTCHA solver or bypass is implemented. Authorization is not independently certified by this document.

Sources stop at access challenges, login redirects and HTTP 401/403/429, recording a pause gate. Inspect evidence and access authorization before resuming. Never remove a gate as a substitute for resolving a restriction.

```bash
docker exec vinted-minipc-watcher python /app/monitor.py browser-resume --source vinted
# Or after resolving Skelbiu access:
docker exec vinted-minipc-watcher python /app/monitor.py browser-resume --source skelbiu
```

Searches use the Lithuanian buyer catalogue and rotating terms. `max_search_pages: 2` follows a visible next/second-page link on the same host. Actual pages and coverage are reported; no pagination link means only the current page was read. Existing run budgets/detail caps remain. Broader pages do not establish completeness.

Vinted item 404/410 plus an explicit not-found page marks that item REMOVED and resolves its individual incident. Generic error pages, source/search errors and blocked access do not mark items removed. Other detail failures continue within the bounded plan unless access restrictions require stopping.

Transient network/server failures receive at most one bounded retry with the original deadline; a browser crash can restart the browser within that deadline. Repeated failures produce persistent incident notifications, resolved only by matching successful checks. Unrelated successful searches do not erase a failing detail incident.

Evidence lives in `data/browser-evidence` and `data/skelbiu-evidence`. Daily retention defaults to 30 days and 512 MiB target, preserving recent and unresolved-incident evidence. A protected set can exceed the target. These files and private authorization records must not be published.

Visible fee-inclusive EUR totals are compared with an independent current asking-price line to derive the displayed buyer fee. English and Lithuanian labels are supported. Shipping “from” amounts remain lower bounds and cannot confirm checkout eligibility or complete delivered costs. See the manual verification workflow in [README.md](README.md).
