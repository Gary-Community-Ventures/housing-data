# Platform Fingerprint Breakdown

_Generated 2026-08-27 18:36 UTC_

Which site builders expose structured rent and availability, measured by outcome per detected platform.

| Platform / builder | Sites | Yielded rent | Yielded availability | Structure only | Nothing | Blocked | Rent behind portal | Rows | Rent yield |
|---|---|---|---|---|---|---|---|---|---|
| unknown | 374 | 25 | 11 | 30 | 66 | 37 | 40 | 526 | 6.7% |
| WordPress | 197 | 50 | 32 | 4 | 143 | 0 | 33 | 961 | 25.4% |
| Jonah Digital | 121 | 116 | 118 | 0 | 3 | 0 | 1 | 5,422 | 95.9% |
| Funnel / Nestio | 104 | 56 | 52 | 0 | 38 | 0 | 25 | 794 | 53.8% |
| Next.js | 38 | 9 | 9 | 0 | 29 | 0 | 0 | 75 | 23.7% |
| Drupal | 21 | 0 | 0 | 1 | 20 | 0 | 0 | 1 | 0.0% |
| ActiveBuilding CMS | 13 | 5 | 1 | 0 | 8 | 0 | 8 | 27 | 38.5% |
| Duda | 10 | 0 | 0 | 0 | 10 | 0 | 8 | 0 | 0.0% |
| Wix | 5 | 1 | 0 | 0 | 4 | 0 | 0 | 2 | 20.0% |
| Respage | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0% |
| Webflow | 2 | 1 | 0 | 0 | 1 | 0 | 0 | 3 | 50.0% |
| Nuxt | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0.0% |
| Squarespace | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0.0% |

## Which extraction layer won

| Layer | Sites where it produced the best result |
|---|---|
| L1:jonah | 112 |
| L1b:spaces | 81 |
| L4:html-join | 56 |
| L3:jsonld | 34 |
| L2:json-island | 14 |
| L4:html-join+plan-pages(8) | 1 |
| +plan-pages(5) | 1 |
| +plan-pages(7) | 1 |

**Layer definitions**

- **L1** — platform-specific JSON island. Jonah Digital publishes a complete `<script type="application/json" id="jd-fp-data-script-app">` blob with one record per *available apartment*: unit number, exact rent, base rent, square footage, available date, building.
- **L2** — generic framework/JSON island scan (`__NEXT_DATA__`, `__NUXT__`, any `application/json` script) matched heuristically on rent-ish + bed-ish keys.
- **L3** — schema.org JSON-LD, walked recursively. Floor plan structure and availability counts; rarely carries rent.
- **L4** — rendered-HTML card parse. Lowest confidence, used as a fallback.

