"""
Parse floor-plan data out of browser-rendered page TEXT.

Used for the small set of hosts that refuse plain HTTP requests via CDN
bot-management (their robots.txt permits crawling). A browser captures the
rendered text verbatim; extraction happens here, deterministically, so no
model is inventing numbers.
"""
from __future__ import annotations
import glob, json, os, re, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hn.extract import Listing, money, beds, baths, sqft_of

# "1 Bed 1 Bath" / "Studio 1 Bath" / "2 Beds 2 Baths"
# Studios are labelled "Studio  1 Bath" with no "Bed" token at all, so the bed
# side has to match either "N Bed(s)" or a bare "Studio".
ANCHOR = re.compile(
    r"(?:(?P<bedn>\d+)\s*bed(?:room)?s?|(?P<studio>studio))"
    r"\s*(?P<bath>\d+(?:\.\d)?)\s*bath(?:room)?s?", re.I)
SQFT = re.compile(r"([\d,]{3,6})\s*sq\.?\s*(?:ft|feet)", re.I)
AVAIL = re.compile(r"(\d+)\s*(?:units?\s*)?available", re.I)
PRICE_FROM = re.compile(r"(?:starting\s+at|from)\s*\$\s*([\d,]+(?:\.\d{2})?)", re.I)
PRICE_BASE = re.compile(r"base\s+rent\s*\$\s*([\d,]+(?:\.\d{2})?)", re.I)
PRICE_ANY = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")
TERM = re.compile(r"(\d{1,2})\s*-?\s*month\s+term", re.I)
# a plan label immediately before the anchor: "A2", "S1", "The Aspen", "B1-R"
PLAN_BEFORE = re.compile(r"([A-Z][A-Za-z0-9][A-Za-z0-9.\-]{0,12})\s*$")
NOISE = re.compile(r"filter|sort|any price|all bedrooms|move-?in date|compare", re.I)


def parse_text(text: str, url: str, name_hint: str | None = None) -> list[Listing]:
    flat = re.sub(r"[ \t]*\n[ \t]*", " \n ", text)
    flat = re.sub(r"[ \t]{2,}", " ", flat)
    one = re.sub(r"\s+", " ", flat)
    rows: list[Listing] = []
    seen = set()
    for m in ANCHOR.finditer(one):
        before = one[max(0, m.start() - 60):m.start()]
        after = one[m.end():m.end() + 420]
        if NOISE.search(before[-40:]) or NOISE.search(after[:60]):
            continue
        bd = 0.0 if m.group("studio") else beds(m.group("bedn"))
        bt = baths(m.group("bath"))

        sq = None
        sm = SQFT.search(after) or SQFT.search(before)
        if sm:
            sq = sqft_of(sm.group(1))

        av = None
        am = AVAIL.search(after)
        if am:
            try:
                av = int(am.group(1))
            except ValueError:
                av = None
        elif re.search(r"inquire|call for details|contact us", after[:160], re.I):
            av = 0

        rent = base = None
        pm = PRICE_FROM.search(after)
        if pm:
            rent = money(pm.group(1))
        bm = PRICE_BASE.search(after)
        if bm:
            base = money(bm.group(1))
        if rent is None:
            cand = [money(x.group(1)) for x in PRICE_ANY.finditer(after[:300])]
            cand = [c for c in cand if c and c >= 500]
            rent = cand[0] if cand else None

        term = None
        tm = TERM.search(after)
        if tm:
            term = int(tm.group(1))

        plan = None
        pb = PLAN_BEFORE.search(before.strip())
        if pb:
            cand = pb.group(1).strip()
            if not re.fullmatch(r"\d+", cand) and cand.lower() not in (
                    "bed", "bath", "studio", "beds", "baths", "bedroom", "available"):
                plan = cand

        if bd is None and sq is None:
            continue
        key = (plan, bd, bt, sq, rent, av)
        if key in seen:
            continue
        seen.add(key)
        rows.append(Listing(
            property_name=name_hint, plan_name=plan, bedrooms=bd, bathrooms=bt,
            sqft=sq, rent=rent, rent_min=rent, base_rent=base,
            rent_includes_fees=bool(base and rent and rent > base),
            units_available=av, lease_term_months=term,
            granularity="floorplan", source_url=url,
            collected_at=datetime.now(timezone.utc).isoformat(),
            extraction_method="L5:browser-rendered-text",
            platform="browser-recovered", confidence="medium",
        ))
    return rows


def main(indir="data/browser_text", targets="data/blocked_targets.json",
         out="data/listings_browser.jsonl"):
    tmap = {}
    if os.path.exists(targets):
        for t in json.load(open(targets)):
            tmap[t["host"]] = t
    total, wrote, per_site = 0, 0, []
    with open(out, "w") as f:
        for path in sorted(glob.glob(f"{indir}/*.txt")):
            host = os.path.basename(path)[:-4]
            raw = open(path).read()
            first, _, body = raw.partition("---PAGETEXT---")
            url = first.strip().splitlines()[0].strip() if first.strip() else host
            if not body.strip():
                body = raw
            t = tmap.get(host, {})
            rows = parse_text(body, url, t.get("name"))
            priced = sum(1 for r in rows if r.rent is not None)
            per_site.append((host, len(rows), priced))
            total += 1
            for r in rows:
                r.operator = t.get("operator")
                r.state = "CO"
                f.write(json.dumps(r.dict()) + "\n")
                wrote += 1
    print(f"parsed {total} browser-captured pages -> {wrote} rows")
    for h, n, p in per_site:
        print(f"  {h:42} rows={n:3} priced={p:3}")
    return per_site


if __name__ == "__main__":
    main()
