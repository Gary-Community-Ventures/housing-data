#!/usr/bin/env python
"""
Re-collect a subset of sites and replace their rows in place.

Used after an extraction fix so the corrected parser is applied without
re-fetching all 647 hosts.
"""
import json, os, sys, threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hn.policy import Fetcher, _host
from hn.collect import Collector

LOCK = threading.Lock()


def main(match_layer="L4", workers=12, delay=3.0, outcomes=None):
    results = [json.loads(l) for l in open("data/site_results.jsonl") if l.strip()]
    by_url = {}
    for r in results:
        by_url[r["marketing_url"]] = r
    if outcomes:
        targets = [r for r in by_url.values() if r["outcome"] in outcomes]
    else:
        targets = [r for r in by_url.values()
                   if match_layer in (r.get("winning_layer") or "")]
    tgt_urls = {r["marketing_url"] for r in targets}
    src_urls = {r.get("floorplan_url") for r in targets if r.get("floorplan_url")}
    what = f"outcomes {sorted(outcomes)}" if outcomes else f"winning layer ~ {match_layer!r}"
    print(f"re-running {len(targets)} sites ({what})")

    # strip their old rows
    keep_res = [r for r in by_url.values() if r["marketing_url"] not in tgt_urls]
    with open("data/site_results.jsonl", "w") as f:
        for r in keep_res:
            f.write(json.dumps(r) + "\n")
    for path, key in (("data/listings.jsonl", "source_url"), ("data/properties.jsonl", "marketing_url")):
        if not os.path.exists(path):
            continue
        rows = [json.loads(l) for l in open(path) if l.strip()]
        before = len(rows)
        drop = src_urls if key == "source_url" else tgt_urls
        rows = [r for r in rows if r.get(key) not in drop]
        with open(path, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"  {path}: dropped {before - len(rows)} stale rows")

    cands = [{"name": r["name"], "operator": r["operator"],
              "marketing_url": r["marketing_url"],
              "candidate_source": r.get("candidate_source")} for r in targets]
    by_hostgrp = defaultdict(list)
    for c in cands:
        by_hostgrp[_host(c["marketing_url"])].append(c)
    groups = list(by_hostgrp.values())
    shards = [[] for _ in range(workers)]
    for i, g in enumerate(groups):
        shards[i % workers].append(g)
    done = [0]

    def worker(groups):
        col = Collector(Fetcher(min_delay=delay), out_dir="data")
        for g in groups:
            for c in g:
                try:
                    r = col.collect(c)
                    tag = r.outcome
                except Exception as e:
                    tag = f"EXC {type(e).__name__}"
                with LOCK:
                    done[0] += 1
                    print(f"[{done[0]}/{len(cands)}] {str(c['name'])[:34]:36} {tag}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(worker, shards))
    print("done")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcomes", default="", help="comma-separated outcome codes")
    ap.add_argument("--layer", default="L4")
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    outs = set(x.strip() for x in a.outcomes.split(",") if x.strip())
    main(match_layer=a.layer, workers=a.workers, outcomes=outs or None)
