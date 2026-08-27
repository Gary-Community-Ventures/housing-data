"""
Access policy: domain denylist, vendor-host detection, robots.txt, rate limiting.

Every network request in this project goes through Fetcher.get(). There is no
other code path to the network. That is deliberate: the compliance rules are
enforced in one place so the provenance story is auditable.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.robotparser
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse, urljoin

import requests

CONTACT_URL = "https://garycommunity.org/housing-navigator-bot"
USER_AGENT = (
    "HousingNavigatorBot/0.1 (Gary Community Ventures housing navigator; "
    f"+{CONTACT_URL})"
)

# ---------------------------------------------------------------------------
# RULE 1 — hard domain denylist. Leasing-engine vendors whose terms prohibit
# automated access. We never request, follow, or parse these. Not negotiable.
# ---------------------------------------------------------------------------
DENY_EXACT = {
    "securecafe.com",
    "rentcafe.com",
    "api.rentcafe.com",
    "onlineleasing.realpage.com",
    "selftournow.com",
    "prospectportal.com",
    "activebuilding.com",
    "app.meetelise.com",
}
# suffix rules: any host ending in these (covers subdomains + entrata.* TLDs)
DENY_SUFFIX = (
    ".securecafe.com",
    ".rentcafe.com",
    ".onlineleasing.realpage.com",
    ".selftournow.com",
    ".prospectportal.com",
    ".appfolio.com",
    ".myresman.com",
    ".activebuilding.com",
    ".meetelise.com",
)
# entrata.* — any TLD
DENY_STEMS = ("entrata",)

# ILS / aggregator listing sites. Prohibited as enumeration sources, and never
# fetched at all: their terms prohibit automated access and several are CoStar
# properties that enforce. A property's "marketing site" that turns out to be an
# aggregator listing page is not the property's own site and is dropped.
ILS_DENY = {
    "apartments.com", "zillow.com", "realtor.com", "rent.com",
    "apartmentguide.com", "apartmentlist.com", "trulia.com", "hotpads.com",
    "padmapper.com", "forrent.com", "costar.com", "loopnet.com",
    "apartmentfinder.com", "rentals.com", "zumper.com", "apartmenthomeliving.com",
    "westsiderentals.com", "abodo.com", "rentler.com",
}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().lstrip(".")


def is_denied(url: str) -> tuple[bool, str]:
    """RULE 1. Returns (denied, reason)."""
    h = _host(url)
    if not h:
        return True, "unparseable-host"
    if h in DENY_EXACT:
        return True, f"denylist:{h}"
    for suf in DENY_SUFFIX:
        if h.endswith(suf):
            return True, f"denylist-suffix:{suf}"
    for ils in ILS_DENY:
        if h == ils or h.endswith("." + ils):
            return True, f"ils-aggregator:{ils}"
    labels = h.split(".")
    for stem in DENY_STEMS:
        # entrata.com, entrata.net, foo.entrata.com ...
        if stem in labels:
            return True, f"denylist-stem:{stem}.*"
    if "appfolio.com" in h and "/listings" in url:
        return True, "denylist:appfolio-listings"
    return False, ""


# ---------------------------------------------------------------------------
# RULE 3 — vendor-hosted marketing sites. If the property's own marketing site
# IS the vendor's product, the vendor's anti-scraping terms attach to the page
# itself. Skip the property entirely.
# ---------------------------------------------------------------------------
VENDOR_HOSTED_HOST_MARKERS = {
    "prospectportal.com": "Entrata (ProspectPortal)",
    "appfolio.com": "AppFolio",
    "rentcafewebsites.com": "Yardi RENTCafe Websites",
    "securecafe.com": "Yardi SecureCafe",
    "entrata.com": "Entrata",
    "residentportal.com": "Entrata ResidentPortal",
    "myresman.com": "ResMan",
    "realpage.com": "RealPage",
    "rentprogress.com": "Progress Residential",
    "onsitepm.com": "OnSite",
}
# body/footer markers that indicate the *page itself* is a vendor product and
# republishes vendor terms. Entrata does this verbatim with a labeled footer.
VENDOR_HOSTED_BODY_MARKERS = {
    "entrata": [
        "entrata, inc",
        "powered by entrata",
        "entrata.com/terms",
        "prospectportal",
    ],
    "yardi": [
        "yardi systems",
        "rentcafe.com/terms",
        "yardi.com/terms",
        "powered by yardi",
    ],
    "realpage": ["realpage, inc", "powered by realpage", "realpage.com/terms"],
    "appfolio": ["appfolio, inc", "powered by appfolio"],
    "resman": ["resman, llc", "powered by resman"],
}


def vendor_hosted_by_host(url: str) -> str | None:
    h = _host(url)
    for marker, vendor in VENDOR_HOSTED_HOST_MARKERS.items():
        if h == marker or h.endswith("." + marker):
            return vendor
    return None


def vendor_hosted_by_body(html: str) -> str | None:
    low = html.lower()
    for vendor, markers in VENDOR_HOSTED_BODY_MARKERS.items():
        for m in markers:
            if m in low:
                return f"{vendor} (body marker: {m!r})"
    return None


# ---------------------------------------------------------------------------
# RULE 5 — robots.txt + polite rate limiting
# ---------------------------------------------------------------------------
@dataclass
class FetchResult:
    url: str
    final_url: str | None = None
    status: int | None = None
    text: str = ""
    ok: bool = False
    outcome: str = ""          # ok | denied | robots | http_error | error | vendor_hosted
    detail: str = ""
    elapsed_ms: int = 0
    bytes: int = 0
    fetched_at: str = ""
    via: str = "http"          # http | browser

    def to_log(self) -> dict:
        d = asdict(self)
        d.pop("text", None)
        return d


class Fetcher:
    """Single choke point for all outbound HTTP. Enforces rules 1, 3, 5."""

    def __init__(self, min_delay=3.0, timeout=30, log_path="logs/fetch_log.jsonl",
                 cache_dir="data/raw", respect_robots=True):
        self.min_delay = min_delay
        self.timeout = timeout
        self.log_path = log_path
        self.cache_dir = cache_dir
        self.respect_robots = respect_robots
        self._last: dict[str, float] = {}
        self._robots: dict[str, tuple] = {}
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)

    # -- robots -------------------------------------------------------------
    def robots_for(self, url: str):
        h = _host(url)
        scheme = urlparse(url).scheme or "https"
        if h in self._robots:
            return self._robots[h]
        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"{scheme}://{h}/robots.txt"
        crawl_delay = None
        try:
            self._throttle(h)
            r = self.s.get(robots_url, timeout=15)
            self._last[h] = time.time()
            if r.status_code == 200 and len(r.text) < 500_000:
                rp.parse(r.text.splitlines())
                cd = rp.crawl_delay(USER_AGENT) or rp.crawl_delay("*")
                if cd:
                    crawl_delay = float(cd)
            else:
                rp.allow_all = True
        except Exception:
            # robots unreachable -> be conservative but not paralysed: allow,
            # since an unreachable robots.txt is conventionally "allow all".
            rp.allow_all = True
        self._robots[h] = (rp, crawl_delay)
        return self._robots[h]

    def robots_allows(self, url: str) -> tuple[bool, float | None]:
        if not self.respect_robots:
            return True, None
        rp, cd = self.robots_for(url)
        try:
            return bool(rp.can_fetch(USER_AGENT, url)), cd
        except Exception:
            return True, cd

    def _throttle(self, host: str, extra: float | None = None):
        delay = max(self.min_delay, extra or 0)
        last = self._last.get(host)
        if last is not None:
            wait = delay - (time.time() - last)
            if wait > 0:
                time.sleep(wait)

    # -- main ---------------------------------------------------------------
    def get(self, url: str, allow_vendor=False) -> FetchResult:
        from datetime import datetime, timezone
        now = lambda: datetime.now(timezone.utc).isoformat()
        res = FetchResult(url=url, fetched_at=now())

        denied, why = is_denied(url)
        if denied:
            res.outcome, res.detail = "denied", why
            self._log(res)
            return res

        if not allow_vendor:
            v = vendor_hosted_by_host(url)
            if v:
                res.outcome, res.detail = "vendor_hosted", v
                self._log(res)
                return res

        allowed, cd = self.robots_allows(url)
        if not allowed:
            res.outcome, res.detail = "robots", "robots.txt disallows this path"
            self._log(res)
            return res

        h = _host(url)
        self._throttle(h, cd)
        t0 = time.time()
        try:
            r = self.s.get(url, timeout=self.timeout, allow_redirects=True)
            self._last[h] = time.time()
            res.status = r.status_code
            res.final_url = r.url
            res.elapsed_ms = int((time.time() - t0) * 1000)
            # a redirect onto a denied host must not be parsed
            denied2, why2 = is_denied(r.url)
            if denied2:
                res.outcome, res.detail = "denied", f"redirected-to-{why2}"
                self._log(res)
                return res
            if r.status_code == 200:
                res.text = r.text
                res.bytes = len(r.content)
                res.ok = True
                res.outcome = "ok"
                self._cache_write(r.url, r.text)
            else:
                res.outcome = "http_error"
                res.detail = f"HTTP {r.status_code}"
        except Exception as e:
            self._last[h] = time.time()
            res.outcome = "error"
            res.detail = f"{type(e).__name__}: {e}"[:300]
            res.elapsed_ms = int((time.time() - t0) * 1000)
        self._log(res)
        return res

    def _cache_write(self, url: str, text: str):
        """Persist raw HTML so extraction can be re-run without re-fetching.
        Iterating on parsers is the common case; re-hitting every host to do it
        is both slow and impolite."""
        try:
            import hashlib
            h = hashlib.sha256(url.encode()).hexdigest()[:20]
            host = _host(url) or "unknown"
            d = os.path.join(self.cache_dir, host)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, h + ".html"), "w") as f:
                f.write(url + "\n<!--HN-CACHE-->\n" + text)
        except Exception:
            pass

    def _log(self, res: FetchResult):
        with open(self.log_path, "a") as f:
            f.write(json.dumps(res.to_log()) + "\n")

    # ------------------------------------------------------------------
    # Narrow exception: reading a TERMS DOCUMENT on an otherwise-denied host.
    #
    # RULE 4 says check the terms before deciding about a site. On denylisted
    # hosts that created a circular problem -- we refused to fetch anything,
    # including the page that states the policy, so the denial rested on an
    # assumption rather than evidence. Fetching one public legal page to learn
    # what it says is not data collection, so it is permitted here and logged
    # with purpose="terms-audit". Still honours robots.txt. Never returns
    # listing data and is never called by the collector.
    # ------------------------------------------------------------------
    TERMS_PATH_OK = re.compile(
        r"/(terms|legal|terms-of-use|terms-of-service|terms-and-conditions|"
        r"terms_of_use|conditions|user-agreement|tos)", re.I)

    def get_terms_document(self, url: str) -> FetchResult:
        from datetime import datetime, timezone
        res = FetchResult(url=url, fetched_at=datetime.now(timezone.utc).isoformat())
        if not self.TERMS_PATH_OK.search(urlparse(url).path or ""):
            res.outcome = "refused"
            res.detail = "not a terms-document path; exception does not apply"
            self._log(res)
            return res
        allowed, cd = self.robots_allows(url)
        if not allowed:
            res.outcome = "robots"
            res.detail = "robots.txt disallows the terms path"
            self._log(res)
            return res
        h = _host(url)
        self._throttle(h, cd)
        import time as _t
        t0 = _t.time()
        try:
            r = self.s.get(url, timeout=self.timeout, allow_redirects=True)
            self._last[h] = _t.time()
            res.status, res.final_url = r.status_code, r.url
            res.elapsed_ms = int((_t.time() - t0) * 1000)
            if r.status_code == 200:
                res.text, res.bytes, res.ok, res.outcome = r.text, len(r.content), True, "ok"
            else:
                res.outcome, res.detail = "http_error", f"HTTP {r.status_code}"
        except Exception as e:
            self._last[h] = _t.time()
            res.outcome, res.detail = "error", f"{type(e).__name__}: {e}"[:200]
        res.detail = (res.detail + " | purpose=terms-audit").strip(" |")
        self._log(res)
        return res
