"""Yield report, platform fingerprint breakdown, and terms audit rollup."""
from __future__ import annotations
import json, os, collections, statistics

OUTCOME_LABELS = {
    "A_rent_and_availability": "Clean rent + availability",
    "B1_rent_only": "Rent only (no availability count)",
    "B2_availability_only": "Availability only (no rent)",
    "B3_structure_only": "Floor plan structure only (no rent, no availability)",
    "C_nothing": "Nothing extracted",
    "D_skipped_vendor_hosted": "Skipped - vendor-hosted marketing site",
    "E_bot_blocked": "Bot-blocked",
    "F_dropped_terms_prohibit": "Dropped - terms prohibit automated access",
    "G_unreachable": "Unreachable / dead URL",
    "H_denylisted": "Denylisted domain (never requested)",
    "I_no_floorplan_page": "No floor-plan page found",
}


def load(path):
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def build(data_dir="data", log_dir="logs", out_dir="reports"):
    os.makedirs(out_dir, exist_ok=True)
    results = load(f"{data_dir}/site_results.jsonl")
    listings = load(f"{data_dir}/listings.jsonl")
    props = load(f"{data_dir}/properties.jsonl")
    terms = load(f"{log_dir}/terms_audit.jsonl")

    # de-dup site results by url (last run wins)
    by_url = {}
    for r in results:
        by_url[r["marketing_url"]] = r
    results = list(by_url.values())

    n = len(results)
    counts = collections.Counter(r["outcome"] for r in results)

    def pct(x):
        return round(100.0 * x / n, 1) if n else 0.0

    yield_report = {
        "sites_attempted": n,
        "buckets": [
            {"code": k, "label": OUTCOME_LABELS.get(k, k), "n": counts.get(k, 0),
             "pct": pct(counts.get(k, 0))}
            for k in sorted(set(list(OUTCOME_LABELS) + list(counts)),
                            key=lambda k: -counts.get(k, 0))
            if counts.get(k, 0) or k in OUTCOME_LABELS
        ],
        "usable_any_data": counts.get("A_rent_and_availability", 0)
                           + counts.get("B1_rent_only", 0)
                           + counts.get("B2_availability_only", 0),
        "listing_rows": len(listings),
        "unit_level_rows": sum(1 for l in listings if l.get("granularity") == "unit"),
        "rows_with_rent": sum(1 for l in listings if l.get("rent") is not None),
        "rows_with_availability": sum(1 for l in listings if l.get("units_available") is not None),
        "rows_with_geo": sum(1 for l in listings if l.get("lat")),
        "distinct_properties_with_data": len({l.get("property_name") for l in listings if l.get("property_name")}),
    }
    yield_report["usable_pct"] = pct(yield_report["usable_any_data"])
    yield_report["structure_only"] = counts.get("B3_structure_only", 0)
    yield_report["rent_behind_denylisted_portal"] = sum(
        1 for r in results if r.get("rent_behind_denylisted_portal"))

    # Yield split by where the candidate came from. This matters: the
    # OpenStreetMap sweep pulls in senior-living, co-ops and non-rental
    # entities, so a single blended number understates the operator-portfolio
    # path and overstates the OSM one.
    by_src = collections.defaultdict(collections.Counter)
    for r in results:
        src = r.get("candidate_source") or "unknown"
        src = "OpenStreetMap" if "OpenStreetMap" in src else (
            "operator portfolios" if "candidates_batch" in src else src)
        by_src[src][r["outcome"]] += 1
    yield_by_source = []
    for src, c in by_src.items():
        tot = sum(c.values())
        usable = c["A_rent_and_availability"] + c["B1_rent_only"] + c["B2_availability_only"]
        yield_by_source.append({
            "source": src, "attempted": tot,
            "clean_rent_and_availability": c["A_rent_and_availability"],
            "usable_any": usable,
            "usable_pct": round(100.0 * usable / tot, 1) if tot else 0.0,
            "structure_only": c["B3_structure_only"],
            "nothing": c["C_nothing"], "blocked": c["E_bot_blocked"],
            "vendor_hosted": c["D_skipped_vendor_hosted"],
            "terms_dropped": c["F_dropped_terms_prohibit"],
            "unreachable": c["G_unreachable"], "denylisted": c["H_denylisted"],
        })
    yield_by_source.sort(key=lambda x: -x["attempted"])

    # yield by candidate source
    src_of = {}
    for path in os.listdir(data_dir):
        pass
    # platform breakdown
    plat = collections.defaultdict(lambda: {"sites": 0, "with_rent": 0, "with_avail": 0,
                                            "rows": 0, "blocked": 0, "nothing": 0,
                                            "structure_only": 0, "portal_gated": 0})
    for r in results:
        p = r.get("platform") or "unknown"
        if r["outcome"] in ("H_denylisted", "G_unreachable"):
            continue
        d = plat[p]
        d["sites"] += 1
        d["rows"] += r.get("n_rows", 0)
        if r.get("rent_behind_denylisted_portal"):
            d["portal_gated"] = d.get("portal_gated", 0) + 1
        if r["outcome"] == "A_rent_and_availability":
            d["with_rent"] += 1
            d["with_avail"] += 1
        elif r["outcome"] == "B1_rent_only":
            d["with_rent"] += 1
        elif r["outcome"] == "B2_availability_only":
            d["with_avail"] += 1
        elif r["outcome"] == "E_bot_blocked":
            d["blocked"] += 1
        elif r["outcome"] == "C_nothing":
            d["nothing"] += 1
        elif r["outcome"] == "B3_structure_only":
            d["structure_only"] += 1
    platform_report = []
    for p, d in sorted(plat.items(), key=lambda kv: -kv[1]["sites"]):
        usable = d["with_rent"] + d["with_avail"] - min(d["with_rent"], d["with_avail"])
        usable = d["with_rent"] or d["with_avail"]
        platform_report.append({
            "platform": p, **d,
            "usable_rate_pct": round(100.0 * (d["with_rent"] or 0) / d["sites"], 1) if d["sites"] else 0.0,
        })

    # extraction layer effectiveness
    layers = collections.Counter(r.get("winning_layer") for r in results if r.get("winning_layer"))

    # terms audit rollup
    tby = {}
    for t in terms:
        tby[t["site"]] = t
    terms_rollup = {
        "sites_checked": len(tby),
        "verdicts": dict(collections.Counter(t["verdict"] for t in tby.values())),
        "prohibiting_sites": [
            {"site": t["site"], "terms_url": t["terms_url"], "snippets": t["matched_snippets"]}
            for t in tby.values() if t["verdict"] == "PROHIBITS"
        ],
    }

    # rent statistics by bedroom count (sanity check on the data)
    by_bed = collections.defaultdict(list)
    for l in listings:
        # Plausible rows only, and per-bed student-housing pricing excluded:
        # a $631 bed in a 5x5 is not a 5-bedroom rent and would corrupt the
        # distribution it is averaged into.
        if l.get("plausible") is False:
            continue
        if "per_bed_pricing" in (l.get("quality_flags") or []):
            continue
        if l.get("rent") and l.get("bedrooms") is not None:
            by_bed[l["bedrooms"]].append(l["rent"])
    rent_stats = []
    for bd in sorted(by_bed):
        v = sorted(by_bed[bd])
        rent_stats.append({
            "bedrooms": bd, "n": len(v),
            "min": v[0], "p25": v[len(v)//4], "median": statistics.median(v),
            "p75": v[3*len(v)//4], "max": v[-1],
            "mean": round(statistics.mean(v), 2),
        })

    flag_counts = collections.Counter(
        f.split("(")[0] for l in listings for f in (l.get("quality_flags") or []))
    by_layer = collections.Counter(
        (l.get("extraction_method") or "?").split(":")[0] for l in listings)
    by_layer_rent = collections.Counter(
        (l.get("extraction_method") or "?").split(":")[0]
        for l in listings if l.get("rent") is not None)
    conf = collections.Counter(l.get("confidence") for l in listings)
    basis = collections.Counter(l.get("rent_basis") for l in listings)
    normalization = {
        "rows": len(listings),
        "confidence": dict(conf),
        "rent_basis": dict(basis),
        "with_comparable_rent": sum(1 for l in listings if l.get("comparable_rent") is not None),
        "term_matrix_published": sum(1 for l in listings if l.get("rent_term_matrix")),
        "mandatory_fees_known": sum(1 for l in listings if l.get("mandatory_fees_monthly")),
        "with_concession": sum(1 for l in listings if l.get("concession_months_free")),
        "income_restricted": sum(1 for l in listings if l.get("income_restricted")),
        "per_bed_normalized": sum(1 for l in listings if l.get("rent_basis") == "per_bed"),
        "cost_completeness": dict(collections.Counter(
            l.get("cost_completeness") for l in listings)),
        "top_cost_gaps": dict(collections.Counter(
            g for l in listings for g in (l.get("cost_gaps") or [])).most_common(6)),
        "top_confidence_blockers": dict(collections.Counter(
            r for l in listings for r in (l.get("confidence_reasons") or [])).most_common(8)),
    }

    data_quality = {
        "rows": len(listings),
        "plausible": sum(1 for l in listings if l.get("plausible") is not False),
        "implausible": sum(1 for l in listings if l.get("plausible") is False),
        "flag_counts": dict(flag_counts),
        "rows_by_layer": dict(by_layer),
        "priced_rows_by_layer": dict(by_layer_rent),
        "high_confidence_rows": sum(
            1 for l in listings
            if not (l.get("extraction_method") or "").startswith("L4")
            and l.get("plausible") is not False),
    }

    # Browser-recovered sites are reported SEPARATELY and never folded into the
    # primary yield number. That number measures what a plain, polite HTTP
    # crawler achieves; mixing in browser output would overstate it.
    browser_rows = load(f"{data_dir}/listings_browser.jsonl")
    br_hosts = {}
    for r in browser_rows:
        try:
            h = (r.get("source_url") or "").split("/")[2]
        except IndexError:
            continue
        d = br_hosts.setdefault(h, {"rows": 0, "priced": 0, "avail": 0})
        d["rows"] += 1
        d["priced"] += 1 if r.get("rent") is not None else 0
        d["avail"] += 1 if r.get("units_available") is not None else 0
    blocked_n = counts.get("E_bot_blocked", 0)
    # Count attempts from the captured pages, not from the rows they produced:
    # a page we captured that yielded nothing is still an attempt, and dropping
    # it would flatter the recovery rate.
    import glob as _glob
    captured_hosts = {os.path.basename(x)[:-4]
                      for x in _glob.glob(f"{data_dir}/browser_text/*.txt")}
    browser_recovery = {
        "bot_blocked_sites": blocked_n,
        "attempted_via_browser": len(captured_hosts) or len(br_hosts),
        "captured_pages": sorted(captured_hosts),
        "captured_but_empty": sorted(h for h in captured_hosts
                                     if not br_hosts.get(h, {}).get("rows")),
        "recovered_with_rows": sum(1 for d in br_hosts.values() if d["rows"]),
        "recovered_with_rent": sum(1 for d in br_hosts.values() if d["priced"]),
        "rows": len(browser_rows),
        "priced_rows": sum(1 for r in browser_rows if r.get("rent") is not None),
        "per_host": br_hosts,
        "note": ("robots.txt permits crawling on every one of these hosts; the 403s "
                 "are CDN bot-management defaults. Reported separately so the "
                 "primary yield figure stays a measure of plain HTTP collection."),
    }

    report = {
        "yield": yield_report,
        "normalization": normalization,
        "browser_recovery": browser_recovery,
        "data_quality": data_quality,
        "yield_by_source": yield_by_source,
        "platforms": platform_report,
        "winning_layers": dict(layers),
        "terms": terms_rollup,
        "rent_stats_by_bedrooms": rent_stats,
        "attribution": [
            "Property enumeration partly from OpenStreetMap - (c) OpenStreetMap contributors, ODbL 1.0",
            "Rent and availability collected from each property's own marketing website.",
        ],
    }
    json.dump(report, open(f"{out_dir}/report.json", "w"), indent=1)
    return report


if __name__ == "__main__":
    r = build()
    y = r["yield"]
    print(f"sites attempted: {y['sites_attempted']}")
    for b in y["buckets"]:
        if b["n"]:
            print(f"  {b['code']:28} {b['n']:5}  {b['pct']:5}%  {b['label']}")
    print(f"\nusable (any data): {y['usable_any_data']} ({y['usable_pct']}%)")
    print(f"listing rows: {y['listing_rows']} | unit-level: {y['unit_level_rows']} | with rent: {y['rows_with_rent']}")
    print("\nwinning layers:", r["winning_layers"])
    print("\ntop platforms:")
    for p in r["platforms"][:12]:
        print(f"  {p['platform']:22} sites={p['sites']:4} rent={p['with_rent']:4} blocked={p['blocked']:4} nothing={p['nothing']:4}")
    nz = r["normalization"]
    print(f"\nnormalization: confidence={nz['confidence']} | comparable rent on "
          f"{nz['with_comparable_rent']} rows")
    print(f"  term matrices: {nz['term_matrix_published']} | fees known: {nz['mandatory_fees_known']} "
          f"| concessions: {nz['with_concession']} | per-bed normalized: {nz['per_bed_normalized']}")
    print(f"  cost completeness: {nz['cost_completeness']}")
    print("  cost gaps:")
    for k, v in nz["top_cost_gaps"].items():
        print(f"    {v:6}  {k}")
    print("  confidence blockers:")
    for k, v in nz["top_confidence_blockers"].items():
        print(f"    {v:6}  {k}")
    dq = r["data_quality"]
    print(f"\ndata quality: {dq['plausible']}/{dq['rows']} plausible | "
          f"high-confidence (non-L4) rows: {dq['high_confidence_rows']}")
    print("  rows by layer:", dq["rows_by_layer"])
    print("  flags:", dq["flag_counts"])
    br = r["browser_recovery"]
    print(f"\nbrowser recovery: {br['recovered_with_rent']}/{br['attempted_via_browser']} "
          f"attempted hosts yielded rent ({br['priced_rows']} priced rows) "
          f"of {br['bot_blocked_sites']} bot-blocked sites")
    print("\nyield by source:")
    for x in r["yield_by_source"]:
        print(f"  {x['source']:22} attempted={x['attempted']:4} clean={x['clean_rent_and_availability']:4} "
              f"usable={x['usable_any']:4} ({x['usable_pct']}%) struct={x['structure_only']:3} "
              f"nothing={x['nothing']:4} blocked={x['blocked']:3} vendor={x['vendor_hosted']:3} dead={x['unreachable']:3}")
    print(f"\nrent behind denylisted portal: {r['yield']['rent_behind_denylisted_portal']}")
    print("\nterms:", r["terms"]["verdicts"])
    print("prohibiting:", [p["site"] for p in r["terms"]["prohibiting_sites"]])
