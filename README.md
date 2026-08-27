# Housing Navigator — market-rate rental collector

Collects **availability and asking rent** for market-rate apartments in the Denver
metro from each property's **own marketing website**, and normalizes it into
records a housing navigator can query.

Built for a foundation-funded civic tool whose partnerships depend on a clean
provenance story, so the compliance rules are enforced in code, not in a policy
document that the code might drift from.

## Quick start

```bash
python3 -m venv .venv && ./.venv/bin/pip install requests beautifulsoup4 lxml flask

# 1. build the candidate list (OpenStreetMap; operator portfolios are checked in)
./.venv/bin/python -c "import sys;sys.path.insert(0,'.');from hn.osm import *;import json;json.dump(to_candidates(fetch_osm()),open('data/candidates_osm.json','w'))"

# 2. collect
./.venv/bin/python run_collect.py --workers 14 --delay 3 --shuffle

# 3. clean names/cities, fill missing lat-long from the US Census geocoder
./.venv/bin/python -m hn.cleanup

# 4. flag implausible rows, then make rents comparable across sites
./.venv/bin/python -m hn.validate
./.venv/bin/python -m hn.normalize

# 5. build reports
./.venv/bin/python -m hn.report && ./.venv/bin/python -m hn.report_md

# 6. browse it
./.venv/bin/python web/app.py     # http://127.0.0.1:5050
```

## Daily runs / time series

```bash
./.venv/bin/python run_daily.py       # one locked end-to-end pass
./setup_schedule.sh                   # install a 06:10 daily run via launchd
```

`run_daily.py` is the only supported way to run the pipeline end to end: it holds a
real `fcntl` lock for the whole run (ad-hoc process coordination deadlocked and once
left data half-normalized), deletes the live JSONL files so each day observes today's
state, then snapshots to `data/history/<date>/` (gzipped, one per calendar day) and
rebuilds `reports/timeseries.json`.

History is derived, not collected: diffs (listed / unlisted / rent_change,
days-on-market) are computed from snapshots by `hn/history.py`, so they can be
re-derived after any parser fix. Rows from stale sources (e.g. browser-recovered
pages not refreshed that day) are excluded from a day's observations rather than
counted as stable, and their disappearance is not an "unlisted" event. The UI's
**Trends** tab reads the result.

Run order matters: `normalize` reads the `plausible` flag that `validate` sets.

```bash
# extra passes
./.venv/bin/python enum_operators.py         # candidates from operator sitemaps
./.venv/bin/python probe_terms.py            # read denylisted hosts' own terms
./.venv/bin/python reaudit_terms.py          # re-check every terms verdict
./.venv/bin/python drop_prohibited.py        # delete data from prohibiting hosts
./.venv/bin/python rerun_subset.py --outcomes C_nothing   # retry after a parser fix
./.venv/bin/python tests/test_reference.py && ./.venv/bin/python tests/test_normalize.py
```

## What comes out

One row per **available apartment** where the site exposes unit-level data,
otherwise one row per floor plan.

**Identity & location** — property name, operator, street, city, state, postal code,
lat/long (from schema.org, else the US Census geocoder).

**The unit** — floor plan, unit number, building, bedrooms, bathrooms, sq ft,
available date, lease term, unit tags.

**Rent, normalized so it is actually comparable** — see below.

**Provenance** — source URL, collected-at, extraction layer, confidence +
the reasons for it, cost completeness + what is missing.

### Why raw rent is not comparable, and what we do about it

Four independent traps in this data, all of which produce wrong advice if ignored:

| Trap | Example found | Field |
|---|---|---|
| **Lease term** | A Griffis unit is $4,133 on a 2-month term and $1,552 on 15 months — 2.7x for the same apartment | `rent_12mo`, `rent_term_matrix`, `rent_12mo_method` |
| **Fee inclusion** | Ten50 quotes $1,748.70 all-in; base rent is $1,710.00 | `base_rent_month`, `all_in_rent_month`, `mandatory_fees_monthly` |
| **Rent basis** | A "$631 five-bedroom" is one bed in a 5×5 student lease; the unit is ~$3,155 | `rent_basis`, `rent_per_unit_month`, `rent_per_bed_month` |
| **Concessions** | "Up to 12 weeks free" cuts effective rent ~19% | `concession_months_free`, `effective_rent_12mo` |

Everything resolves to one number, **`comparable_rent`**: the all-in monthly cost of
the **whole unit** on a **12-month term**, **net of concessions**. Plus
`rent_per_bed_month` and `rent_per_sqft_month` for cross-format comparison, and
`market_rate` / `income_restricted` so an income-restricted unit never silently
lands in a market-rate median.

Nothing is silently assumed: `normalization_notes` records every derivation, and a
rent quoted on a non-standard term with no published matrix is flagged rather than
converted.

### Two confidence axes, kept separate

- **`confidence`** — do we believe this is the rent for this unit? Driven by *where
  the number came from*. Fix by writing a better extractor.
- **`cost_completeness`** — how much of the true monthly cost we know. Fix requires
  the landlord to publish a fee schedule.

Folding these together made confidence unactionable, so they are reported apart.

## Compliance rules, and where they live in the code

| Rule | Enforced in |
|---|---|
| 1. Vendor leasing-engine domains are never requested, followed, or parsed | `hn/policy.py` — `is_denied()`, checked again after every redirect |
| 2. No API token is ever harvested from page source | no code path reads tokens; `api.rentcafe.com` is denylisted |
| 3. Vendor-hosted marketing sites are skipped entirely | `hn/policy.py` — `vendor_hosted_by_host()`, `hn/extract.py` — `vendor_hosted()` |
| 4. Per-site terms check, logged, on every run | `hn/terms.py` → `logs/terms_audit.jsonl` |
| 5. robots.txt respected; polite per-host rate limit; honest UA with contact URL | `hn/policy.py` — `Fetcher` |
| 6. No photographs collected or stored | `hn/extract.py` strips image fields; `Collector._store_meta` filters them |

Every outbound request in the project goes through `Fetcher.get()`. There is no
other path to the network, so the rules cannot be bypassed by a new caller.

## Layout

```
hn/policy.py      denylist, vendor detection, robots, rate limit, HTML cache
hn/terms.py       terms discovery + prohibition classifier (conservative)
hn/extract.py     platform fingerprinting + 4 extraction layers
hn/collect.py     per-property orchestration, outcome classification
hn/osm.py         OpenStreetMap enumeration via Overpass
hn/operator_enum.py  property-page discovery from operator sitemaps
hn/normalize.py   lease-term / fee / per-bed / concession normalization
hn/validate.py    plausibility gate (flags, never silently drops)
hn/browser_parse.py  parse browser-rendered text for hosts that refuse HTTP
hn/cleanup.py     name/city normalization + Census geocoding
hn/report.py      yield / platform / terms rollup  -> reports/report.json
hn/report_md.py   markdown deliverables
run_collect.py    parallel runner (per-host serialized)
web/              internal browsing UI (Flask + Leaflet)
```

## Attribution

- Property enumeration partly from **OpenStreetMap** — © OpenStreetMap
  contributors, ODbL 1.0.
- Geocoding of addresses missing coordinates: **US Census Bureau** geocoder
  (public domain).
- Rent and availability: each property's own marketing website, recorded per row
  in `source_url` with a collection timestamp.
