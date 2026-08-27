# Architecture

## Data flow

```
candidates (data/candidates_*.json)
   │  operator portfolios · operator sitemaps · OSM · Boulder licenses (all enumerated, never aggregators)
   ▼
run_collect.py ── per-host serialized workers; every request via Fetcher.get()
   │
   ├─ hn/policy.py   RULE 1/3/5: denylist (vendors + aggregators, incl. redirects),
   │                 vendor-host detection, robots.txt, ≥3s/host, honest UA, HTML cache
   ├─ hn/terms.py    RULE 4: per-host terms discovery + prohibition classifier,
   │                 EVERY run → logs/terms_audit.jsonl. PROHIBITS ⇒ drop host + data
   ├─ hn/collect.py  orchestration, outcome codes A…H, floor-plan page discovery
   └─ hn/extract.py  platform fingerprint + 5 extraction layers (below)
   ▼
data/listings.jsonl (+ listings_browser.jsonl for L5)
   ▼
hn/cleanup.py     name/city/street sanitation, Census geocoding
hn/validate.py    plausibility flags (order matters: normalize reads these)
hn/normalize.py   comparable_rent + term/fee/per-bed/concession normalization
   ▼
hn/report.py → reports/report.json → hn/report_md.py → reports/*.md
hn/history.py     daily gzip snapshot → derived time series (reports/timeseries.json)
web/app.py        read-only Flask UI on :5050
```

`run_daily.py` is the only supported end-to-end entry point: it holds an fcntl
lock for the whole run, clears the live derived files (each day observes today's
state; history keeps the past), executes the stages in order, then snapshots.

## Extraction layers (best result wins per site)

| Layer | Source | Granularity | Trust |
|---|---|---|---|
| L1 `jonah-json-island` | `<script id="jd-fp-data-script-app">` | unit (number, exact rent, base rent, term, matrix, fees, available date) | high |
| L1b `spaces-unit-json` | `const spacesUnitJSON = […]` | unit + 14-term price matrix (matrix is BASE rent — adjusted to all-in) | high |
| L2 `json-island` | any JSON in `<script type=application/json>`, framework globals, or **plain `var X = {…}` assignments** | varies | high/med |
| L3 `jsonld-graph-walk` | schema.org JSON-LD, walked **recursively** (top-level @graph parse finds nothing) | floorplan, rarely rent | med |
| L4 `html-card-join` | rendered HTML cards | floorplan | **low — never a production rent source** |
| L5 `browser-rendered-text` | real-browser text for hosts that 403 plain HTTP (robots.txt permits all of them) | floorplan | med |

Scoring prefers rent coverage > unit granularity > availability > structure; a
layer that finds plan structure without rent still beats nothing
(`B3_structure_only` outcome).

## Site outcome codes

`A` rent+availability · `B1` rent only · `B2` availability only · `B3` structure
only · `C` nothing · `D` vendor-hosted (skipped) · `E` bot-blocked · `F` terms
prohibit (dropped) · `G` unreachable · `H` denylisted (never requested)

## Design decisions worth knowing

- **Single network choke point.** No code path reaches the network except
  `Fetcher.get()` (plus the narrow `get_terms_document()` exception that may read
  a TERMS page on a denied host — legal-notice paths only, logged, never listings).
- **History is derived, never collected.** Diffs are recomputed from snapshots,
  so a parser fix retroactively fixes the series. Hosts that fail a day are
  "unobserved", not "unlisted"; stale L5 rows are excluded, not counted stable.
- **Validation flags, never deletes** — except terms-prohibited data, which IS
  deleted.
- **Two quality axes** (`confidence` vs `cost_completeness`) because their fixes
  have different owners (us vs the landlord).
- **Background jobs coordinate via the fcntl lock only.** pgrep-based waiting
  self-matches and deadlocks; it did, twice.
