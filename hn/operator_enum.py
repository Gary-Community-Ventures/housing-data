"""
Enumerate property pages on an operator's own site.

Most operators keep every community on their own domain rather than giving each
a marketing site. That turned out NOT to be an extraction problem -- the generic
JSON-in-JS scanner reads Griffis, Cortland and RedPeak fine -- it is a
DISCOVERY problem: we need the list of property URLs.

Sitemaps are the deterministic way to get it. robots.txt advertises them, they
are meant to be machine-read, and it costs one request instead of crawling.
Falls back to parsing the portfolio page's own links.
"""
from __future__ import annotations
import re, sys, os
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hn.policy import Fetcher, is_denied, _host

# URL shapes that indicate an individual community page
PROPERTY_PATH = re.compile(
    r"/(?:propert(?:y|ies)|communit(?:y|ies)|apartments?|residences?|locations?|"
    r"our-communities|find-a-home|living|neighborhoods?)/[^/]+/?$", re.I)
# ...and pages that are clearly not a single property
NOT_PROPERTY = re.compile(
    r"/(?:blog|news|careers?|about|contact|privacy|terms|search|sitemap|team|"
    r"press|investors?|resident|portal|apply|tour|gallery|amenities|faq|"
    r"floorplans?|availability|pricing|specials|page|category|tag|author)\b", re.I)

CO_CITY = (r"denver|aurora|lakewood|boulder|littleton|arvada|thornton|"
           r"westminster|centennial|broomfield|longmont|loveland|greeley|englewood|"
           r"golden|parker|brighton|lafayette|louisville|superior|erie|"
           r"highlands-?ranch|lone-?tree|wheat-?ridge|northglenn|commerce-?city|"
           r"castle-?rock|fort-?collins|colorado-?springs|glendale|edgewater")
CO_HINTS = re.compile(CO_CITY + r"|colorado", re.I)

# An explicit state marker in the slug is far more reliable than a city name.
# Several Colorado city names collide with other states -- Lafayette LA,
# Glendale CA, and a Minnesota URL that merely contained "edgewater" all passed
# a bare city-name filter.
CO_EXPLICIT = re.compile(r"[-/](?:co|colo|colorado)(?:/|$|[-_])", re.I)
OTHER_STATE = re.compile(
    r"[-/](?:al|ak|az|ar|ca|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|"
    r"ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|"
    r"wv|wi|wy|dc)(?:/|$)|"
    r"(?:alabama|alaska|arizona|arkansas|california|connecticut|delaware|florida|"
    r"georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|"
    r"maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|"
    r"nebraska|nevada|new-hampshire|new-jersey|new-mexico|new-york|north-carolina|"
    r"north-dakota|ohio|oklahoma|oregon|pennsylvania|rhode-island|south-carolina|"
    r"south-dakota|tennessee|texas|utah|vermont|virginia|washington|west-virginia|"
    r"wisconsin|wyoming)(?:/|$|[-_])", re.I)

# Region/hub landing pages, not individual communities.
HUB_PATH = re.compile(r"/(?:" + CO_CITY + r"|colorado)(?:-(?:metro|area|co|colorado))?/?$", re.I)


def classify_state(url: str) -> str:
    """'co', 'other', or 'unknown' from the URL alone."""
    if CO_EXPLICIT.search(url):
        return "co"
    if OTHER_STATE.search(url):
        return "other"
    if CO_HINTS.search(url):
        return "co"
    return "unknown"


def sitemap_urls(f: Fetcher, origin: str) -> list[str]:
    """Sitemap locations advertised by robots.txt, plus the conventional paths."""
    out, host = [], _host(origin)
    scheme = urlparse(origin).scheme or "https"
    try:
        r = f.get(f"{scheme}://{host}/robots.txt")
        if r.ok:
            out += re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r.text)
    except Exception:
        pass
    for p in ("/sitemap.xml", "/sitemap_index.xml", "/community-sitemap.xml",
              "/property-sitemap.xml", "/wp-sitemap.xml"):
        u = f"{scheme}://{host}{p}"
        if u not in out:
            out.append(u)
    return out


def _locs(xml: str) -> list[str]:
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml, re.I)


def from_sitemap(f: Fetcher, origin: str, max_sitemaps=6) -> list[str]:
    seen_sm, urls = set(), []
    queue = sitemap_urls(f, origin)
    while queue and len(seen_sm) < max_sitemaps:
        sm = queue.pop(0)
        if sm in seen_sm or is_denied(sm)[0]:
            continue
        seen_sm.add(sm)
        r = f.get(sm)
        if not r.ok or "<" not in r.text[:400]:
            continue
        locs = _locs(r.text)
        # a sitemap index points at more sitemaps
        if "<sitemapindex" in r.text[:800].lower():
            nested = [l for l in locs if l.endswith(".xml")]
            # prefer ones that sound like communities
            nested.sort(key=lambda x: 0 if re.search(
                r"propert|communit|apartment|location", x, re.I) else 1)
            queue = nested + queue
            continue
        urls += locs
    return urls


def from_portfolio_page(f: Fetcher, portfolio_url: str) -> list[str]:
    r = f.get(portfolio_url)
    if not r.ok:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    base_host = _host(r.final_url or portfolio_url)
    out = []
    for a in soup.find_all("a", href=True):
        full = urljoin(r.final_url or portfolio_url, a["href"]).split("#")[0]
        if _host(full) != base_host or is_denied(full)[0]:
            continue
        out.append(full)
    return out


def property_urls(f: Fetcher, origin: str, portfolio_url: str | None = None,
                  co_only=True, limit=400) -> list[str]:
    cands = from_sitemap(f, origin)
    if len(cands) < 5 and portfolio_url:
        cands = from_portfolio_page(f, portfolio_url)

    shortlist, seen = [], set()
    for u in cands:
        path = urlparse(u).path
        if not path or path == "/":
            continue
        if NOT_PROPERTY.search(path) or HUB_PATH.search(path):
            continue
        if not PROPERTY_PATH.search(path):
            continue
        key = u.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        shortlist.append((u, classify_state(u)))

    if not co_only:
        return [u for u, _ in shortlist][:limit]

    co = [u for u, st in shortlist if st == "co"]
    unknown = [u for u, st in shortlist if st == "unknown"]
    # If a site labels states in its slugs, trust that and drop the rest. If it
    # labels none (Griffis: /property/north-union/), URL filtering cannot work,
    # so pass the unknowns through and let collection verify the address --
    # better than silently dropping every Colorado property on the site.
    if co:
        return (co + unknown)[:limit] if len(co) < 3 else co[:limit]
    return unknown[:limit]


if __name__ == "__main__":
    f = Fetcher(min_delay=2.0)
    for origin, portfolio in [
        ("https://griffisresidential.com/", "https://griffisresidential.com/communities/colorado/"),
        ("https://www.willowbridgepc.com/", "https://www.willowbridgepc.com/colorado"),
        ("https://cortland.com/", "https://cortland.com/apartments/"),
    ]:
        urls = property_urls(f, origin, portfolio)
        print(f"\n{origin}  -> {len(urls)} CO property URLs")
        for u in urls[:8]:
            print("   ", u)
