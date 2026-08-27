#!/usr/bin/env python
"""
Build candidates from operator sites, via their sitemaps.

Covers the operators that keep every community on their own domain -- the group
that URL-per-property enumeration previously missed entirely.
"""
import json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hn.policy import Fetcher, _host
from hn.operator_enum import property_urls

LOCK = threading.Lock()


def origin_of(u):
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}/"


def main(workers=8):
    seeds = []
    # operators found uncovered in the coverage pass
    if os.path.exists("data/operators_uncovered.json"):
        d = json.load(open("data/operators_uncovered.json"))
        for grp in ("market_rate", "affordable"):
            for r in d.get(grp) or []:
                u = r.get("portfolio_url")
                if u:
                    seeds.append({"operator": r["operator"], "group": r["group"],
                                  "portfolio_url": u, "origin": origin_of(u)})
    # operators we already had, whose properties live on the operator domain
    for op, u in [
        ("Griffis Residential", "https://griffisresidential.com/communities/colorado/"),
        ("Cortland", "https://cortland.com/apartments/"),
        ("RedPeak Properties", "https://redpeak.com/properties/"),
        ("Simpson Property Group", "https://www.simpsonpropertygroup.com/apartment-search"),
        ("Camden", "https://www.camdenliving.com/apartments/denver-metro"),
        ("AIR Communities", "https://www.aircommunities.com/en/community.html"),
    ]:
        seeds.append({"operator": op, "group": "market-rate",
                      "portfolio_url": u, "origin": origin_of(u)})

    # de-dup by origin
    by_origin = {}
    for s in seeds:
        by_origin.setdefault(s["origin"], s)
    seeds = list(by_origin.values())
    print(f"enumerating {len(seeds)} operator sites\n")

    out, done = [], [0]

    def work(chunk):
        f = Fetcher(min_delay=2.5, log_path="logs/operator_enum_fetch.jsonl")
        for s in chunk:
            try:
                urls = property_urls(f, s["origin"], s["portfolio_url"])
            except Exception as e:
                urls = []
                s["error"] = f"{type(e).__name__}"
            with LOCK:
                done[0] += 1
                print(f"[{done[0]}/{len(seeds)}] {s['operator'][:34]:36} "
                      f"{len(urls):4} property URLs   {_host(s['origin'])}", flush=True)
                for u in urls:
                    out.append({
                        "name": None,                # resolved during collection
                        "operator": s["operator"],
                        "group": s["group"],
                        "city": None, "state": "CO", "address": None,
                        "marketing_url": u,
                        "own_domain": False,
                        "vendor_hosted": False, "vendor": None,
                        "source": "operator-sitemap",
                        "source_page": s["portfolio_url"],
                    })

    shards = [seeds[i::workers] for i in range(workers)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, shards))

    # drop URLs we already have
    existing = set()
    if os.path.exists("data/site_results.jsonl"):
        for line in open("data/site_results.jsonl"):
            try:
                existing.add(json.loads(line)["marketing_url"].rstrip("/").lower())
            except Exception:
                pass
    fresh = [c for c in out if c["marketing_url"].rstrip("/").lower() not in existing]

    json.dump({"communities": fresh,
               "notes": "Property pages enumerated from operator sitemaps. "
                        "Names/addresses resolved at collection time; "
                        "non-Colorado rows are discarded then."},
              open("data/candidates_operator_sitemaps.json", "w"), indent=1)
    print(f"\n{len(out)} property URLs found, {len(fresh)} not already attempted")
    print("wrote data/candidates_operator_sitemaps.json")


if __name__ == "__main__":
    main()
