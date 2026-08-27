#!/usr/bin/env python
"""
Internal data browser for the housing-navigator collection.

Read-only, localhost. Surfaces everything we hold: unit-level listings, the
properties behind them, the map, and -- deliberately -- the failures, the terms
audit, and the platform breakdown, so the yield story is visible next to the
data rather than in a separate document.
"""
from __future__ import annotations
import json, os, sys, collections, statistics
from flask import Flask, jsonify, request, send_from_directory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DATA, LOGS, REPORTS = f"{ROOT}/data", f"{ROOT}/logs", f"{ROOT}/reports"

app = Flask(__name__, static_folder=f"{ROOT}/web/static", static_url_path="/static")

CACHE = {}


def load_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def refresh():
    listings = load_jsonl(f"{DATA}/listings.jsonl")
    # L5 rows come from browser-rendered text on hosts that refuse plain HTTP.
    # They carry extraction_method "L5:browser-rendered-text" so they stay
    # distinguishable everywhere in the UI.
    listings += load_jsonl(f"{DATA}/listings_browser.jsonl")
    results = load_jsonl(f"{DATA}/site_results.jsonl")
    props = load_jsonl(f"{DATA}/properties.jsonl")
    terms = load_jsonl(f"{LOGS}/terms_audit.jsonl")

    # last-write-wins de-dup
    res_by_url = {r["marketing_url"]: r for r in results}
    prop_by_url = {p["marketing_url"]: p for p in props}

    # Joining property metadata to listing rows is fiddly: listings carry the
    # floor-plan page URL (often with a query string) while properties.jsonl is
    # keyed on the entry URL. An exact-URL join dropped every amenity and phone
    # number; a host-only join was worse -- it gave 48 separate RedPeak
    # properties the same shared operator metadata. So: match on host+path,
    # trimming path segments, and fall back to host only when that host has
    # exactly one property.
    def _norm(u):
        try:
            rest = (u or "").split("://", 1)[-1]
            hostpath = rest.split("?")[0].split("#")[0]
            return hostpath.rstrip("/").lower()
        except Exception:
            return ""

    def _host_of(u):
        n = _norm(u)
        return n.split("/")[0] if n else ""

    prop_by_norm, host_counts = {}, collections.Counter()
    for p_ in props:
        n = _norm(p_.get("marketing_url"))
        if n:
            prop_by_norm[n] = p_
            host_counts[n.split("/")[0]] += 1
    prop_by_host_unique = {}
    for p_ in props:
        h = _host_of(p_.get("marketing_url"))
        if h and host_counts[h] == 1:
            prop_by_host_unique[h] = p_

    def meta_for(url):
        n = _norm(url)
        if not n:
            return {}
        if n in prop_by_norm:
            return prop_by_norm[n]
        parts = n.split("/")
        for cut in range(len(parts) - 1, 0, -1):
            cand = "/".join(parts[:cut])
            if cand in prop_by_norm:
                return prop_by_norm[cand]
        return prop_by_host_unique.get(parts[0], {})

    terms_by_site = {t["site"]: t for t in terms}

    # de-dup listing rows (a re-run appends)
    seen, uniq = set(), []
    for l in listings:
        k = (l.get("source_url"), l.get("plan_name"), l.get("unit_number"),
             l.get("rent"), l.get("sqft"), l.get("bedrooms"))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(l)
    listings = uniq

    # property-level aggregation from the listing rows
    agg = {}
    for l in listings:
        key = l.get("property_name") or l.get("source_url")
        a = agg.setdefault(key, {
            "property_name": l.get("property_name"), "operator": l.get("operator"),
            "street": l.get("street"), "city": l.get("city"), "state": l.get("state"),
            "postal_code": l.get("postal_code"), "lat": l.get("lat"), "lon": l.get("lon"),
            "source_url": l.get("source_url"), "platform": l.get("platform"),
            "n_rows": 0, "n_units": 0, "rents": [], "beds": set(), "sqfts": [],
            "available_now": 0, "extraction_method": l.get("extraction_method"),
            "n_flagged": 0, "flags": set(),
        })
        a["n_rows"] += 1
        if l.get("plausible") is False:
            a["n_flagged"] += 1
        for fl in (l.get("quality_flags") or []):
            a["flags"].add(fl.split("(")[0])
        if l.get("granularity") == "unit":
            a["n_units"] += 1
        if l.get("comparable_rent"):
            a["rents"].append(l["comparable_rent"])
        elif l.get("rent"):
            a["rents"].append(l["rent"])
        if l.get("bedrooms") is not None:
            a["beds"].add(l["bedrooms"])
        if l.get("sqft"):
            a["sqfts"].append(l["sqft"])
        if (l.get("available_display") or "").lower().startswith("available now"):
            a["available_now"] += 1
    properties = []
    for k, a in agg.items():
        rents = a.pop("rents")
        sqfts = a.pop("sqfts")
        beds = sorted(a.pop("beds"))
        a["flags"] = sorted(a["flags"])
        meta = meta_for(a["source_url"])
        t = terms_by_site.get(_host_of(a["source_url"]), {})
        properties.append({
            **a,
            "rent_min": min(rents) if rents else None,
            "rent_max": max(rents) if rents else None,
            "rent_median": round(statistics.median(rents), 0) if rents else None,
            "beds_offered": beds,
            "sqft_min": min(sqfts) if sqfts else None,
            "sqft_max": max(sqfts) if sqfts else None,
            "walk_score": meta.get("walk_score"),
            "telephone": meta.get("telephone"),
            "amenities": meta.get("amenities") or [],
            "pet_policy": meta.get("pet_policy"),
            "description": meta.get("description"),
            "office_hours": meta.get("office_hours"),
            "terms_verdict": t.get("verdict"),
            "terms_url": t.get("terms_url"),
        })
    properties.sort(key=lambda p: (p["property_name"] or "").lower())

    CACHE.update({
        "listings": listings,
        "results": list(res_by_url.values()),
        "properties": properties,
        "terms": list(terms_by_site.values()),
        "report": json.load(open(f"{REPORTS}/report.json")) if os.path.exists(f"{REPORTS}/report.json") else {},
    })
    return CACHE


@app.route("/")
def index():
    return send_from_directory(f"{ROOT}/web/static", "index.html")


@app.route("/api/reload")
def api_reload():
    refresh()
    return jsonify({"ok": True, "listings": len(CACHE["listings"]),
                    "properties": len(CACHE["properties"]),
                    "sites": len(CACHE["results"])})


@app.route("/api/properties")
def api_properties():
    return jsonify(CACHE.get("properties", []))


@app.route("/api/listings")
def api_listings():
    rows = CACHE.get("listings", [])
    q = request.args
    def keep(l):
        if q.get("beds") not in (None, "", "any"):
            try:
                if l.get("bedrooms") is None or float(l["bedrooms"]) != float(q["beds"]):
                    return False
            except ValueError:
                pass
        if q.get("max_rent"):
            if l.get("rent") is None or l["rent"] > float(q["max_rent"]):
                return False
        if q.get("min_rent"):
            if l.get("rent") is None or l["rent"] < float(q["min_rent"]):
                return False
        if q.get("city"):
            if (l.get("city") or "").lower() != q["city"].lower():
                return False
        if q.get("operator"):
            if (l.get("operator") or "").lower() != q["operator"].lower():
                return False
        if q.get("has_rent") == "1" and l.get("rent") is None:
            return False
        if q.get("plausible_only") == "1" and l.get("plausible") is False:
            return False
        if q.get("high_conf") == "1" and l.get("confidence") != "high":
            return False
        if q.get("market_rate") == "1" and l.get("market_rate") is False:
            return False
        if q.get("has_comparable") == "1" and l.get("comparable_rent") is None:
            return False
        if q.get("cost_complete") == "1" and l.get("cost_completeness") != "complete":
            return False
        if q.get("search"):
            s = q["search"].lower()
            hay = " ".join(str(l.get(k) or "") for k in
                           ("property_name", "plan_name", "city", "operator", "street"))
            if s not in hay.lower():
                return False
        return True
    out = [l for l in rows if keep(l)]
    return jsonify({"n": len(out), "rows": out[: int(q.get("limit", 5000))]})


@app.route("/api/site_results")
def api_site_results():
    return jsonify(CACHE.get("results", []))


@app.route("/api/terms")
def api_terms():
    return jsonify(CACHE.get("terms", []))


@app.route("/api/report")
def api_report():
    return jsonify(CACHE.get("report", {}))


@app.route("/api/timeseries")
def api_timeseries():
    p = f"{REPORTS}/timeseries.json"
    return jsonify(json.load(open(p)) if os.path.exists(p) else {"days": [], "events": []})


@app.route("/api/facets")
def api_facets():
    rows = CACHE.get("listings", [])
    cities = collections.Counter(l.get("city") for l in rows if l.get("city"))
    ops = collections.Counter(l.get("operator") for l in rows if l.get("operator"))
    beds = collections.Counter(l.get("bedrooms") for l in rows if l.get("bedrooms") is not None)
    return jsonify({
        "cities": sorted(cities.items(), key=lambda kv: -kv[1]),
        "operators": sorted(ops.items(), key=lambda kv: -kv[1]),
        "bedrooms": sorted(beds.items()),
        "rent_range": [min((l["rent"] for l in rows if l.get("rent")), default=0),
                       max((l["rent"] for l in rows if l.get("rent")), default=0)],
    })


if __name__ == "__main__":
    refresh()
    print(f"loaded {len(CACHE['listings'])} listings / {len(CACHE['properties'])} properties "
          f"/ {len(CACHE['results'])} site results")
    app.run(host="127.0.0.1", port=5050, debug=False)
