# Operations runbook

## Fresh machine

```bash
git clone <repo> && cd housing-data
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m hn.history restore        # rehydrate live data from latest snapshot
.venv/bin/python tests/test_reference.py && .venv/bin/python tests/test_normalize.py
.venv/bin/python web/app.py                   # UI at http://127.0.0.1:5050
```

## Daily run

```bash
.venv/bin/python run_daily.py        # collect → clean → validate → normalize → report → snapshot
```
- fcntl-locked; a second invocation exits with code 2. Never run stages by hand
  in a different order (normalize depends on validate's flags).
- ~70 min for ~950 sites at polite rates. Logs: `logs/daily_<date>.log`,
  status: `logs/daily_status.json`.
- Scheduling: `./setup_schedule.sh` (launchd, 06:10) — machine must be awake.
  Preferred long-term: an always-on box or scheduled cloud runner that commits
  `data/history/` back. At ~15%/day unit repricing, missed days lose real events.
- After a run, commit the new snapshot: `git add data/history logs/terms_audit.jsonl reports && git commit`.

## After changing an extractor or normalizer

1. Run both test suites. The Ten50 fixture is hand-verified against the
   browser-rendered page to the cent — if it fails, the change is wrong.
2. Re-extract WITHOUT re-fetching where possible (raw HTML is cached in
   `data/raw/`), or re-run affected sites only:
   `.venv/bin/python rerun_subset.py --layer "L1:jonah"` or `--outcomes C_nothing`.
3. Re-run cleanup → validate → normalize → report, then `hn.history snapshot <today>`
   to fold corrections into today's snapshot. History diffs recompute automatically.

## Adding candidates

Drop a `data/candidates_<name>.json` file (`{"communities":[{name, operator,
city, state, marketing_url, source, …}]}`). Next run picks it up; dedup is by
(name, host). Enumeration helpers: `enum_operators.py` (operator sitemaps),
`hn/osm.py` (Overpass). Never enumerate from listing aggregators.

## Monitoring — what to alarm on

- **Per-PLATFORM row-count deltas**, not just per-site. Jonah Digital supplies
  ~⅔ of all rows; a Jonah page-contract change is the #1 structural risk and
  looks like a cliff in `reports/report.json → platforms`.
- New `F_dropped_terms_prohibit` outcomes (standing terms check caught someone).
- `data quality → implausible` above ~1%: an extractor is inventing numbers.
- Mass "unlisted" events concentrated in one host: usually a site failure, and
  the series already suppresses these — but check `site_results` for G/E outcomes.

## Known limits

- 6 hosts CAPTCHA-gated (never solved), ~131 vendor-hosted (skipped), 113 hosts
  terms-dropped, ~88 sites publish structure but keep rent behind a denylisted
  portal. That ~30% is policy, not a bug. Browser-recovered (L5) hosts go stale
  unless manually refreshed; the time series excludes stale rows automatically.
