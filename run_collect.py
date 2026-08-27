#!/usr/bin/env python
"""
Collection runner.

Concurrency model: candidates are grouped by host and each host-group is handled
by exactly one worker with its own Fetcher. That guarantees the polite per-host
delay still holds no matter how many workers run, because two workers can never
touch the same host.
"""
from __future__ import annotations

import argparse, glob, json, os, random, sys, threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hn.policy import Fetcher, _host, is_denied
from hn.collect import Collector

PRINT_LOCK = threading.Lock()


def load_candidates():
    cands, seen = [], set()
    for path in sorted(glob.glob("data/candidates_*.json")):
        try:
            blob = json.load(open(path))
        except Exception as e:
            print(f"  ! skipping {path}: {e}")
            continue
        rows = blob.get("communities") if isinstance(blob, dict) else blob
        if not isinstance(rows, list):
            continue
        src = os.path.basename(path)
        for r in rows:
            if not isinstance(r, dict):
                continue
            url = (r.get("marketing_url") or "").strip()
            if not url:
                continue
            if not url.startswith("http"):
                url = "https://" + url.lstrip("/")
            # normalize to origin for the homepage entry point
            p = urlparse(url)
            origin = f"{p.scheme}://{p.netloc}{p.path if len(p.path) > 1 else '/'}"
            # Sitemap-derived candidates have no name yet -- it is resolved from
            # the page at collection time -- so fall back to the URL for dedup.
            nm = (r.get("name") or "").strip().lower()
            key = (nm, _host(url)) if nm else ("", origin.rstrip("/").lower())
            if key in seen:
                continue
            seen.add(key)
            r = dict(r)
            r["marketing_url"] = origin
            r["candidate_source"] = r.get("source") or src
            cands.append(r)
    return cands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--out", default="data")
    ap.add_argument("--shuffle", action="store_true")
    ap.add_argument("--only", default="", help="substring filter on candidate source")
    args = ap.parse_args()

    cands = load_candidates()
    if args.only:
        cands = [c for c in cands if args.only in (c.get("candidate_source") or "")]
    # drop denylisted / vendor-hosted up front so they are reported, not fetched
    pre_skipped = []
    keep = []
    for c in cands:
        d, why = is_denied(c["marketing_url"])
        if d:
            pre_skipped.append((c, "H_denylisted", why))
        else:
            keep.append(c)
    if args.shuffle:
        random.Random(7).shuffle(keep)
    if args.limit:
        keep = keep[: args.limit]

    print(f"candidates loaded: {len(cands)}  | denylisted up front: {len(pre_skipped)}  | attempting: {len(keep)}")

    by_host = defaultdict(list)
    for c in keep:
        by_host[_host(c["marketing_url"])].append(c)
    host_groups = list(by_host.values())
    print(f"distinct hosts: {len(host_groups)}")

    os.makedirs(args.out, exist_ok=True)
    # record the pre-skips into the results stream
    from hn.collect import SiteResult
    from datetime import datetime, timezone
    with open(os.path.join(args.out, "site_results.jsonl"), "a") as f:
        for c, outcome, why in pre_skipped:
            sr = SiteResult(name=c.get("name"), operator=c.get("operator"),
                            marketing_url=c["marketing_url"], outcome=outcome,
                            detail=why, collected_at=datetime.now(timezone.utc).isoformat(),
                            candidate_source=c.get("candidate_source"))
            f.write(json.dumps(sr.dict()) + "\n")

    shards = [[] for _ in range(args.workers)]
    for i, g in enumerate(host_groups):
        shards[i % args.workers].append(g)

    done = [0]
    total = sum(len(g) for g in host_groups)

    def worker(idx, groups):
        f = Fetcher(min_delay=args.delay, log_path=f"logs/fetch_log.jsonl")
        col = Collector(f, out_dir=args.out)
        for g in groups:
            for cand in g:
                try:
                    r = col.collect(cand)
                    tag = r.outcome
                except Exception as e:
                    tag = f"EXC {type(e).__name__}: {e}"[:120]
                with PRINT_LOCK:
                    done[0] += 1
                    print(f"[{done[0]}/{total}] {cand.get('name') or '?':38.38} "
                          f"{_host(cand['marketing_url']):32.32} {tag}", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(lambda t: worker(*t), enumerate(shards)))

    print("done.")


if __name__ == "__main__":
    main()
