"""
RULE 4 — per-site terms check, logged, on every run.

This is a standing check, not a one-time audit. A site that was silent last
week can add prohibiting terms tomorrow; when it does, we drop it and record
why. The classifier is deliberately conservative: anything that looks like a
prohibition of automated access is treated as PROHIBITS, and the matching
sentence is stored verbatim so a human can audit the call.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .policy import Fetcher, _host

# Link text / href hints that indicate a terms document
TERMS_LINK_PAT = re.compile(
    r"terms\s*(of\s*(use|service)|and\s*conditions|&\s*conditions)?|"
    r"legal\s*(notice|disclaimer)?|conditions\s+of\s+use|website\s+terms|user\s+agreement",
    re.I,
)
# Capped deliberately: probing a dozen speculative paths per site is both slow
# and impolite. Terms are normally linked from the footer; these four cover the
# common cases when they are not.
COMMON_TERMS_PATHS = ["/terms-of-use/", "/terms/", "/terms-and-conditions/", "/legal/"]

# Automated-access nouns
AUTOMATION_TERMS = [
    "scrape", "scraping", "scraper", "screen scrape", "screen-scrape",
    "data mining", "data-mining", "datamining", "spider", "crawler", "crawl",
    "robot", "bot ", "bots", "automated means", "automated system",
    "automated device", "automated process", "automated script",
    "automated software", "automatic device", "harvest", "harvesting",
    "web crawler", "extraction software", "indexing", "deep-link",
    "artificial intelligence", "machine learning",
    # Added after a regression test caught "you must not conduct any automated
    # data collection activities" being classified SILENT: the noun list only
    # had "automated means/system/device/process/script/software", so common
    # real-world phrasings slipped through. Broadening errs toward dropping
    # sites, which is the safe direction here.
    "automated data collection", "automated collection", "automated retrieval",
    "automated extraction", "automated query", "automated queries",
    "automated tool", "automated agent", "automated access", "automated script",
    "automatically collect", "automatically extract", "automatically retrieve",
    "systematic retrieval", "systematic access", "systematic collection",
    "systematic downloading", "systematic extraction", "screen scraping",
    "screen-scraping", "web scraping", "data scraping", "text and data mining",
]
# Prohibition verbs that must appear near an automation noun
PROHIBITION_CUES = [
    "prohibit", "not permitted", "may not", "shall not", "must not",
    "agree not to", "refrain from", "without prior written", "unauthorized",
    "forbid", "restrict", "no right", "is not allowed", "are not allowed",
    "expressly prohibited", "you will not", "do not", "cannot", "prevent",
]
# Phrases that mean the automation noun is being *permitted* / merely mentioned
BENIGN_CUES = [
    "search engine", "publicly available search", "robots.txt", "we use cookies",
    "google analytics",
]


@dataclass
class TermsRecord:
    site: str
    homepage: str
    checked_at: str
    terms_url: str | None = None
    terms_found: bool = False
    discovery: str = ""            # how we found it: link-text | common-path | none
    verdict: str = "NO_TERMS_FOUND"  # PROHIBITS | SILENT | NO_TERMS_FOUND | UNREACHABLE
    matched_snippets: list = field(default_factory=list)
    automation_mentions: int = 0
    notes: str = ""
    collect_allowed: bool = True

    def dict(self):
        return asdict(self)


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    return re.split(r"(?<=[.;:!?])\s+", text)


# Stems that open a list of prohibitions. Terms are overwhelmingly written as
# "You agree not to:" followed by bullets, so the operative verb sits in a
# DIFFERENT sentence from the automation noun. Requiring both in one sentence
# produced false SILENT verdicts on exactly the most common drafting style --
# RealPage's "Use any robot, spider, crawler ... to scrape" bullet was scored
# SILENT because "You agree not to" was in the preceding stem.
PROHIBITION_STEMS = [
    "you agree not to", "you may not", "you shall not", "you must not",
    "you will not", "agree that you will not", "prohibited from",
    "you are prohibited", "the following is prohibited", "restrictions on use",
    "prohibited uses", "prohibited conduct", "acceptable use",
    "you shall refrain", "refrain from", "without our prior written",
    "you must refrain", "unauthorized use", "you undertake not to",
    "may not, and will not", "shall not, and will not",
]
# Some prohibitions target harvesting USERS' PERSONAL DATA ("harvest, collect or
# gather user data without the user's consent"; "collect information about
# others, including e-mail addresses") rather than site content. We collect no
# personal data at all, so those clauses do not reach this activity -- but that
# is a judgment call about scope, so it is surfaced for human review rather than
# silently decided. Distinguishing this is reading the clause, not arguing about
# its enforceability.
PERSONAL_DATA_SCOPE = [
    "user data", "personal data", "personal information", "e-mail address",
    "email address", "information about others", "other users", "about our users",
    "personally identifiable", "contact information of",
]
CONTENT_SCOPE = [
    "website", "web site", "content", "the site", "this site", "the service",
    "listings", "pages", "materials", "database", "any portion",
]

# How far a stem's authority reaches. Prohibition lists run long, so this is
# generous; the snippet is always recorded so a human can check the call.
STEM_WINDOW = 2500


def classify_terms_text(text: str) -> tuple[str, list[str], int]:
    """Return (verdict, snippets, automation_mention_count)."""
    flat = re.sub(r"\s+", " ", text)
    low = flat.lower()
    mentions = sum(low.count(t) for t in AUTOMATION_TERMS)
    hits = []

    # (a) same-sentence prohibitions
    for sent in _sentences(flat):
        s = sent.lower()[:1200]
        if not any(t in s for t in AUTOMATION_TERMS):
            continue
        if not any(c in s for c in PROHIBITION_CUES):
            continue
        if any(b in s for b in BENIGN_CUES) and "prohibit" not in s and "may not" not in s:
            continue
        hits.append({"stem": "(same sentence)", "term": next(
            (t for t in AUTOMATION_TERMS if t in s), "?"),
            "text": sent.strip()[:420], "scope": _scope(sent)})

    # (b) automation noun inside the scope of a preceding prohibition stem
    for m in re.finditer("|".join(re.escape(x) for x in PROHIBITION_STEMS), low):
        window = low[m.end():m.end() + STEM_WINDOW]
        for t in AUTOMATION_TERMS:
            idx = window.find(t)
            if idx == -1:
                continue
            # centre the snippet on the matched term, not on the stem -- an
            # earlier version showed the preceding bullet and read as a false
            # positive when the verdict was actually right.
            seg = flat[m.end() + max(0, idx - 130): m.end() + idx + 220].strip()
            if any(b in seg.lower() for b in BENIGN_CUES):
                continue
            stem = flat[m.start():m.end()].strip()
            abs_i = m.end() + idx
            hits.append({"stem": stem, "term": t, "text": seg[:420],
                         "scope": _scope(_clause_around(flat, abs_i, len(t)))})
            break

    uniq, seen = [], set()
    for h in hits:
        k = re.sub(r"[^a-z0-9]", "", h["text"].lower())[:120]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(h)

    if not uniq:
        return "SILENT", [], mentions
    # If EVERY hit is scoped to users' personal data, this clause does not reach
    # collecting public listing content. Flagged, not silently cleared.
    if all(h["scope"] == "personal-data" for h in uniq):
        return "PROHIBITS_PERSONAL_DATA_ONLY", uniq[:6], mentions
    return "PROHIBITS", uniq[:6], mentions


def _clause_around(flat: str, idx: int, tlen: int) -> str:
    """The single clause containing the matched term.

    Scoping on a wide window let CONTENT_SCOPE words leak in from ADJACENT
    bullets -- "use this Site in conjunction with sending spam; harvest user
    data" scored as site-content because of the neighbouring clause. Clause
    boundaries are the semicolons and full stops that separate list items.
    """
    start = max((flat.rfind(c, 0, idx) for c in ";.\u2022\n"), default=-1)
    end_candidates = [flat.find(c, idx + tlen) for c in ";.\u2022\n"]
    end_candidates = [e for e in end_candidates if e != -1]
    end = min(end_candidates) if end_candidates else len(flat)
    return flat[start + 1:end].strip()


def _scope(seg: str) -> str:
    low = seg.lower()
    personal = any(x in low for x in PERSONAL_DATA_SCOPE)
    content = any(x in low for x in CONTENT_SCOPE)
    if personal and not content:
        return "personal-data"
    if content:
        return "site-content"
    return "unclear"


class TermsAuditor:
    def __init__(self, fetcher: Fetcher, log_path="logs/terms_audit.jsonl"):
        self.f = fetcher
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        self._cache: dict[str, TermsRecord] = {}

    def check(self, homepage: str, homepage_html: str | None = None) -> TermsRecord:
        site = _host(homepage)
        if site in self._cache:
            return self._cache[site]
        rec = TermsRecord(
            site=site, homepage=homepage,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

        html = homepage_html
        if html is None:
            r = self.f.get(homepage)
            if not r.ok:
                rec.verdict = "UNREACHABLE"
                rec.notes = f"homepage fetch: {r.outcome} {r.detail}"
                rec.collect_allowed = False
                return self._finish(rec)
            html = r.text

        terms_url, how = self._discover(homepage, html)
        rec.terms_url, rec.discovery = terms_url, how

        if not terms_url:
            rec.terms_found = False
            rec.verdict = "NO_TERMS_FOUND"
            rec.notes = ("No terms-of-use document discoverable from homepage links "
                         "or common paths. Collection proceeds; re-checked every run.")
            rec.collect_allowed = True
            return self._finish(rec)

        tr = self.f.get(terms_url)
        if not tr.ok:
            rec.terms_found = False
            # A 404/410 on the linked terms URL is positive evidence that no
            # terms document exists (a dead footer link), so collection may
            # proceed. Any other failure means a document may exist that we
            # could not read -- and we will not assert that an unread document
            # permits collection, so we abstain.
            if tr.status in (404, 410):
                rec.verdict = "NO_TERMS_FOUND"
                rec.notes = (f"Terms link present but dead ({tr.status} at {terms_url}). "
                             "Treated as no terms document; re-checked every run.")
                rec.collect_allowed = True
            else:
                rec.verdict = "UNREADABLE"
                rec.notes = f"terms fetch failed: {tr.outcome} {tr.detail}. Abstaining."
                rec.collect_allowed = False
            return self._finish(rec)

        rec.terms_found = True
        soup = BeautifulSoup(tr.text, "lxml")
        for bad in soup(["script", "style", "noscript"]):
            bad.decompose()
        body = soup.get_text(" ", strip=True)
        verdict, snips, mentions = classify_terms_text(body)
        rec.verdict = verdict
        rec.matched_snippets = snips
        rec.automation_mentions = mentions
        rec.collect_allowed = verdict not in ("PROHIBITS",)
        if verdict == "PROHIBITS_PERSONAL_DATA_ONLY":
            rec.notes = ("REVIEW: prohibition appears scoped to users' personal data, "
                         "not site content. Collection proceeds; flagged for human review.")
        if verdict == "PROHIBITS":
            rec.notes = "DROPPED: terms prohibit automated access."
        else:
            rec.notes = f"Terms present, no automated-access prohibition found ({mentions} incidental mentions)."
        return self._finish(rec)

    def _discover(self, homepage: str, html: str) -> tuple[str | None, str]:
        soup = BeautifulSoup(html, "lxml")
        base_host = _host(homepage)
        best = None
        for a in soup.find_all("a", href=True):
            txt = (a.get_text(" ", strip=True) or "")[:80]
            href = a["href"]
            hay = f"{txt} {href}"
            if not TERMS_LINK_PAT.search(hay):
                continue
            if re.search(r"privacy|accessib|sitemap|cookie", hay, re.I) and not re.search(r"terms", hay, re.I):
                continue
            full = urljoin(homepage, href)
            if _host(full) != base_host:
                # off-site terms (often the vendor's). Record it — it still binds
                # the page if the page is the vendor's product.
                best = best or full
                continue
            return full, "link-text"
        if best:
            return best, "link-text-offsite"
        # try common paths
        for p in COMMON_TERMS_PATHS:
            cand = urljoin(homepage, p)
            r = self.f.get(cand)
            if r.ok and len(r.text) > 2000:
                low = r.text.lower()
                if "terms" in low or "conditions of use" in low:
                    return r.final_url or cand, "common-path"
        return None, "none"

    def _finish(self, rec: TermsRecord) -> TermsRecord:
        self._cache[rec.site] = rec
        with open(self.log_path, "a") as f:
            f.write(json.dumps(rec.dict()) + "\n")
        return rec
