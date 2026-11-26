> Historical implementation/research record. Current deployment and later changes: [PROJECT.md](PROJECT.md) and [DEPLOYMENT.md](DEPLOYMENT.md). Test totals and publication statements below apply to the original report, not the latest version.

# CPU policy research — 20 November 2026

The original eleven price ceilings and comparison percentages come from the owner. They remain unchanged. Percentages are user estimates, not benchmark measurements. Purchase ceilings are preferences, not market valuations. CPU nominal power never implies computer wall power; every device has unknown idle power until sourced measurements are supplied.

## Additional approved models

| Model | Nominal CPU power | Ceiling | Rationale |
|---|---:|---:|---|
| Ryzen 5 5625U | 15 W default TDP | €150 | Same conservative ceiling as the approved 5600U. Notebookcheck's directly reported multi-benchmark rating places 5625U alongside 5600U and 7530U. No premium for unverified device idle power. |
| Ryzen 5 7530U | 15 W default TDP | €150 | Six Zen 3 cores / twelve threads; Notebookcheck's measured rating is close to 5600U. Same €150 ceiling rather than increasing the owner's spending. |

Evidence reviewed before activation:

- [AMD 5625U specification](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-5000-series/amd-ryzen-5-5625u.html): default TDP 15 W.
- [AMD 7530U specification](https://www.amd.com/en/products/processors/laptop/ryzen/7000-series/amd-ryzen-5-7530u.html): default TDP 15 W.
- [Notebookcheck 7530U measurements](https://www.notebookcheck.net/AMD-Ryzen-5-7530U-Processor-Benchmarks-and-Specs.681702.0.html): reported aggregate performance rating 40.9 for 7530U, 40.2 for 5625U, 39.7 for 5600U. These aggregate ratings are a separate dataset; they are not converted into the owner's N100 percentages. Device cooling and configured power limits materially affect actual results.

## Completed additional policy review

The following ten models also passed the initial policy review. These are conservative purchase preferences, documented before activating the configuration; they are not estimates of current retail value. All require a complete mini PC with at least 16 GB installed RAM and remain subject to device-level evidence.

| Model | Nominal CPU power | Activated ceiling | Comparison rationale |
|---|---:|---:|---|
| Core i3-N300 | 7 W base | €130 | PassMark reports 7,920 CPU Mark; a modest premium over the owner's N100 ceiling, comparable to the 4300U budget. |
| Core i3-N305 | 15 W base | €140 | PassMark reports 9,333 CPU Mark; stronger than N300 but no premium over the owner's 5300U budget. |
| Core 3 N350 | 7 W base | €130 | PassMark list reports 7,472 CPU Mark; same conservative budget as N300, not a presumed generational upgrade. |
| Core 3 N355 | 15 W base | €150 | PassMark list reports 10,456 CPU Mark; capped at the owner's upper Ryzen budget. |
| Ryzen 3 5425U | 15 W TDP | €140 | PassMark's submitted results outperform 5300U; retain the same €140 ceiling without charging a premium for the model number. |
| Ryzen 5 4500U | 15 W TDP | €140 | Six-core Zen 2; directly measured TechSpot review establishes capable CPU performance. Discount below the owner's newer 5500U/5600U ceiling. |
| Ryzen 5 4600U | 15 W TDP | €150 | Six cores/twelve threads; PassMark comparison establishes stronger multi-thread performance than 4500U. Cap at the owner's 5500U ceiling. |
| Ryzen 5 7520U | 15 W TDP | €130 | PassMark comparison reports 8,896 CPU Mark. Conservative ceiling below 5300U; explicitly require the offered 16 GB configuration. |
| Ryzen 7 5800U | 15 W TDP | €150 | PassMark reports 17,916 CPU Mark; use the owner's 5700U ceiling, with no premium for unmeasured device efficiency. |
| Ryzen 7 5825U | 15 W TDP | €150 | PassMark reports 17,767 CPU Mark; use the same ceiling as 5700U/5800U. |

Primary benchmark and specification evidence:

- [Intel N-series launch specifications](https://download.intel.com/newsroom/2023/client-computing/Intel-N-series-Processors-Media_Presentation.pdf): N300/N305/N200 power, cores and memory types.
- [Intel N350/N355 product brief](https://cdrdv2-public.intel.com/763908/n-series-processors-product-brief.pdf): exact 7 W/15 W processor base power.
- [PassMark N300](https://www.cpubenchmark.net/cpu.php?cpu=Intel+Core+i3-N300), [N305](https://www.cpubenchmark.net/cpu.php?cpu=Intel+Core+i3-N305&id=5213), and [full CPU list](https://www.cpubenchmark.net/cpu-list/all): submitted benchmark aggregates, reviewed 20 November 2026. Scores change with samples and system power limits; none is stored as an N100-relative reference percentage.
- [AMD 5425U specifications](https://www.amd.com/es/support/downloads/drivers.html/processors/ryzen/ryzen-5000-series/amd-ryzen-3-5425u.html), [4500U specifications](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-4000-series/amd-ryzen-5-4500u.html), and [AMD-authored business reference guide hosted by HP](https://valuehub.hp.com/static/amd/docs/AMD-10451%20AMD%20Ryzen%20for%20Business%20QRG%20Hawk%20PRO%20Reference%20Guide.pdf): exact CPU configurations and nominal TDP, including 4600U.
- [AMD consumer pocket guide](https://www.amd.com/content/dam/amd/en/documents/partner-hub/ryzen/amd-consumer-pocket-guide-ryzen-radeon-july-2024.pdf): 5800U/5825U product specifications.
- [PassMark 5425U vs 5300U](https://www.cpubenchmark.net/compare/4715vs4288/AMD-Ryzen-3-5425U-vs-AMD-Ryzen-3-5300U), [4600U vs 4500U](https://www.cpubenchmark.net/compare/AMD-Ryzen-5-4600U-vs-AMD-Ryzen-5-4500U/3725vs3702), [5800U and 5825U](https://www.cpubenchmark.net/compare/4102vs4788vs5215vs4750vs6016/AMD-Ryzen-7-5800U-vs-AMD-Ryzen-7-5825U-vs-AMD-Ryzen-7-7730U-vs-Intel-i5-12500H-vs-AMD-Ryzen-7-8840HS), and the N305 comparison above which includes 7520U.
- [TechSpot's measured 4500U review](https://www.techspot.com/review/2045-amd-ryzen-4500u/): measured workload results rather than an inferred model-number comparison.

N200 and N250 remain recognized, searched and under manual review with no active ceiling. Their reviewed submitted CPU Mark aggregates are below N100, so nominal 6 W ratings alone do not establish an improvement for this owner's reference workload. A particular device can still be evaluated manually. This completes the initial evaluation of all fourteen proposed extra models; future unknown models still require research. No device-level idle consumption was established by this CPU research.

Primary references for the two manual-review outcomes: [N100/N200 submitted benchmark comparison](https://www.cpubenchmark.net/compare/5157vs5178/Intel-N100-vs-Intel-N200/1000), [N250 submitted results](https://www.cpubenchmark.net/cpu.php?cpu=Intel+N250&id=6398), and [Intel N250 specifications](https://www.intel.com/content/www/us/en/products/sku/241637/intel-processor-n250-6m-cache-up-to-3-80-ghz/specifications.html).
