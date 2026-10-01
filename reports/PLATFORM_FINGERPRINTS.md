# Platform Fingerprint Breakdown

_Generated 2026-10-01 18:33 UTC_

Which site builders expose structured rent and availability, measured by outcome per detected platform.

| Platform / builder | Sites | Yielded rent | Yielded availability | Structure only | Nothing | Blocked | Rent behind portal | Rows | Rent yield |
|---|---|---|---|---|---|---|---|---|---|
| unknown | 364 | 28 | 9 | 28 | 64 | 44 | 38 | 536 | 7.7% |
| WordPress | 199 | 51 | 33 | 4 | 144 | 0 | 34 | 904 | 25.6% |
| Jonah Digital | 125 | 120 | 123 | 0 | 2 | 0 | 0 | 6,026 | 96.0% |
| Funnel / Nestio | 108 | 56 | 53 | 0 | 39 | 0 | 27 | 1,222 | 51.9% |
| Next.js | 38 | 9 | 9 | 0 | 29 | 0 | 0 | 82 | 23.7% |
| Drupal | 21 | 1 | 0 | 0 | 20 | 0 | 0 | 7 | 4.8% |
| ActiveBuilding CMS | 13 | 5 | 1 | 0 | 8 | 0 | 8 | 28 | 38.5% |
| Duda | 11 | 0 | 0 | 0 | 11 | 0 | 9 | 0 | 0.0% |
| Wix | 6 | 1 | 0 | 0 | 4 | 0 | 0 | 2 | 16.7% |
| Respage | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% |
| Nuxt | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0.0% |
| Webflow | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 3 | 100.0% |
| Squarespace | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0.0% |

## Which extraction layer won

| Layer | Sites where it produced the best result |
|---|---|
| L1:jonah | 118 |
| L1b:spaces | 84 |
| L4:html-join | 57 |
| L3:jsonld | 32 |
| L2:json-island | 14 |
| L4:html-join+plan-pages(8) | 1 |
| +plan-pages(5) | 1 |
| +plan-pages(7) | 1 |

**Layer definitions**

- **L1** — platform-specific JSON island. Jonah Digital publishes a complete `<script type="application/json" id="jd-fp-data-script-app">` blob with one record per *available apartment*: unit number, exact rent, base rent, square footage, available date, building.
- **L2** — generic framework/JSON island scan (`__NEXT_DATA__`, `__NUXT__`, any `application/json` script) matched heuristically on rent-ish + bed-ish keys.
- **L3** — schema.org JSON-LD, walked recursively. Floor plan structure and availability counts; rarely carries rent.
- **L4** — rendered-HTML card parse. Lowest confidence, used as a fallback.

