#!/usr/bin/env python
"""
Remove all collected data for hosts whose terms prohibit automated access.

Driven by logs/terms_reaudit.json. Rows are deleted, not flagged: we do not
retain data from a site that told us not to collect it.
"""
import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def host_of(u):
    try:
        return (u or "").split("/")[2].lower()
    except IndexError:
        return ""


def main():
    ra = json.load(open("logs/terms_reaudit.json"))
    prohibited = {r["site"].lower() for r in ra if r["new_verdict"] == "PROHIBITS"}
    review = {r["site"].lower() for r in ra
              if r["new_verdict"] == "PROHIBITS_PERSONAL_DATA_ONLY"}
    print(f"hosts prohibiting: {len(prohibited)}")
    print(f"hosts flagged for review (personal-data scope only): {len(review)}")

    # 1. listings
    removed_rows, removed_props, changed_sites = 0, 0, 0
    for path in ("data/listings.jsonl", "data/listings_browser.jsonl"):
        if not os.path.exists(path):
            continue
        rows = [json.loads(l) for l in open(path) if l.strip()]
        keep = [r for r in rows if host_of(r.get("source_url")) not in prohibited]
        removed_rows += len(rows) - len(keep)
        with open(path, "w") as f:
            for r in keep:
                f.write(json.dumps(r) + "\n")

    # 2. property metadata
    if os.path.exists("data/properties.jsonl"):
        rows = [json.loads(l) for l in open("data/properties.jsonl") if l.strip()]
        keep = [r for r in rows if host_of(r.get("marketing_url")) not in prohibited]
        removed_props = len(rows) - len(keep)
        with open("data/properties.jsonl", "w") as f:
            for r in keep:
                f.write(json.dumps(r) + "\n")

    # 3. site results -> reclassify as terms-dropped, keeping the audit trail
    rows = [json.loads(l) for l in open("data/site_results.jsonl") if l.strip()]
    for r in rows:
        h = host_of(r.get("marketing_url"))
        if h in prohibited and r["outcome"] != "F_dropped_terms_prohibit":
            r["outcome"] = "F_dropped_terms_prohibit"
            r["detail"] = ("DROPPED on re-audit: terms prohibit automated access "
                           "(stem-scoped clause missed by the earlier classifier)")
            r["terms_verdict"] = "PROHIBITS"
            r["n_rows"] = r["n_rows_with_rent"] = r["n_rows_with_avail"] = 0
            r["n_units_available"] = None
            r["reaudited_at"] = datetime.now(timezone.utc).isoformat()
            changed_sites += 1
        elif h in review:
            r["terms_verdict"] = "PROHIBITS_PERSONAL_DATA_ONLY"
            r["detail"] = ((r.get("detail") or "") +
                           " | REVIEW: prohibition scoped to users' personal data").strip()
    with open("data/site_results.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    print(f"\nremoved {removed_rows} listing rows, {removed_props} property records")
    print(f"reclassified {changed_sites} sites as terms-dropped")
    for h in sorted(prohibited):
        n = sum(1 for r in rows if host_of(r.get("marketing_url")) == h)
        print(f"  {h:44} {n} site record(s)")


if __name__ == "__main__":
    main()
