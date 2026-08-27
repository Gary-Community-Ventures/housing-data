#!/usr/bin/env python
"""
One locked entry point for a full daily collection pass.

    ./.venv/bin/python run_daily.py            # full run
    ./.venv/bin/python run_daily.py --dry      # print the plan, touch nothing

Order: collect -> cleanup -> validate -> normalize -> reports -> snapshot ->
timeseries. The order matters (normalize reads validate's flags), so this is
the only supported way to run the pipeline end to end.

Locking is a real fcntl lock on a lockfile, held for the whole run. The
previous pgrep-based coordination deadlocked twice (waiter shells matched each
other's command lines) and once left the data half-normalized; a kernel lock
cannot see its own reflection.
"""
from __future__ import annotations
import argparse, fcntl, json, os, subprocess, sys, time
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, ".venv", "bin", "python")
LOCK = os.path.join(ROOT, "logs", "daily.lock")
LOG = os.path.join(ROOT, "logs", f"daily_{date.today().isoformat()}.log")

STEPS = [
    ("collect",   [PY, "run_collect.py", "--workers", "12", "--delay", "3", "--shuffle"]),
    ("cleanup",   [PY, "-m", "hn.cleanup"]),
    ("validate",  [PY, "-m", "hn.validate"]),
    ("normalize", [PY, "-m", "hn.normalize"]),
    ("report",    [PY, "-m", "hn.report"]),
    ("report_md", [PY, "-m", "hn.report_md"]),
    ("tests",     [PY, "tests/test_reference.py"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--skip-collect", action="store_true",
                    help="re-derive everything from data already on disk")
    args = ap.parse_args()

    if args.dry:
        for name, cmd in STEPS:
            print(f"{name:10} {' '.join(cmd)}")
        print("then: snapshot + timeseries")
        return 0

    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    lock_fh = open(LOCK, "a+")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_fh.seek(0)
        print(f"another daily run holds the lock ({lock_fh.read().strip()!r}); exiting")
        return 2
    lock_fh.truncate(0)
    lock_fh.write(f"pid={os.getpid()} started={datetime.now(timezone.utc).isoformat()}\n")
    lock_fh.flush()

    # The collector APPENDS; a daily run must observe today's state, not
    # accumulate every day's rows in the live files. History keeps the past.
    fresh = ["data/listings.jsonl", "data/site_results.jsonl", "data/properties.jsonl"]

    log = open(LOG, "a")

    def run(name, cmd) -> int:
        t0 = time.time()
        log.write(f"\n===== {name} @ {datetime.now(timezone.utc).isoformat()} =====\n")
        log.flush()
        rc = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=log).returncode
        log.write(f"===== {name} rc={rc} ({time.time()-t0:.0f}s) =====\n")
        log.flush()
        print(f"  {name:10} rc={rc} ({time.time()-t0:.0f}s)")
        return rc

    status = {"date": date.today().isoformat(), "steps": {}}
    try:
        for name, cmd in STEPS:
            if name == "collect":
                if args.skip_collect:
                    status["steps"][name] = "skipped"
                    continue
                for f in fresh:
                    p = os.path.join(ROOT, f)
                    if os.path.exists(p):
                        os.remove(p)
            rc = run(name, cmd)
            status["steps"][name] = rc
            # tests failing must not lose the day's snapshot, but must be loud
            if rc != 0 and name not in ("tests",):
                print(f"step {name} FAILED (rc={rc}) -- stopping before snapshot; "
                      f"see {LOG}")
                status["aborted_at"] = name
                return 1

        sys.path.insert(0, ROOT)
        from hn.history import snapshot, build_timeseries
        out = snapshot()
        ts = build_timeseries()
        status["snapshot"] = out
        status["timeseries_days"] = len(ts["days"])
        status["events"] = ts["event_counts"]
        print(f"  snapshot   {out}")
        print(f"  timeseries {len(ts['days'])} day(s), events: {ts['event_counts']}")
        return 0
    finally:
        status["finished_at"] = datetime.now(timezone.utc).isoformat()
        json.dump(status, open(os.path.join(ROOT, "logs", "daily_status.json"), "w"), indent=1)
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()


if __name__ == "__main__":
    sys.exit(main())
