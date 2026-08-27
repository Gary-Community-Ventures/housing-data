"""
Extraction engine.

Four layers, tried in order, best result wins:

  L1  platform-specific JSON island  (Jonah Digital `jd-fp-data-script-app`)
      -> UNIT-level records: apartment number, exact rent, available date.
  L2  generic framework/JSON island scan (__NEXT_DATA__, __NUXT__, application/json)
      -> unit- or floorplan-level, whatever the blob holds.
  L3  schema.org JSON-LD, walked RECURSIVELY (the @graph mistake)
      -> floorplan-level structure + availability counts, rarely rent.
  L4  HTML price regex joined to floor-plan names in the rendered markup.
      -> floorplan-level rent, lowest confidence.

RULE 6: we never store image URLs or download images. Extractors strip them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# platform fingerprints
# ---------------------------------------------------------------------------
# Site-builder / CMS fingerprints. These identify WHO BUILT the marketing page.
# They are NOT vendor-hosting determinations -- see vendor_hosted() below.
SITE_BUILDERS = [
    ("Jonah Digital",    ["jd-fp-data-script-app", "schema.jonahdigital.com", "jonahdigital.com"]),
    ("G5",               ["g5search", "g5-cls-", "g5-element", "cdn.g5search.com"]),
    ("Funnel / Nestio",  ["nestiolistings", "funnelleasing", "nestio.com"]),
    ("Knock",            ["knockrentals", "knock-cta", "knockcrm"]),
    ("Respage",          ["respage.com", "respage-"]),
    ("Rentable",         ["rentable.co"]),
    ("Roost",            ["roostcms"]),
    ("ActiveBuilding CMS", ["activebuilding.com"]),
    ("Next.js",          ["__next_data__", "/_next/static"]),
    ("Nuxt",             ["__nuxt__", "/_nuxt/"]),
    ("WordPress",        ["wp-content", "wp-json", "wp-includes"]),
    ("Webflow",          ["webflow.com", "w-webflow", "assets.website-files.com"]),
    ("Squarespace",      ["static1.squarespace", "squarespace.com"]),
    ("Wix",              ["wixstatic", "parastorage.com"]),
    ("Duda",             ["dudamobile", "multiscreensite"]),
    ("Drupal",           ["/sites/default/files", "drupal-settings-json"]),
]

# Widgets that indicate a third-party availability/pricing module is present.
DATA_WIDGETS = [
    ("Engrain SightMap", ["sightmap.com", "engrain"]),
    ("Matterport",       ["matterport.com"]),
    ("RentDynamics",     ["rentdynamics"]),
    ("Updater",          ["updater.com"]),
]

# RULE 3 / RULE 1 -- STRONG evidence that the PAGE ITSELF is a vendor product.
# A mere outbound "Apply Now" link to a leasing engine is NOT this: those hosts
# are denylisted and never followed, but they do not make the marketing site
# vendor-hosted. Conflating the two would discard good properties for no
# compliance benefit, so the test is host identity or a self-identifying
# footer / copyright / vendor-terms link.
VENDOR_BODY_STRONG = [
    ("Entrata",  ["powered by entrata", "entrata, inc", "entrata.com/terms",
                  "prospectportal.com/terms", "\u00a9 entrata"]),
    ("Yardi",    ["powered by yardi", "yardi systems, inc", "rentcafe.com/terms",
                  "yardi.com/terms", "yardi systems inc"]),
    ("RealPage", ["powered by realpage", "realpage, inc", "realpage.com/legal",
                  "realpage.com/terms"]),
    ("AppFolio", ["powered by appfolio", "appfolio, inc"]),
    ("ResMan",   ["powered by resman", "resman, llc"]),
]

# Leasing engines referenced from the page. Informational only: we log that they
# exist (it tells us where the authoritative pricing lives) and never fetch them.
LEASING_ENGINE_HOSTS = [
    "onlineleasing.realpage.com", "securecafe.com", "rentcafe.com",
    "selftournow.com", "prospectportal.com", "entrata.com", "myresman.com",
    "meetelise.com", "activebuilding.com", "appfolio.com",
]


def vendor_hosted(html: str) -> str | None:
    """Strong-evidence test that this page is a vendor-hosted product."""
    low = html.lower()
    for vendor, markers in VENDOR_BODY_STRONG:
        hit = next((m for m in markers if m in low), None)
        if hit:
            return f"{vendor} (self-identifying marker: {hit!r})"
    return None


def fingerprint(html: str) -> dict:
    low = html.lower()
    builders = [b for b, ms in SITE_BUILDERS if any(m in low for m in ms)]
    widgets = [w for w, ms in DATA_WIDGETS if any(m in low for m in ms)]
    engines = sorted({h for h in LEASING_ENGINE_HOSTS if h in low})
    return {
        "primary": builders[0] if builders else "unknown",
        "builders": builders,
        "widgets": widgets,
        "leasing_engines_referenced": engines,
        "vendor_hosted": vendor_hosted(html),
    }


# ---------------------------------------------------------------------------
# normalized output record
# ---------------------------------------------------------------------------
@dataclass
class Listing:
    property_name: str | None = None
    operator: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    lat: float | None = None
    lon: float | None = None

    plan_name: str | None = None
    plan_type: str | None = None        # Studio / 1 Bedroom / ...
    bedrooms: float | None = None
    bathrooms: float | None = None
    sqft: int | None = None

    rent: float | None = None           # best single asking rent, as displayed
    rent_min: float | None = None
    rent_max: float | None = None
    base_rent: float | None = None      # rent excluding mandatory fees, when disclosed
    rent_includes_fees: bool | None = None
    units_available: int | None = None

    unit_number: str | None = None
    available_date: str | None = None
    available_display: str | None = None
    lease_term_months: int | None = None
    rent_term_matrix: list = field(default_factory=list)
    fee_items: list = field(default_factory=list)
    property_specials: str | None = None
    building: str | None = None
    specials: str | None = None
    unit_amenities: list = field(default_factory=list)

    granularity: str = "floorplan"      # unit | floorplan
    source_url: str = ""
    collected_at: str = ""
    extraction_method: str = ""
    platform: str = ""
    confidence: str = "medium"

    def dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
_MONEY = re.compile(r"\$\s?([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{2})?|[0-9]{3,5}(?:\.[0-9]{2})?)")


def money(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if 200 <= f <= 25000 else None
    s = str(v)
    m = _MONEY.search(s)
    if not m:
        s2 = re.sub(r"[^0-9.]", "", s)
        try:
            f = float(s2)
        except ValueError:
            return None
        return f if 200 <= f <= 25000 else None
    f = float(m.group(1).replace(",", ""))
    return f if 200 <= f <= 25000 else None


def beds(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    if s in ("studio", "efficiency", "st", "0 bed", "studios"):
        return 0.0
    m = re.search(r"(\d+(?:\.\d)?)", s)
    return float(m.group(1)) if m else None


def baths(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"(\d+(?:\.\d)?)", str(v))
    return float(m.group(1)) if m else None


def sqft_of(v) -> int | None:
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("value") or v.get("minValue") or v.get("maxValue")
    if isinstance(v, (int, float)):
        return int(v) if 100 <= v <= 12000 else None
    m = re.search(r"(\d[\d,]{1,6})", str(v))
    if not m:
        return None
    n = int(m.group(1).replace(",", ""))
    return n if 100 <= n <= 12000 else None


def _norm_key(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def walk_json(obj, pred, out=None, depth=0):
    """Recursive walk collecting dicts matching pred. Handles @graph and any nesting."""
    if out is None:
        out = []
    if depth > 14:
        return out
    if isinstance(obj, dict):
        if pred(obj):
            out.append(obj)
        for v in obj.values():
            walk_json(v, pred, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            walk_json(v, pred, out, depth + 1)
    return out


def json_islands(html: str):
    """Yield (label, parsed_json) for every JSON blob embedded in the page."""
    soup = BeautifulSoup(html, "lxml")
    for sc in soup.find_all("script"):
        typ = (sc.get("type") or "").lower()
        sid = sc.get("id") or ""
        raw = sc.string or sc.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        if typ in ("application/json", "application/ld+json") or sid:
            if not (raw.startswith("{") or raw.startswith("[")):
                continue
            try:
                yield (f"script#{sid or typ}", json.loads(raw))
            except Exception:
                continue
    # Arbitrary JS variable assignments holding JSON.
    #
    # This is where most of the "low confidence HTML card" sites actually keep
    # their data: `const spacesUnitJSON = [{...}]` (Griffis, unit-level),
    # `var preload = {"floorplans":{...}}` (Cortland). Scanning only
    # <script type="application/json"> and the known framework globals missed
    # all of it and forced a fallback to guessing at rendered markup.
    for m in re.finditer(r'(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?=[\{\[])', html):
        name = m.group(1)
        blob = _balanced(html, m.end())
        if not blob or len(blob) < 120:
            continue
        try:
            yield (f"js:{name}", json.loads(blob))
        except Exception:
            continue

    # framework globals
    for pat, label in [
        (r"window\.__NEXT_DATA__\s*=\s*", "__NEXT_DATA__"),
        (r"window\.__NUXT__\s*=\s*", "__NUXT__"),
        (r"window\.__INITIAL_STATE__\s*=\s*", "__INITIAL_STATE__"),
        (r"window\.__APOLLO_STATE__\s*=\s*", "__APOLLO_STATE__"),
        (r"window\.__PRELOADED_STATE__\s*=\s*", "__PRELOADED_STATE__"),
    ]:
        for m in re.finditer(pat, html):
            blob = _balanced(html, m.end())
            if blob:
                try:
                    yield (label, json.loads(blob))
                except Exception:
                    continue


def _balanced(s: str, start: int) -> str | None:
    """Extract a balanced {...} or [...] starting at/after start."""
    while start < len(s) and s[start] not in "{[":
        if s[start] in ";\n" or start > len(s):
            return None
        start += 1
    if start >= len(s):
        return None
    open_c = s[start]
    close_c = "}" if open_c == "{" else "]"
    depth, i, in_str, esc = 0, start, False, False
    while i < len(s) and i - start < 8_000_000:
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == open_c:
                depth += 1
            elif c == close_c:
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
        i += 1
    return None


def ld_json_blocks(html: str):
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.S | re.I):
        raw = m.group(1).strip()
        try:
            yield json.loads(raw)
        except Exception:
            # some sites emit multiple concatenated objects
            for chunk in re.findall(r"\{.*?\}(?=\s*(?:\{|$))", raw, re.S):
                try:
                    yield json.loads(chunk)
                except Exception:
                    pass



# Front Range municipalities, used to validate scraped city strings.
CO_CITIES = {
    "denver", "aurora", "lakewood", "thornton", "arvada", "westminster",
    "centennial", "boulder", "broomfield", "longmont", "loveland", "greeley",
    "littleton", "northglenn", "commerce city", "parker", "castle rock",
    "brighton", "wheat ridge", "englewood", "golden", "louisville",
    "lafayette", "erie", "superior", "lone tree", "highlands ranch",
    "greenwood village", "glendale", "sheridan", "edgewater", "federal heights",
    "fort collins", "colorado springs", "castle pines", "cherry hills village",
    "columbine valley", "dacono", "firestone", "frederick", "lochbuie",
    "aurora city", "morrison", "bow mar", "foxfield", "timnath", "windsor",
    "berthoud", "mead", "johnstown", "evans", "milliken", "platteville",
    "thornton city", "eagle", "gypsum", "monument", "fountain", "pueblo",
}

# SEO copy that shows a title is marketing text, not the property's name.
MARKETING_JUNK = re.compile(
    r"\b(?:apartments?\s+(?:for\s+rent|in)\b|\d\s*[,&]|bedroom|studio|"
    r"for\s+rent|floor\s*plans?|availability|pricing|luxury\s+apartments|"
    r"official\s+site|welcome\s+to)\b", re.I)


def clean_name(raw: str | None) -> str | None:
    """Trim SEO decoration off a page title to recover the property name."""
    if not raw:
        return None
    import html as _html
    s = re.sub(r"\s+", " ", _html.unescape(str(raw))).strip()
    parts = [p.strip() for p in re.split(r"\s*[|\u2013\u2014]\s*|\s+-\s+", s) if p.strip()]
    if parts:
        # Take the FIRST segment that is neither SEO copy nor a bare location.
        # Preferring the last segment instead turned "Parc Mosaic Apartments -
        # Boulder, CO" into "Boulder, CO".
        def bad(p):
            if MARKETING_JUNK.search(p):
                return True
            loc = re.sub(r",?\s*(?:CO|Colorado)\.?$", "", p, flags=re.I).strip()
            return loc.lower() in CO_CITIES or bool(re.fullmatch(r"[A-Za-z .'\-]+,\s*[A-Z]{2}", p))
        clean = [p for p in parts if not bad(p)]
        s = (clean[0] if clean else parts[0])
    return s[:200] or None


# ===========================================================================
# property-level metadata
# ===========================================================================
def property_meta(html: str, url: str) -> dict:
    """Name / address / geo, preferring schema.org, falling back to meta tags."""
    meta = {"property_name": None, "street": None, "city": None, "state": None,
            "postal_code": None, "lat": None, "lon": None, "telephone": None,
            "amenities": [], "walk_score": None, "pet_policy": None,
            "description": None, "office_hours": None, "name_source": None,
            "property_specials": None}

    def is_place(n):
        t = str(n.get("@type", ""))
        return any(k in t for k in ("ApartmentComplex", "Apartment", "Residence",
                                    "LocalBusiness", "RealEstateListing", "Place",
                                    "Organization", "LodgingBusiness"))

    nodes = []
    for blk in ld_json_blocks(html):
        nodes += walk_json(blk, is_place)
    # prefer the node with the most useful fields
    nodes.sort(key=lambda n: -sum(1 for k in ("name", "address", "geo", "telephone") if n.get(k)))
    for n in nodes:
        if not meta["property_name"] and isinstance(n.get("name"), str):
            meta["property_name"] = n["name"].strip()[:200]
            meta["name_source"] = "schema.org"
        addr = n.get("address")
        if isinstance(addr, dict) and not meta["street"]:
            meta["street"] = (addr.get("streetAddress") or None)
            meta["city"] = (addr.get("addressLocality") or None)
            st = addr.get("addressRegion")
            meta["state"] = st if isinstance(st, str) else None
            meta["postal_code"] = str(addr.get("postalCode")) if addr.get("postalCode") else None
        geo = n.get("geo")
        if isinstance(geo, dict) and meta["lat"] is None:
            try:
                meta["lat"] = float(geo.get("latitude"))
                meta["lon"] = float(geo.get("longitude"))
            except (TypeError, ValueError):
                pass
        if not meta["telephone"] and isinstance(n.get("telephone"), str):
            meta["telephone"] = n["telephone"]
        if not meta["description"] and isinstance(n.get("description"), str):
            meta["description"] = n["description"][:800]
        if not meta["amenities"]:
            am = n.get("amenityFeature")
            if isinstance(am, list):
                meta["amenities"] = [
                    {"name": a.get("name"), "category": a.get("jonah:category")}
                    for a in am if isinstance(a, dict) and a.get("name")
                ][:80]
        for prop in (n.get("additionalProperty") or []):
            if isinstance(prop, dict) and str(prop.get("name", "")).lower().startswith("walk"):
                meta["walk_score"] = prop.get("value")
        ann = n.get("jonah:announcements")
        if isinstance(ann, list) and not meta["property_specials"]:
            txts = [str(a.get("jonah:name") or a.get("name") or "")
                    for a in ann if isinstance(a, dict)]
            txts = [t for t in txts if t]
            if txts:
                meta["property_specials"] = "; ".join(txts)[:400]
        if n.get("jonah:petPolicy") and not meta["pet_policy"]:
            meta["pet_policy"] = str(n["jonah:petPolicy"])[:300]
        oh = n.get("openingHoursSpecification")
        if isinstance(oh, list) and not meta["office_hours"]:
            meta["office_hours"] = [
                {"days": o.get("dayOfWeek"), "opens": o.get("opens"), "closes": o.get("closes")}
                for o in oh if isinstance(o, dict)
            ][:10]

    soup = BeautifulSoup(html, "lxml")
    if not meta["property_name"]:
        og = soup.find("meta", property="og:site_name") or soup.find("meta", property="og:title")
        if og and og.get("content"):
            meta["property_name"] = clean_name(og["content"])
            # og:title is frequently SEO copy ("1, 2 & 3-Bedroom Apartments |
            # Foo"), so it only counts as a strong name when it is not.
            meta["name_source"] = "og-meta" if not MARKETING_JUNK.search(og["content"]) else "og-meta-weak"
        elif soup.title and soup.title.string:
            meta["property_name"] = clean_name(soup.title.string)
            meta["name_source"] = "html-title"

    if not meta["street"]:
        # Plain-text Colorado address in the footer. An earlier, looser regex
        # split on whitespace and produced cities like "Way Loveland" and
        # "10th Avenue Denver", so the city half is now validated against a
        # known Front Range municipality list and anything else is discarded
        # rather than stored as a bad value.
        txt = soup.get_text(" ", strip=True)
        m = re.search(
            r"(\d{2,6}\s+(?:[NSEW]\.?\s+)?[A-Za-z0-9][A-Za-z0-9.'\- ]{2,44}?"
            r"(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Ln|Lane|Way|Ct|Court|"
            r"Pl|Place|Pkwy|Parkway|Cir|Circle|Ter|Terrace|Trl|Trail|Hwy|Highway)\.?)"
            r",?\s+([A-Za-z][A-Za-z.\- ]{2,24}?),?\s+(?:CO|Colorado)\.?,?\s+(\d{5})",
            txt)
        if m:
            city = re.sub(r"\s+", " ", m.group(2)).strip(" .,-")
            if city.lower() in CO_CITIES:
                meta["street"] = re.sub(r"\s+", " ", m.group(1)).strip()
                meta["city"] = city
                meta["state"], meta["postal_code"] = "CO", m.group(3)
    return meta


# ===========================================================================
# L1 -- Jonah Digital JSON island (unit level)
# ===========================================================================

def _term_months(v) -> int | None:
    """Lease length in months from Jonah's term fields ("12", "12 months",
    "13 Months ($1,399 Base Rent)")."""
    if v in (None, "", [], {}):
        return None
    m = re.search(r"(\d{1,2})", str(v))
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 36 else None


def extract_jonah(html: str, url: str) -> list[Listing]:
    m = re.search(r'<script[^>]+id="jd-fp-data-script-app"[^>]*>(.*?)</script>',
                  html, re.S | re.I)
    if not m:
        return []
    try:
        d = json.loads(m.group(1))
    except Exception:
        return []

    out: list[Listing] = []
    fps = {str(f.get("id")): f for f in (d.get("floorplans") or [])}

    def pe(obj, key):
        p = obj.get("price_entity")
        return p.get(key) if isinstance(p, dict) else None

    def base_of(obj):
        v = pe(obj, "priceDisplayNoFees")
        return money(v) if v else None

    # unit-level rows
    for u in (d.get("units") or []):
        if not isinstance(u, dict):
            continue
        fp = fps.get(str(u.get("floorplan_id")), {})
        avail = u.get("available_date")
        iso = None
        if avail:
            try:
                from datetime import datetime, timezone
                iso = datetime.fromtimestamp(int(avail), timezone.utc).date().isoformat()
            except Exception:
                iso = None
        # Jonah publishes a full price-by-term matrix in `lease_terms`, and the
        # term the headline price applies to in `price_entity.term`. An earlier
        # version read neither -- it looked for a `lease_term`/`price` shape that
        # Jonah does not use -- so ~5,500 rows recorded no lease term at all when
        # the site had in fact disclosed one. That single omission is what made
        # lease-term disclosure look far rarer than it is.
        matrix = []
        for lt in (u.get("lease_terms") or []):
            if not isinstance(lt, dict):
                continue
            term = _term_months(lt.get("term") or lt.get("lease_term")
                                or lt.get("termDisplay"))
            if term is None:
                continue
            pr = (money(lt.get("priceLow")) or money(lt.get("price"))
                  or money(lt.get("priceDisplay")) or money(lt.get("rent")))
            if pr:
                matrix.append({"term_months": term, "rent": pr,
                               "advertised_best": bool(lt.get("best"))})
        matrix.sort(key=lambda x: x["term_months"])

        # NB: `pe` is already a helper function in this scope -- do not shadow it.
        pent = u.get("price_entity") if isinstance(u.get("price_entity"), dict) else {}
        quoted_term = _term_months(pent.get("term") or pent.get("termDisplay"))

        # The two price sources are NOT the same basis, which is easy to miss:
        #   price_entity.priceLow  = ALL-IN  (base + mandatory monthly fees)
        #   lease_terms[].priceLow = BASE    (fees excluded)
        # Verified on one unit: quoted 15-month $1,455.06 all-in against a
        # matrix 15-month entry of $1,399 base, a $56.06 fee. Comparing a matrix
        # price to a quoted price without adjusting mixes bases and silently
        # erases the fee. Mandatory monthly fees do not vary with lease length,
        # so the delta measured at the quoted term carries across the matrix.
        quoted_all_in = money(u.get("rent_min")) or money(u.get("price"))
        quoted_base = base_of(u)
        fee_delta = (round(quoted_all_in - quoted_base, 2)
                     if (quoted_all_in and quoted_base and quoted_all_in > quoted_base)
                     else 0.0)
        for e in matrix:
            e["rent_base"] = e["rent"]
            e["rent_all_in"] = round(e["rent"] + fee_delta, 2)
            e["rent"] = e["rent_all_in"]   # `rent` stays the comparable, all-in figure
            e["fee_assumed_from_quoted_term"] = bool(fee_delta)

        # Colorado requires a mandatory-fee disclosure, and Jonah renders it as
        # a structured itemisation. This is the difference between base rent and
        # what a household actually pays.
        fees = []
        pi = u.get("price_itemized")
        if isinstance(pi, dict):
            for it in (pi.get("items") or []):
                if not isinstance(it, dict):
                    continue
                v = money(it.get("value"))
                if v and it.get("label"):
                    fees.append({"label": str(it["label"])[:80], "amount": v})

        out.append(Listing(
            rent_term_matrix=matrix,
            fee_items=fees[:20],
            plan_name=u.get("floorplan_title") or fp.get("title"),
            plan_type=u.get("bedrooms_display"),
            bedrooms=beds(u.get("bedrooms")),
            bathrooms=baths(u.get("bathrooms")),
            sqft=sqft_of(u.get("square_feet")),
            rent=money(u.get("rent_min")) or money(u.get("price")),
            rent_min=money(u.get("rent_min")),
            rent_max=money(u.get("rent_max")),
            base_rent=base_of(u),
            rent_includes_fees=bool(pe(u, "pricingReflectFees")),
            units_available=fp.get("availability_count") and int(fp["availability_count"]),
            unit_number=str(u.get("apartment_number")) if u.get("apartment_number") else None,
            available_date=iso,
            available_display=u.get("available_display"),
            lease_term_months=quoted_term,
            building=str(u.get("building")) if u.get("building") else None,
            specials="; ".join(
                str(s.get("title") or s.get("name") or s)[:120]
                for s in (u.get("specials") or []) if s)[:400] or None,
            unit_amenities=[a.get("name") if isinstance(a, dict) else str(a)
                            for a in (u.get("amenities") or [])][:40],
            granularity="unit",
            source_url=url,
            extraction_method="L1:jonah-json-island",
            platform="Jonah Digital",
            confidence="high",
        ))

    # floorplan-level rows for plans with no listed units (records the zero)
    for f in (d.get("floorplans") or []):
        if f.get("units"):
            continue
        out.append(Listing(
            plan_name=f.get("title"),
            plan_type=f.get("bedrooms") if isinstance(f.get("bedrooms"), str) else None,
            bedrooms=beds(f.get("bedrooms")),
            bathrooms=baths(f.get("bathrooms")),
            sqft=sqft_of(f.get("square_feet")),
            rent=money(f.get("rent_min")),
            rent_min=money(f.get("rent_min")),
            rent_max=money(f.get("rent_max")),
            units_available=int(f.get("availability_count") or 0),
            granularity="floorplan",
            source_url=url,
            extraction_method="L1:jonah-json-island",
            platform="Jonah Digital",
            confidence="high",
        ))
    return out


# ===========================================================================
# L2 -- generic JSON island / framework state scan
# ===========================================================================
RENT_KEYS = {"rent", "rentmin", "rentmax", "minrent", "maxrent", "price",
             "marketrent", "baserent", "startingat", "minimumrent", "lowrent",
             "highrent", "pricemin", "pricemax", "rentrange", "askingrent",
             "monthlyrent", "effectiverent", "startingprice", "minprice", "maxprice"}
BED_KEYS = {"bedrooms", "beds", "bedroomcount", "numberofbedrooms", "bed",
            "bedcount", "numbeds", "bedroom"}
BATH_KEYS = {"bathrooms", "baths", "bathroomcount", "numberofbathrooms", "bath",
             "bathcount", "numbaths", "numberoffullbathrooms", "bathroom",
             "bathsfull", "fullbaths", "bathroomsfull", "batharea", "bathtotal",
             "numberofbathroomstotal", "bathrooms_min", "minbathrooms"}
NAME_KEYS = {"name", "title", "floorplantitle", "floorplanname", "planname",
             "unittype", "floorplan", "displayname", "marketingname"}
SQFT_KEYS = {"squarefeet", "sqft", "size", "floorsize", "squarefeetmin",
             "minsquarefeet", "maxsquarefeet", "area", "squarefootage"}
AVAIL_KEYS = {"availabilitycount", "unitsavailable", "availableunits",
              "numberofavailableaccommodationunits", "availablecount",
              "totalavailable", "availability"}
UNITNO_KEYS = {"apartmentnumber", "unitnumber", "unitname", "apartment", "unitid"}


def _pick(obj: dict, keys: set):
    for k, v in obj.items():
        if _norm_key(k) in keys and v not in (None, "", [], {}):
            return v
    return None


def _looks_like_listing(o: dict) -> bool:
    nk = {_norm_key(k) for k in o.keys()}
    has_rent = bool(nk & RENT_KEYS)
    has_bed = bool(nk & BED_KEYS)
    has_name = bool(nk & NAME_KEYS)
    has_sqft = bool(nk & SQFT_KEYS)
    # need rent + (bed or sqft) + a name-ish field, or bed+sqft+avail
    if has_rent and (has_bed or has_sqft) and has_name:
        return True
    if has_bed and has_sqft and bool(nk & AVAIL_KEYS):
        return True
    return False


def extract_generic_json(html: str, url: str) -> list[Listing]:
    out: list[Listing] = []
    seen = set()
    for label, blob in json_islands(html):
        if label.startswith("script#jd-fp-data-script-app"):
            continue  # L1 owns this
        cands = walk_json(blob, _looks_like_listing)
        for c in cands[:4000]:
            name = _pick(c, NAME_KEYS)
            if isinstance(name, dict):
                name = name.get("name") or name.get("title")
            name = str(name)[:120] if name else None
            rent = money(_pick(c, {"rent", "rentmin", "minrent", "price", "marketrent",
                                   "baserent", "monthlyrent", "startingat", "minimumrent",
                                   "lowrent", "pricemin", "minprice", "askingrent",
                                   "effectiverent", "startingprice"}))
            rmax = money(_pick(c, {"rentmax", "maxrent", "highrent", "pricemax", "maxprice"}))
            bd = beds(_pick(c, BED_KEYS))
            bt = baths(_pick(c, BATH_KEYS))
            sq = sqft_of(_pick(c, SQFT_KEYS))
            av = _pick(c, AVAIL_KEYS)
            un = _pick(c, UNITNO_KEYS)
            if rent is None and sq is None and bd is None:
                continue
            key = (name, rent, rmax, bd, bt, sq, str(un))
            if key in seen:
                continue
            seen.add(key)
            try:
                avn = int(float(av)) if av is not None and not isinstance(av, (list, dict)) else (
                    len(av) if isinstance(av, list) else None)
            except (TypeError, ValueError):
                avn = None
            out.append(Listing(
                plan_name=name,
                bedrooms=bd, bathrooms=bt, sqft=sq,
                rent=rent, rent_min=rent, rent_max=rmax,
                units_available=avn,
                unit_number=str(un)[:20] if un else None,
                granularity="unit" if un else "floorplan",
                source_url=url,
                extraction_method=f"L2:json-island({label})",
                platform="",
                confidence="medium",
            ))
    return out


# ===========================================================================
# L3 -- schema.org JSON-LD, walked recursively (the @graph fix)
# ===========================================================================
def extract_jsonld(html: str, url: str) -> list[Listing]:
    out: list[Listing] = []

    def is_plan(n):
        t = str(n.get("@type", "")) + " " + str(n.get("additionalType", ""))
        return ("FloorPlan" in t or "Accommodation" in t or "Apartment" in t
                or "SingleFamilyResidence" in t)

    nodes = []
    for blk in ld_json_blocks(html):
        nodes += walk_json(blk, is_plan)

    seen = set()
    for n in nodes:
        name = n.get("name")
        if isinstance(name, list):
            name = name[0] if name else None
        name = str(name)[:120] if name else None
        rent = rmin = rmax = None
        # offers / price on the node
        for offkey in ("offers", "potentialAction", "priceSpecification"):
            off = n.get(offkey)
            for o in walk_json(off, lambda x: any(
                    _norm_key(k) in {"price", "minprice", "maxprice", "lowprice",
                                     "highprice", "pricerange"} for k in x)):
                rent = rent or money(_pick(o, {"price", "minprice", "lowprice"}))
                rmax = rmax or money(_pick(o, {"maxprice", "highprice"}))
        rent = rent or money(n.get("price")) or money(n.get("priceRange"))
        av = n.get("numberOfAvailableAccommodationUnits")
        try:
            avn = int(av) if av is not None else None
        except (TypeError, ValueError):
            avn = None
        bd = beds(n.get("numberOfBedrooms") if n.get("numberOfBedrooms") is not None
                  else n.get("numberOfRooms"))
        if bd is None and isinstance(n.get("additionalType"), str):
            bd = beds(n["additionalType"])
        bt = baths(n.get("numberOfFullBathrooms") if n.get("numberOfFullBathrooms") is not None
                   else n.get("numberOfBathroomsTotal"))
        part = n.get("numberOfPartialBathrooms")
        if bt is not None and part:
            try:
                bt += 0.5 * float(part)
            except (TypeError, ValueError):
                pass
        sq = sqft_of(n.get("floorSize") or n.get("floorLevel"))
        if name is None and bd is None and sq is None:
            continue
        key = (name, rent, bd, bt, sq, avn)
        if key in seen:
            continue
        seen.add(key)
        out.append(Listing(
            plan_name=name,
            plan_type=n.get("additionalType") if isinstance(n.get("additionalType"), str) else None,
            bedrooms=bd, bathrooms=bt, sqft=sq,
            rent=rent, rent_min=rent or rmin, rent_max=rmax,
            units_available=avn,
            granularity="floorplan",
            source_url=url,
            extraction_method="L3:jsonld-graph-walk",
            platform="",
            confidence="high" if avn is not None else "medium",
        ))
    return out


# ===========================================================================
# L4 -- rendered-HTML price regex joined to floor-plan names
# ===========================================================================
FILTER_UI_PAT = re.compile(
    r"any\s+price|all\s+bedrooms|move-?in\s+date|\bfilters?\b|price\s+range|"
    r"sort\s+by|reset\s+filters", re.I)

PLAN_NAME_PAT = re.compile(
    r"^(?:[A-Z]{1,3}[0-9]{1,3}[A-Za-z]?|(?:The\s+)?[A-Z][A-Za-z'\-]{2,24})$")


def extract_html_join(html: str, url: str) -> list[Listing]:
    soup = BeautifulSoup(html, "lxml")
    for bad in soup(["script", "style", "noscript", "svg", "head"]):
        bad.decompose()
    out: list[Listing] = []
    seen = set()
    # Look for repeated card-ish containers holding a price and a bed count
    for el in soup.find_all(["article", "li", "div", "tr", "section"]):
        txt = el.get_text(" ", strip=True)
        if not (30 < len(txt) < 700):
            continue
        # Skip filter/search widgets. A price-range picker ("Any Price
        # $500-$1,500 $1,500-$2,000 ...") reads exactly like a listing card to a
        # naive money regex, and produced hundreds of rows asserting a $500
        # Denver studio when $500 was the low end of a dropdown.
        if FILTER_UI_PAT.search(txt):
            continue
        if len(re.findall(r"\$[\d,]+\s*(?:-|\u2013|to)\s*\$[\d,]+", txt)) >= 1:
            continue
        if el.find(["select", "option", "form"]) or el.name == "form":
            continue
        ident = " ".join(filter(None, [str(el.get("class") or ""), str(el.get("id") or "")]))
        if re.search(r"filter|facet|refine|search-form|dropdown|sort", ident, re.I):
            continue
        # A real listing card names a size or an availability count.
        if not re.search(r"sq\.?\s*(?:ft|feet)|\bsf\b|units?\s+available|"
                         r"available\s+(?:now|soon)|\bavailable\b", txt, re.I):
            continue
        pm = _MONEY.search(txt)
        if not pm:
            continue
        bd = None
        # Single digit only. "(\d+)" matched square footage when markup put the
        # sqft value next to a "bed" label ("554" + "bed" -> "554 bed"), which
        # produced rows claiming 554 bedrooms.
        bm = re.search(r"\b([0-9])\s*(?:bd\b|beds?\b|bedrooms?\b)", txt, re.I)
        if bm:
            bd = float(bm.group(1))
        elif re.search(r"\bstudio\b", txt, re.I):
            bd = 0.0
        else:
            continue
        btm = re.search(r"(\d+(?:\.\d)?)\s*(?:ba|bath)", txt, re.I)
        sqm = re.search(r"([\d,]{3,6})\s*(?:sq\.?\s*(?:ft|feet)|sf)", txt, re.I)
        # plan name: heading inside the card
        name = None
        h = el.find(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"])
        if h:
            cand = h.get_text(" ", strip=True)[:60]
            if cand and not _MONEY.search(cand):
                name = cand
        if not name:
            # "Has Special A2 1 Unit Available 1 Bed 1 Bath 730 Sq. Ft." -> "A2"
            nm = re.match(r"(?:has special\s+)?([A-Z][A-Za-z0-9.\-]{0,9})\s+"
                          r"(?:\d+\s+units?\s+available|\d\s*bed)", txt, re.I)
            if nm and not re.fullmatch(r"\d+", nm.group(1)):
                name = nm.group(1)
        # In card markup the first currency string is often a fee or deposit
        # ("$300 deposit"), so take the largest plausible monthly figure.
        frm = re.search(r"(?:from|starting\s+at)\s*(\$[\d,]+(?:\.\d{2})?)", txt, re.I)
        if frm:
            rent = money(frm.group(1))
        else:
            prices = [money(m.group(0)) for m in _MONEY.finditer(txt)]
            prices = [x for x in prices if x and x >= 500]
            rent = max(prices) if prices else None
        if rent is None:
            continue
        avm = re.search(r"(\d+)\s+(?:units?|homes?|apartments?)\s+available", txt, re.I)
        key = (name, rent, bd, sqm.group(1) if sqm else None)
        if key in seen:
            continue
        seen.add(key)
        out.append(Listing(
            plan_name=name,
            bedrooms=bd,
            bathrooms=baths(btm.group(1)) if btm else None,
            sqft=sqft_of(sqm.group(1)) if sqm else None,
            rent=rent, rent_min=rent,
            units_available=int(avm.group(1)) if avm else None,
            granularity="floorplan",
            source_url=url,
            extraction_method="L4:html-card-join",
            platform="",
            confidence="low",
        ))
    # de-duplicate nested containers producing identical rows
    return out


# ===========================================================================
# orchestration
# ===========================================================================
def _score(rows: list[Listing]) -> tuple:
    """Rank a layer's output: rent coverage, then availability, then volume.

    The final row-count term matters: without it, a layer returning real floor
    plan structure (beds/baths/sqft but no rent) tied with returning nothing at
    all, so the winner stayed None and the site was reported as a total miss.
    """
    if not rows:
        return (0, 0, 0, 0, 0)
    with_rent = sum(1 for r in rows if r.rent is not None)
    with_avail = sum(1 for r in rows if r.units_available is not None)
    unit_level = sum(1 for r in rows if r.granularity == "unit")
    structural = sum(1 for r in rows
                     if r.bedrooms is not None or r.sqft is not None)
    return (with_rent > 0, unit_level, with_rent, with_avail, structural)


def extract_all(html: str, url: str) -> dict:
    fp = fingerprint(html)
    layers = {
        "L1:jonah": extract_jonah(html, url),
        "L1b:spaces": extract_spaces(html, url),
        "L2:json-island": extract_generic_json(html, url),
        "L3:jsonld": extract_jsonld(html, url),
        "L4:html-join": extract_html_join(html, url),
    }
    best_name, best_rows = None, []
    for name, rows in layers.items():
        if _score(rows) > _score(best_rows):
            best_name, best_rows = name, rows

    # Enrich: if the winning layer lacks availability but L3 has it, join on plan name.
    if best_rows and best_name != "L3:jsonld":
        l3 = {(r.plan_name or "").strip().lower(): r for r in layers["L3:jsonld"] if r.plan_name}
        for r in best_rows:
            k = (r.plan_name or "").strip().lower()
            if r.units_available is None and k in l3:
                r.units_available = l3[k].units_available
            if r.sqft is None and k in l3:
                r.sqft = l3[k].sqft
            if r.bathrooms is None and k in l3:
                r.bathrooms = l3[k].bathrooms
    # and the reverse: L3 structure + L4 rent
    if best_name == "L3:jsonld":
        l4 = {(r.plan_name or "").strip().lower(): r for r in layers["L4:html-join"] if r.plan_name}
        for r in best_rows:
            k = (r.plan_name or "").strip().lower()
            if r.rent is None and k in l4:
                r.rent = l4[k].rent
                r.rent_min = l4[k].rent
                r.extraction_method += "+L4-rent"

    for r in best_rows:
        r.platform = r.platform or fp["primary"]

    return {
        "fingerprint": fp,
        "layer_counts": {k: len(v) for k, v in layers.items()},
        "layer_rent_counts": {k: sum(1 for r in v if r.rent is not None) for k, v in layers.items()},
        "winning_layer": best_name,
        "rows": best_rows,
        "meta": property_meta(html, url),
    }


# ===========================================================================
# L1b -- "Spaces" plugin (Griffis Residential and others)
#
# Publishes `const spacesUnitJSON = [...]` with one record per available unit.
# Two quirks: bed/bath/floor live in a css class array rather than fields, and
# price is a MATRIX keyed by lease term -- the same unit is $4,133 on a 2-month
# term and $1,552 on 15 months. A rent quoted without its term is not
# comparable to anything, so the whole matrix is retained.
# ===========================================================================
CSS_BED = re.compile(r"^(\d+)bed$", re.I)
CSS_BATH = re.compile(r"^(\d+(?:_\d)?)bath$", re.I)
CSS_STUDIO = re.compile(r"^(?:studio|0bed)$", re.I)
CSS_SQFT = re.compile(r"^(?:sqft|size)_(\d{3,5})$", re.I)
CSS_FLOOR = re.compile(r"^floor_(\d+)$", re.I)
CSS_TAG = re.compile(r"^tag-(.+)$", re.I)


def extract_spaces(html: str, url: str) -> list[Listing]:
    units = None
    for label, blob in json_islands(html):
        if label == "js:spacesUnitJSON" and isinstance(blob, list):
            units = blob
            break
    if not units:
        return []

    out: list[Listing] = []
    for u in units:
        if not isinstance(u, dict):
            continue
        css = [str(c) for c in (u.get("css") or [])]
        bd = bt = sq = None
        tags = []
        for c in css:
            if CSS_STUDIO.match(c):
                bd = 0.0
            m = CSS_BED.match(c)
            if m:
                bd = float(m.group(1))
            m = CSS_BATH.match(c)
            if m:
                bt = float(m.group(1).replace("_", "."))
            m = CSS_SQFT.match(c)
            if m:
                sq = sqft_of(m.group(1))
            m = CSS_TAG.match(c)
            if m:
                tags.append(m.group(1))

        matrix = []
        for lt in (u.get("lease_terms") or []):
            if not isinstance(lt, dict):
                continue
            try:
                term = int(str(lt.get("lease_term")).strip())
            except (TypeError, ValueError):
                continue
            price = money(lt.get("price"))
            if price:
                matrix.append({"term_months": term, "rent": price})
        matrix.sort(key=lambda x: x["term_months"])

        # canonical quote: the 12-month term where offered, else the longest
        canon = next((m for m in matrix if m["term_months"] == 12), None)
        if canon is None and matrix:
            canon = matrix[-1]

        out.append(Listing(
            plan_name=None,
            bedrooms=bd, bathrooms=bt, sqft=sq,
            rent=canon["rent"] if canon else None,
            rent_min=min((m["rent"] for m in matrix), default=None),
            rent_max=max((m["rent"] for m in matrix), default=None),
            units_available=1,
            unit_number=str(u.get("id")) if u.get("id") else None,
            available_date=u.get("available_on"),
            lease_term_months=canon["term_months"] if canon else None,
            rent_term_matrix=matrix,
            unit_amenities=tags[:20],
            granularity="unit",
            source_url=url,
            extraction_method="L1b:spaces-unit-json",
            platform="Spaces plugin",
            confidence="high",
        ))
    return out
