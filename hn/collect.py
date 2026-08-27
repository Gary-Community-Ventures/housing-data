"""
Per-property collection orchestration.

Order of operations is the compliance story, so it is fixed:
  1. denylist check (RULE 1)          -> never even resolved
  2. homepage fetch
  3. vendor-hosted check (RULE 3)     -> skip property entirely
  4. terms check (RULE 4)             -> drop if prohibiting, always logged
  5. floor-plan page discovery
  6. extract (RULE 6: no images stored)
Everything routes through Fetcher, which enforces robots.txt and rate limits.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .policy import Fetcher, is_denied, vendor_hosted_by_host, _host
from .terms import TermsAuditor
from .extract import extract_all, fingerprint, vendor_hosted, Listing

# outcome codes used by the yield report
OUT_RENT_AVAIL = "A_rent_and_availability"
OUT_RENT_ONLY = "B1_rent_only"
OUT_AVAIL_ONLY = "B2_availability_only"
OUT_STRUCTURE = "B3_structure_only"
OUT_NOTHING = "C_nothing"
OUT_VENDOR = "D_skipped_vendor_hosted"
OUT_BLOCKED = "E_bot_blocked"
OUT_TERMS = "F_dropped_terms_prohibit"
OUT_UNREACHABLE = "G_unreachable"
OUT_DENIED = "H_denylisted"
OUT_NO_FP_PAGE = "I_no_floorplan_page"

FP_HINTS = [
    (r"floor.?plans?", 100), (r"availab", 95), (r"pricing", 80),
    (r"apartments?$", 60), (r"rentals?", 55), (r"units?$", 50),
    (r"our.?homes", 50), (r"residences", 45), (r"find.?your.?home", 70),
]
# Same reasoning as COMMON_TERMS_PATHS -- only probed when link discovery fails.
FP_COMMON_PATHS = ["/floorplans/", "/floor-plans/", "/availability/", "/apartments/"]
# Block detection. Two earlier versions of this were wrong in opposite ways and
# both corrupted the yield report, so the reasoning is recorded here:
#
#   1. A loose marker list matched the hidden `grecaptcha-badge` CSS that ships
#      with almost every contact form -> healthy sites labelled bot-blocked.
#   2. `/cdn-cgi/challenge-platform` was treated as proof of a block, but it is
#      Cloudflare's PASSIVE JS-detection beacon, injected into pages that serve
#      their full content normally (observed on 200s of 180-385KB). Treating it
#      as a block reported ~1/3 of the sample as blocked when it was not.
#
# What actually indicates a refusal: an explicit status code, or an interstitial
# page, which is always tiny. A 200 carrying a full page of markup is not a
# block regardless of which security vendor's script it contains.
CHALLENGE_MARKERS = [
    "cf_chl_opt", "cf-browser-verification", "/cdn-cgi/challenge-platform",
    "just a moment", "attention required", "checking your browser before accessing",
    "enable javascript and cookies to continue", "incapsula incident id",
    "request unsuccessful", "perimeterx", "px-captcha", "ddos-guard",
    "captcha", "are you a human", "verify you are human", "unusual traffic",
    "security check", "access denied",
]
# Unambiguous refusal text, credible at any page size.
EXPLICIT_BLOCK_MARKERS = [
    "sorry, you have been blocked", "you have been blocked",
    "access to this page has been denied", "this website is using a security service to protect itself",
]
INTERSTITIAL_MAX_BYTES = 30_000


@dataclass
class SiteResult:
    name: str | None
    operator: str | None
    marketing_url: str
    outcome: str
    detail: str = ""
    floorplan_url: str | None = None
    platform: str = "unknown"
    builders: list = field(default_factory=list)
    widgets: list = field(default_factory=list)
    leasing_engines_referenced: list = field(default_factory=list)
    winning_layer: str | None = None
    layer_counts: dict = field(default_factory=dict)
    layer_rent_counts: dict = field(default_factory=dict)
    n_rows: int = 0
    n_rows_with_rent: int = 0
    n_rows_with_avail: int = 0
    n_units_available: int | None = None
    terms_verdict: str = ""
    terms_url: str | None = None
    robots_ok: bool = True
    collected_at: str = ""
    via: str = "http"
    candidate_source: str | None = None
    rent_behind_denylisted_portal: bool = False
    name_source: str | None = None

    def dict(self):
        return asdict(self)


def looks_blocked(status: int | None, text: str) -> bool:
    if status in (403, 429, 503):
        return True
    low = (text or "").lower()
    if any(m in low for m in EXPLICIT_BLOCK_MARKERS):
        return True
    # Challenge markers only count on a response too small to be a real page.
    if len(text or "") < INTERSTITIAL_MAX_BYTES and any(m in low for m in CHALLENGE_MARKERS):
        return True
    return False


# A single-plan DETAIL page (".../floor-plan/1-bedroom/design-1a.html") scores
# just as well on keyword hints as the index that lists every plan, and picking
# one silently reduced whole properties to a single row. Prefer shallow paths.
PLAN_DETAIL_PAT = re.compile(
    r"/(?:design|plan|unit)[-_][0-9a-z]{1,6}(?:\.html?)?/?$|"
    r"/(?:studio|[1-4])[-_]?bed(?:room)?s?/[^/]+$", re.I)


def find_floorplan_url(homepage: str, html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    base_host = _host(homepage)
    scored = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        txt = (a.get_text(" ", strip=True) or "")[:60]
        full = urljoin(homepage, href).split("#")[0]
        if _host(full) != base_host:
            continue
        if is_denied(full)[0]:
            continue
        path = urlparse(full).path.lower()
        score = 0
        for pat, pts in FP_HINTS:
            if re.search(pat, path, re.I):
                score = max(score, pts)
            if re.search(pat, txt, re.I):
                score = max(score, pts - 5)
        if not score:
            continue
        if re.search(r"gallery|photo|tour|virtual|map", path):
            continue
        # penalise depth: an index lives near the root
        segs = [x for x in path.split("/") if x]
        score -= 9 * max(0, len(segs) - 1)
        if PLAN_DETAIL_PAT.search(path):
            score -= 45
        scored.append((score, len(path), full))
    if not scored:
        return None
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[0][2]


def find_plan_detail_urls(page_url: str, html: str, limit=14) -> list[str]:
    """Sites that publish one page per floor plan with no index."""
    soup = BeautifulSoup(html, "lxml")
    base_host = _host(page_url)
    out = []
    for a in soup.find_all("a", href=True):
        full = urljoin(page_url, a["href"]).split("#")[0]
        if _host(full) != base_host or is_denied(full)[0]:
            continue
        if PLAN_DETAIL_PAT.search(urlparse(full).path.lower()) and full not in out:
            out.append(full)
    return out[:limit]


class Collector:
    def __init__(self, fetcher: Fetcher | None = None, out_dir="data"):
        self.f = fetcher or Fetcher()
        self.terms = TermsAuditor(self.f)
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.listings_path = os.path.join(out_dir, "listings.jsonl")
        self.results_path = os.path.join(out_dir, "site_results.jsonl")

    def now(self):
        return datetime.now(timezone.utc).isoformat()

    def collect(self, cand: dict) -> SiteResult:
        url = (cand.get("marketing_url") or "").strip()
        res = SiteResult(name=cand.get("name"), operator=cand.get("operator"),
                         marketing_url=url, outcome=OUT_NOTHING,
                         collected_at=self.now(),
                         candidate_source=cand.get("candidate_source"))
        if not url:
            res.outcome, res.detail = OUT_NOTHING, "no marketing_url"
            return self._finish(res, [])

        # RULE 1
        denied, why = is_denied(url)
        if denied:
            res.outcome, res.detail = OUT_DENIED, why
            return self._finish(res, [])
        # RULE 3 by host
        v = vendor_hosted_by_host(url)
        if v:
            res.outcome, res.detail = OUT_VENDOR, f"host is vendor product: {v}"
            return self._finish(res, [])

        home = self.f.get(url)
        if not home.ok:
            if looks_blocked(home.status, home.text):
                res.outcome, res.detail = OUT_BLOCKED, f"{home.outcome} {home.detail}"
            elif home.outcome == "robots":
                res.outcome, res.detail, res.robots_ok = OUT_UNREACHABLE, "robots.txt disallows", False
            else:
                res.outcome, res.detail = OUT_UNREACHABLE, f"{home.outcome} {home.detail}"
            return self._finish(res, [])

        if looks_blocked(home.status, home.text):
            res.outcome, res.detail = OUT_BLOCKED, "challenge page returned with 200"
            return self._finish(res, [])

        # RULE 3 by strong body marker
        vb = vendor_hosted(home.text)
        if vb:
            res.outcome, res.detail = OUT_VENDOR, f"page is vendor product: {vb}"
            fp = fingerprint(home.text)
            res.platform, res.builders = fp["primary"], fp["builders"]
            return self._finish(res, [])

        # RULE 4 -- standing terms check, logged every run
        trec = self.terms.check(home.final_url or url, home.text)
        res.terms_verdict, res.terms_url = trec.verdict, trec.terms_url
        if not trec.collect_allowed:
            res.outcome = OUT_TERMS if trec.verdict == "PROHIBITS" else OUT_UNREACHABLE
            res.detail = trec.notes
            return self._finish(res, [])

        # floor-plan page
        fp_url = find_floorplan_url(home.final_url or url, home.text)
        page_html, page_url = None, None
        if fp_url:
            r = self.f.get(fp_url)
            if r.ok and not looks_blocked(r.status, r.text):
                page_html, page_url = r.text, r.final_url or fp_url
            elif looks_blocked(r.status, r.text):
                res.outcome, res.detail = OUT_BLOCKED, f"floorplan page blocked: {r.detail}"
                res.floorplan_url = fp_url
                return self._finish(res, [])
        if page_html is None:
            for p in FP_COMMON_PATHS:
                cand_url = urljoin(home.final_url or url, p)
                if cand_url == fp_url:
                    continue
                r = self.f.get(cand_url)
                if r.ok and len(r.text) > 5000 and not looks_blocked(r.status, r.text):
                    page_html, page_url = r.text, r.final_url or cand_url
                    break
        if page_html is None:
            # fall back to the homepage itself -- some sites list plans inline
            page_html, page_url = home.text, home.final_url or url
            res.detail = "no floor-plan page found; parsed homepage"

        res.floorplan_url = page_url
        ex = extract_all(page_html, page_url)

        # Some sites publish one page per floor plan and no index at all. If the
        # page we landed on yielded almost nothing but advertises plan-detail
        # pages, walk a bounded number of them and merge. Capped at 8 so a
        # brochure site can never turn into a crawl.
        structural = sum(1 for r in ex["rows"] if r.bedrooms is not None or r.sqft is not None)
        if structural < 2:
            detail_urls = find_plan_detail_urls(page_url, page_html, limit=8)
            merged, pages_ok = list(ex["rows"]), 0
            for du in detail_urls:
                dr = self.f.get(du)
                if not dr.ok or looks_blocked(dr.status, dr.text):
                    continue
                dex = extract_all(dr.text, dr.final_url or du)
                if dex["rows"]:
                    merged.extend(dex["rows"])
                    pages_ok += 1
            if pages_ok:
                seen_rows, dedup = set(), []
                for r in merged:
                    k = (r.plan_name, r.bedrooms, r.bathrooms, r.sqft, r.rent, r.unit_number)
                    if k in seen_rows:
                        continue
                    seen_rows.add(k)
                    dedup.append(r)
                ex["rows"] = dedup
                ex["winning_layer"] = (ex["winning_layer"] or "") + f"+plan-pages({pages_ok})"
                res.detail = (res.detail + f" merged {pages_ok} plan-detail pages").strip()
        fpr = ex["fingerprint"]
        res.platform = fpr["primary"]
        res.builders = fpr["builders"]
        res.widgets = fpr["widgets"]
        res.leasing_engines_referenced = fpr["leasing_engines_referenced"]
        res.winning_layer = ex["winning_layer"]
        res.layer_counts = ex["layer_counts"]
        res.layer_rent_counts = ex["layer_rent_counts"]

        if fpr["vendor_hosted"]:
            res.outcome = OUT_VENDOR
            res.detail = f"floor-plan page is vendor product: {fpr['vendor_hosted']}"
            return self._finish(res, [])

        rows = ex["rows"]
        meta = ex["meta"]
        for r in rows:
            strong_name = meta.get("name_source") in ("schema.org", "og-meta")
            r.property_name = (meta.get("property_name") if strong_name
                               else (cand.get("name") or meta.get("property_name")))
            r.operator = cand.get("operator")
            r.street = meta.get("street") or cand.get("address")
            r.city = meta.get("city") or cand.get("city")
            r.state = meta.get("state") or cand.get("state") or "CO"
            r.postal_code = meta.get("postal_code")
            r.lat, r.lon = meta.get("lat"), meta.get("lon")
            # Concessions are advertised property-wide ("Up to 12 weeks free on
            # select homes"), not per unit, so they have to be carried down.
            r.property_specials = meta.get("property_specials")
            r.collected_at = res.collected_at

        res.n_rows = len(rows)
        res.n_rows_with_rent = sum(1 for r in rows if r.rent is not None)
        res.n_rows_with_avail = sum(1 for r in rows if r.units_available is not None)
        # Unit-granularity rows ARE available units (one row per available unit).
        # Floorplan-granularity rows carry a count. Add them without double
        # counting: only sum floorplan rows for plans that produced no unit rows.
        unit_rows = [r for r in rows if r.granularity == "unit"]
        plans_with_units = {(r.plan_name or "").strip().lower() for r in unit_rows}
        fp_only = sum(
            r.units_available for r in rows
            if r.granularity == "floorplan" and r.units_available
            and (r.plan_name or "").strip().lower() not in plans_with_units
        )
        total = len(unit_rows) + fp_only
        res.n_units_available = total if (unit_rows or res.n_rows_with_avail) else None

        if res.n_rows_with_rent and res.n_rows_with_avail:
            res.outcome = OUT_RENT_AVAIL
        elif res.n_rows_with_rent:
            res.outcome = OUT_RENT_ONLY
        elif res.n_rows_with_avail:
            res.outcome = OUT_AVAIL_ONLY
        elif any(r.bedrooms is not None or r.sqft is not None for r in rows):
            # Floor plan structure but no price and no count. Common where the
            # marketing site is a brochure and pricing lives only on a
            # denylisted leasing portal -- worth distinguishing from a miss.
            res.outcome = OUT_STRUCTURE
        else:
            res.outcome = OUT_NOTHING

        # Diagnostic: did we fail to find rent on a page that points its
        # pricing at a leasing engine we are not allowed to touch? This is the
        # single most useful number for judging the ceiling of the approach.
        if not res.n_rows_with_rent and res.leasing_engines_referenced:
            res.rent_behind_denylisted_portal = True

        self._store_meta(res, meta)
        return self._finish(res, rows)

    def _store_meta(self, res: SiteResult, meta: dict):
        rec = {"marketing_url": res.marketing_url, "name": res.name,
               "operator": res.operator, "collected_at": res.collected_at}
        # RULE 6 -- no image fields are carried through
        rec.update({k: v for k, v in meta.items() if "image" not in k and "logo" not in k})
        with open(os.path.join(self.out_dir, "properties.jsonl"), "a") as f:
            f.write(json.dumps(rec) + "\n")

    def _finish(self, res: SiteResult, rows: list[Listing]):
        with open(self.results_path, "a") as f:
            f.write(json.dumps(res.dict()) + "\n")
        if rows:
            with open(self.listings_path, "a") as f:
                for r in rows:
                    f.write(json.dumps(r.dict()) + "\n")
        return res
