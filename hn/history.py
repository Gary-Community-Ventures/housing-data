"""
Time series over collection runs.

Each completed run is snapshotted into data/history/<YYYY-MM-DD>/ (gzipped, one
snapshot per calendar day -- a rerun on the same day overwrites, so the series
stays one observation per day). Diffs between snapshots are computed here, not
at collection time, so the collector stays a pure "what is on the page today"
instrument and history is derived, reproducible, and re-computable after a
parser fix.

Unit identity across runs:
  unit-level rows   -> (host, unit_number)
  floorplan rows    -> (host, plan_name, bedrooms, sqft)
A key that disappears is *unlisted* -- usually leased, but we only observe the
listing, so the event is named for what we saw, not what we infer.
"""
from __future__ import annotations
import gzip, json, os, shutil, statistics
from datetime import date, datetime, timezone

HISTORY_DIR = "data/history"
SNAPSHOT_FILES = ["listings.jsonl", "listings_browser.jsonl",
                  "site_results.jsonl", "properties.jsonl"]


def _host(u):
    try:
        return (u or "").split("/")[2].lower()
    except IndexError:
        return ""


def unit_key(r: dict) -> tuple | None:
    h = _host(r.get("source_url"))
    if not h:
        return None
    if r.get("unit_number"):
        return (h, "u", str(r["unit_number"]))
    if r.get("plan_name"):
        return (h, "p", str(r["plan_name"]), r.get("bedrooms"), r.get("sqft"))
    return None


def snapshot(run_date: str | None = None, data_dir="data") -> str:
    d = run_date or date.today().isoformat()
    out = os.path.join(HISTORY_DIR, d)
    os.makedirs(out, exist_ok=True)
    for f in SNAPSHOT_FILES:
        src = os.path.join(data_dir, f)
        if not os.path.exists(src):
            continue
        with open(src, "rb") as i, gzip.open(os.path.join(out, f + ".gz"), "wb") as o:
            shutil.copyfileobj(i, o)
    meta = {"snapshot_date": d,
            "created_at": datetime.now(timezone.utc).isoformat()}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"))
    return out


def snapshots() -> list[str]:
    if not os.path.isdir(HISTORY_DIR):
        return []
    return sorted(d for d in os.listdir(HISTORY_DIR)
                  if os.path.exists(os.path.join(HISTORY_DIR, d, "meta.json")))


def load_snapshot(d: str) -> list[dict]:
    rows = []
    for f in ("listings.jsonl.gz", "listings_browser.jsonl.gz"):
        p = os.path.join(HISTORY_DIR, d, f)
        if not os.path.exists(p):
            continue
        with gzip.open(p, "rt") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    return rows


def build_timeseries(out_path="reports/timeseries.json") -> dict:
    days = snapshots()
    if len(days) < 1:
        return {"days": [], "events": [], "note": "no snapshots yet"}

    # per-day keyed observations.
    #
    # Staleness: browser-recovered (L5) rows are only refreshed manually, so a
    # snapshot can carry rows collected days earlier. Treating them as live
    # would fake price stability; letting them vanish would fire phantom
    # "unlisted" events. So a row older than STALE_DAYS at snapshot time is
    # excluded from that day's observations, its key is remembered as stale,
    # and a disappearance explained by staleness is not an unlisting.
    STALE_DAYS = 2
    obs: dict[str, dict] = {}
    stale_keys: dict[str, set] = {}
    for d in days:
        day = {}
        stale = set()
        dd = date.fromisoformat(d)
        for r in load_snapshot(d):
            k = unit_key(r)
            if k is None:
                continue
            ca = (r.get("collected_at") or "")[:10]
            try:
                if ca and (dd - date.fromisoformat(ca)).days > STALE_DAYS:
                    stale.add(k)
                    continue
            except ValueError:
                pass
            day[k] = {"rent": r.get("comparable_rent") if r.get("comparable_rent") is not None else r.get("rent"),
                      "avail": r.get("units_available"),
                      "property": r.get("property_name"),
                      "beds": r.get("bedrooms"),
                      "conf": r.get("confidence")}
        obs[d] = day
        stale_keys[d] = stale

    # Hosts observed each day. A site that fails collection on day N makes all
    # of its units vanish, and one that recovers on N+1 makes them all
    # reappear -- neither is a leasing event. The top three "mass unlisting"
    # properties in the first real diff were exactly this (all three
    # G_unreachable that day). So listed/unlisted are only emitted for hosts
    # successfully observed on BOTH sides of the comparison; rent_change
    # already requires the key present on both days.
    hosts_of: dict[str, set] = {d: {k[0] for k in obs[d]} for d in days}

    events = []
    first_seen: dict[tuple, str] = {}
    for i, d in enumerate(days):
        prev = obs[days[i - 1]] if i else {}
        cur = obs[d]
        prev_hosts = hosts_of[days[i - 1]] if i else set()
        cur_hosts = hosts_of[d]
        for k, v in cur.items():
            if k not in first_seen:
                first_seen[k] = d
            if i and k not in prev:
                if k[0] not in prev_hosts:
                    continue  # host newly observed / recovered, not a new listing
                events.append({"date": d, "event": "listed", "key": list(k),
                               "property": v["property"], "rent": v["rent"]})
            elif i and k in prev:
                pr, cr = prev[k].get("rent"), v.get("rent")
                if pr and cr and abs(cr - pr) >= 1:
                    events.append({"date": d, "event": "rent_change", "key": list(k),
                                   "property": v["property"],
                                   "from": pr, "to": cr,
                                   "pct": round(100 * (cr - pr) / pr, 2)})
        if i:
            for k, v in prev.items():
                if k in cur:
                    continue
                if k in stale_keys.get(d, set()):
                    continue  # source went stale; we did not observe an unlisting
                if k[0] not in cur_hosts:
                    continue  # host failed collection today; units unobserved, not unlisted
                days_listed = (date.fromisoformat(d)
                               - date.fromisoformat(first_seen.get(k, days[0]))).days
                events.append({"date": d, "event": "unlisted", "key": list(k),
                               "property": v["property"], "last_rent": v.get("rent"),
                               "days_observed_listed": days_listed})

    # per-day market summary (high/medium confidence, market-rate comparable rents)
    daily = []
    for d in days:
        rents = [v["rent"] for v in obs[d].values()
                 if v.get("rent") and v.get("conf") in ("high", "medium")]
        daily.append({
            "date": d,
            "listings": len(obs[d]),
            "priced": len(rents),
            "median_comparable_rent": round(statistics.median(rents), 2) if rents else None,
        })

    ts = {"generated_at": datetime.now(timezone.utc).isoformat(),
          "days": daily,
          "n_events": len(events),
          "events": events[-5000:],
          "event_counts": {},
          }
    from collections import Counter
    ts["event_counts"] = dict(Counter(e["event"] for e in events))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(ts, open(out_path, "w"))
    return ts


def restore(d: str | None = None, data_dir="data"):
    """Rehydrate the live data files from a history snapshot (default: latest).

    The live JSONL files are derived and not committed to git; a fresh clone
    runs this once to get a working dataset without a collection pass."""
    days = snapshots()
    if not days:
        print("no snapshots to restore from")
        return
    d = d or days[-1]
    src = os.path.join(HISTORY_DIR, d)
    for f in SNAPSHOT_FILES:
        gz = os.path.join(src, f + ".gz")
        if not os.path.exists(gz):
            continue
        with gzip.open(gz, "rb") as i, open(os.path.join(data_dir, f), "wb") as o:
            shutil.copyfileobj(i, o)
        print(f"  restored {f} from {d}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        restore(sys.argv[2] if len(sys.argv) > 2 else None)
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "snapshot":
        d = sys.argv[2] if len(sys.argv) > 2 else None
        print("snapshotted to", snapshot(d))
    ts = build_timeseries()
    print(f"snapshots: {[x['date'] for x in ts['days']]}")
    for x in ts["days"]:
        print(f"  {x['date']}: {x['listings']} listings, {x['priced']} priced, "
              f"median ${x['median_comparable_rent']}")
    print("events:", ts["event_counts"])
