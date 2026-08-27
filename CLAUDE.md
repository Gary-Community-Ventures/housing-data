# Housing Navigator rental collector

Collects rent + availability for Denver-metro market-rate apartments from each
property's OWN marketing site, normalizes it into comparable records, and keeps
a daily time series. Feeds a foundation civic tool whose partnerships depend on
a clean provenance story.

## Non-negotiable rules (enforced in code, do not weaken)
- Every network request goes through `hn/policy.py:Fetcher.get()` — the ONLY
  path to the network. Denylist (leasing vendors + listing aggregators),
  robots.txt, per-host rate limit, honest UA live there.
- Terms are checked per host EVERY run (`hn/terms.py`); PROHIBITS -> drop the
  host and delete its data. Never argue clause scope ("we'd win that argument"
  is not the bar). CAPTCHAs are never solved.
- No listing photographs are collected or stored.

## Run it
- `./.venv/bin/python run_daily.py` — the ONLY supported end-to-end entry point
  (fcntl-locked; order matters: validate's flags feed normalize).
- Fresh clone: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
  then `.venv/bin/python -m hn.history restore` to rehydrate live data from the
  latest committed snapshot. UI: `web/app.py` -> http://127.0.0.1:5050.
- Tests: `tests/test_reference.py` (hand-verified ground truth — Ten50 prices
  match the browser to the cent) and `tests/test_normalize.py`. Run both after
  ANY extractor or normalize change.

## Domain traps that already bit us (all covered by tests)
- Rent is not one number: lease term moves the same unit up to 2.7x
  (`rent_term_matrix`), fees vs base rent differ (~$49/mo), student housing
  prices PER BED (`rent_basis`), concessions are "up to" ceilings.
  `comparable_rent` = all-in, whole unit, 12-month, pre-concession.
- Jonah Digital's matrix prices are BASE; its quoted price is ALL-IN.
- `/cdn-cgi/challenge-platform` in HTML is NOT a bot block (passive beacon).
- An outbound "Apply Now" link to a denylisted vendor does NOT make a site
  vendor-hosted; only self-identifying footers/hosts do.
- Time series: history is DERIVED from snapshots (`hn/history.py`), never
  collected. Hosts that fail a day are "unobserved", not "unlisted".
- Never coordinate background steps with pgrep (self-matching deadlocks);
  use the run_daily.py lock.

## Key docs
`reports/ASSESSMENT.md` (feasibility + risks), `reports/DISCLOSURE.md`
(fee/term disclosure findings), `reports/COVERAGE.md` (candidate universe),
`README.md` (pipeline reference).
