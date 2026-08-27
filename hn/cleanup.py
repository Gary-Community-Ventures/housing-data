"""
Post-collection cleanup: normalize property names/cities and fill missing
geocodes from the US Census Bureau geocoder (public domain, no key required).

Runs as a transform over the collected JSONL so parser fixes do not require
re-fetching every site.
"""
from __future__ import annotations
import csv, io, json, os, re, sys
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hn.extract import clean_name, CO_CITIES, MARKETING_JUNK
from hn.policy import USER_AGENT

CENSUS_BATCH = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"


def load(p):
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


STREET_OK = re.compile(
    r"^\d{1,6}[A-Z]?\s+(?:[NSEW]\.?\s+)?[A-Za-z0-9][A-Za-z0-9.'\- ]{2,44}?"
    r"(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Ln|Lane|Way|Ct|Court|"
    r"Pl|Place|Pkwy|Parkway|Cir|Circle|Ter|Terrace|Trl|Trail|Hwy|Highway|Broadway)\.?$",
    re.I)
STREET_JUNK = re.compile(r"sq\.?\s*ft|3d tour|details|floor ?plan|bedroom|bath|"
                         r"\bavailable\b|\$|\d{3,}\s+\d{3,}", re.I)


def fix_street(r: dict) -> dict:
    """Discard street values that are page text rather than addresses.

    An earlier, looser footer regex captured strings like
    "185 Sq. Ft. 3D Tour DETAILS 3D Tour 2234" as a street. Storing a bad
    address is worse than storing none, and it also made geocoding impossible.
    """
    st = (r.get("street") or "").strip()
    if not st:
        return r
    if STREET_JUNK.search(st) or not STREET_OK.match(st):
        r["street_unverified"] = st
        r["street"] = None
    return r


def fix_row(r: dict) -> dict:
    import html as _html
    for k in ("property_name", "plan_name", "street", "city", "operator"):
        if isinstance(r.get(k), str):
            r[k] = _html.unescape(r[k])
    n = clean_name(r.get("property_name"))
    if n:
        r["property_name"] = n
    r = fix_street(r)
    city = (r.get("city") or "").strip()
    if city and city.lower() not in CO_CITIES:
        # try to recover a real city hiding at the end of a mangled string
        toks = city.split()
        for i in range(len(toks)):
            cand = " ".join(toks[i:]).lower()
            if cand in CO_CITIES:
                r["city"] = " ".join(toks[i:])
                break
        else:
            r["city_unverified"] = city
            r["city"] = None
    return r


def geocode_missing(rows: list[dict]) -> dict:
    """Batch-geocode distinct (street, city, zip) with no lat/lon."""
    need = {}
    for r in rows:
        if r.get("lat") or not r.get("street"):
            continue
        key = (r["street"], r.get("city") or "", r.get("postal_code") or "")
        need.setdefault(key, None)
    if not need:
        return {}
    keys = list(need)
    found = {}
    for start in range(0, len(keys), 500):
        chunk = keys[start:start + 500]
        buf = io.StringIO()
        w = csv.writer(buf)
        for i, (st, ci, zp) in enumerate(chunk):
            w.writerow([i, st, ci, "CO", zp])
        try:
            resp = requests.post(
                CENSUS_BATCH,
                files={"addressFile": ("addr.csv", buf.getvalue(), "text/csv")},
                data={"benchmark": "Public_AR_Current"},
                headers={"User-Agent": USER_AGENT}, timeout=300)
            resp.raise_for_status()
        except Exception as e:
            print("  ! census geocoder failed:", e)
            continue
        for line in csv.reader(io.StringIO(resp.text)):
            if len(line) < 6 or line[2] != "Match":
                continue
            try:
                idx = int(line[0])
                lon, lat = line[5].split(",")
                found[chunk[idx]] = (float(lat), float(lon))
            except (ValueError, IndexError):
                continue
    return found


def candidate_names(data_dir="data") -> dict:
    """host -> the name the candidate list gave us, for rows whose on-page title
    is pure marketing copy ("Studio, 1 & 2 Bedroom Apartments for Rent in
    Denver") with no property name in it at all."""
    out = {}
    p = f"{data_dir}/site_results.jsonl"
    if not os.path.exists(p):
        return out
    for line in open(p):
        try:
            r = json.loads(line)
        except Exception:
            continue
        for u in (r.get("floorplan_url"), r.get("marketing_url")):
            if u and r.get("name"):
                try:
                    out[u.split("/")[2]] = r["name"]
                except IndexError:
                    pass
    return out


def main(data_dir="data"):
    names = candidate_names(data_dir)
    for fname in ("listings.jsonl", "properties.jsonl"):
        p = f"{data_dir}/{fname}"
        rows = [fix_row(r) for r in load(p)]
        fixed_names = 0
        for r in rows:
            nm = r.get("property_name") or ""
            if nm and MARKETING_JUNK.search(nm):
                url = r.get("source_url") or r.get("marketing_url") or ""
                try:
                    host = url.split("/")[2]
                except IndexError:
                    continue
                if names.get(host) and not MARKETING_JUNK.search(names[host]):
                    r["property_name"] = names[host]
                    fixed_names += 1
        if fixed_names:
            print(f"  recovered {fixed_names} property names from the candidate list")
        if fname == "listings.jsonl":
            geo = geocode_missing(rows)
            hits = 0
            for r in rows:
                if r.get("lat") or not r.get("street"):
                    continue
                k = (r["street"], r.get("city") or "", r.get("postal_code") or "")
                if k in geo:
                    r["lat"], r["lon"] = geo[k]
                    r["geocode_source"] = "US Census Bureau geocoder"
                    hits += 1
            print(f"  geocoded {hits} rows from {len(geo)} matched addresses")
        with open(p, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"  cleaned {len(rows)} rows in {fname}")


if __name__ == "__main__":
    main()
