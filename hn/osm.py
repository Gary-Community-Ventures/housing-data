"""
OpenStreetMap enumeration via Overpass API.

Data (c) OpenStreetMap contributors, ODbL 1.0. Attribution is carried into
every record and surfaced in the browser UI.
"""
from __future__ import annotations
import json, time, re
import requests
from .policy import USER_AGENT

OVERPASS = "https://overpass-api.de/api/interpreter"
# Denver metro bounding box (Boulder -> Castle Rock, Golden -> Aurora)
DENVER_METRO_BBOX = (39.40, -105.40, 40.15, -104.60)

QUERY = """
[out:json][timeout:180];
(
  nwr["building"="apartments"]["name"]({s},{w},{n},{e});
  nwr["residential"="apartments"]["name"]({s},{w},{n},{e});
  nwr["building"="residential"]["name"]["website"]({s},{w},{n},{e});
);
out center tags;
"""


def fetch_osm(bbox=DENVER_METRO_BBOX, cache="data/osm_denver_metro.json"):
    import os
    if os.path.exists(cache):
        return json.load(open(cache))
    s, w, n, e = bbox
    q = QUERY.format(s=s, w=w, n=n, e=e)
    r = requests.post(OVERPASS, data={"data": q},
                      headers={"User-Agent": USER_AGENT}, timeout=300)
    r.raise_for_status()
    d = r.json()
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(d, open(cache, "w"))
    return d


def to_candidates(d: dict) -> list[dict]:
    out = []
    for el in d.get("elements", []):
        t = el.get("tags", {})
        name = t.get("name")
        if not name:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        site = (t.get("website") or t.get("contact:website")
                or t.get("url") or t.get("contact:url"))
        if site and not site.startswith("http"):
            site = "https://" + site.lstrip("/")
        street = " ".join(x for x in [t.get("addr:housenumber"), t.get("addr:street")] if x) or None
        out.append({
            "name": name,
            "operator": t.get("operator"),
            "city": t.get("addr:city"),
            "state": t.get("addr:state") or "CO",
            "address": street,
            "postal_code": t.get("addr:postcode"),
            "lat": lat, "lon": lon,
            "marketing_url": site,
            "units_osm": t.get("building:units") or t.get("units"),
            "source": "OpenStreetMap",
            "source_license": "ODbL 1.0 (c) OpenStreetMap contributors",
            "osm_id": f"{el.get('type')}/{el.get('id')}",
        })
    return out
