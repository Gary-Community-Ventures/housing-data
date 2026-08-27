#!/usr/bin/env python
"""
Regression tests for the collector.

The Ten50 case is hand-verified against the browser-rendered page (7 of 7 plans
matched to the cent), so it is the ground truth that guards every future parser
change. The rest of these encode bugs that actually shipped during development
and would otherwise silently return.

Run:  ./.venv/bin/python tests/test_reference.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hn.policy import is_denied, vendor_hosted_by_host
from hn.collect import looks_blocked
from hn.extract import extract_all, clean_name, fingerprint
from hn.terms import classify_terms_text
from hn.validate import validate

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "scratch", "ten50.html")

fails = []


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {name}")


print("denylist (RULE 1) ------------------------------------------")
for url, want in [
    ("https://securecafe.com/x", True),
    ("https://foo.securecafe.com/x", True),
    ("https://mine.prospectportal.com/", True),
    ("https://x.entrata.com/", True),
    ("https://entrata.net/", True),
    ("https://x.appfolio.com/listings/a", True),
    ("https://api.rentcafe.com/rentcafeapi.aspx", True),
    ("https://x.myresman.com/", True),
    ("https://app.meetelise.com/", True),
    # ILS aggregators are never fetched either
    ("https://www.apartments.com/denver-co/", True),
    ("https://www.apartmentguide.com/x", True),
    ("https://www.zillow.com/denver", True),
    # a normal property marketing site must pass
    ("https://liveatten50.com/floorplans/", False),
    ("https://www.altapineycreek.com/", False),
]:
    check(f"is_denied({url[:44]})", is_denied(url)[0], want)

print("\nblock detection -------------------------------------------")
# Cloudflare's passive beacon appears on pages that serve fine; a real block is
# a status code or a tiny interstitial.
check("200 + 385KB with cf beacon is NOT blocked",
      looks_blocked(200, "x" * 385_000 + "/cdn-cgi/challenge-platform"), False)
check("200 + big page with grecaptcha-badge is NOT blocked",
      looks_blocked(200, "x" * 100_000 + "grecaptcha-badge"), False)
check("403 IS blocked", looks_blocked(403, ""), True)
check("tiny interstitial IS blocked",
      looks_blocked(200, "Just a moment... cf_chl_opt"), True)

print("\nterms classifier (RULE 4) ---------------------------------")
check("robot/scraper prohibition",
      classify_terms_text("You agree not to use any robot, spider or scraper to "
                          "access the Site without our written permission.")[0],
      "PROHIBITS")
check("systematic data collection prohibition",
      classify_terms_text("You must not conduct any automated data collection "
                          "activities on this website without consent.")[0],
      "PROHIBITS")
check("ordinary terms are SILENT",
      classify_terms_text("These terms govern your use of the site. Disputes are "
                          "resolved in Denver County.")[0], "SILENT")
check("robots.txt mention alone is not a prohibition",
      classify_terms_text("Our robots.txt tells search engine crawlers which "
                          "pages to index.")[0], "SILENT")

print("\nname cleaning ---------------------------------------------")
check("strips SEO prefix", clean_name("1, 2, & 3-Bedroom Apartments | Cortland at Coalton"),
      "Cortland at Coalton")
check("keeps name, drops location", clean_name("Parc Mosaic Apartments - Boulder, CO"),
      "Parc Mosaic Apartments")
check("drops trailing city", clean_name("Ten50 | Apartments in Denver, CO"), "Ten50")
check("decodes entities", clean_name("1357 &amp; 1373 Cook"), "1357 & 1373 Cook")

print("\nvalidation ------------------------------------------------")
r = validate({"bedrooms": 554.0, "rent": 300.0, "sqft": None,
              "extraction_method": "L4:html-card-join", "plan_name": "554"})
check("sqft-as-bedrooms is rejected", r["bedrooms"], None)
check("row marked implausible", r["plausible"], False)
r2 = validate({"bedrooms": 5.0, "rent": 631.0, "sqft": 1701,
               "extraction_method": "L1:jonah-json-island",
               "plan_name": "5X5 E1", "unit_number": "5X5 E1 (1)"})
check("per-bed student pricing flagged", "per_bed_pricing" in r2["quality_flags"], True)

print("\nreference case: Ten50 (ground truth) ----------------------")
if not os.path.exists(FIXTURE):
    print("  SKIP  fixture scratch/ten50.html not present")
else:
    html = open(FIXTURE).read()
    fp = fingerprint(html)
    check("fingerprinted as Jonah Digital", fp["primary"], "Jonah Digital")
    # An outbound leasing link must NOT mark the marketing site vendor-hosted.
    check("not treated as vendor-hosted", fp["vendor_hosted"], None)
    check("leasing engine detected but not followed",
          "onlineleasing.realpage.com" in fp["leasing_engines_referenced"], True)

    ex = extract_all(html, "https://liveatten50.com/floorplans/")
    check("winning layer is the JSON island", ex["winning_layer"], "L1:jonah")
    check("row count", len(ex["rows"]), 162)
    check("priced rows", sum(1 for r in ex["rows"] if r.rent is not None), 147)
    check("unit-level rows", sum(1 for r in ex["rows"] if r.granularity == "unit"), 147)

    m = ex["meta"]
    check("property name", m["property_name"], "Ten50")
    check("street", m["street"], "1050 Broadway")
    check("city", m["city"], "Denver")
    check("has coordinates", m["lat"] is not None and m["lon"] is not None, True)

    # prices verified against the browser-rendered page, to the cent
    by_plan = {}
    for row in ex["rows"]:
        if row.rent is not None:
            by_plan.setdefault(row.plan_name, []).append(row.rent)
    for plan, (lo, hi) in {"E1": (1718.70, 1823.70), "E2": (1958.70, 2118.70),
                           "A6": (2308.70, 2338.70), "A0C": (1953.70, 1953.70),
                           "A0": (2338.70, 2373.70), "A1": (2458.70, 2618.70),
                           "A2A": (2478.70, 2853.70)}.items():
        rs = by_plan.get(plan, [])
        ok = bool(rs) and abs(min(rs) - lo) < 0.02 and abs(max(rs) - hi) < 0.02
        check(f"plan {plan} matches displayed {lo}-{hi}", ok, True)

    # base rent vs fee-inclusive rent must both survive
    e1 = [r for r in ex["rows"] if r.plan_name == "E1" and r.unit_number == "1009"]
    if e1:
        check("E1 #1009 fee-inclusive rent", e1[0].rent, 1748.70)
        check("E1 #1009 base rent", e1[0].base_rent, 1710.0)
        check("rent_includes_fees flagged", e1[0].rent_includes_fees, True)

    # RULE 6 -- no image data may survive extraction
    leaked = [k for r in ex["rows"] for k in r.dict()
              if "image" in k.lower() or "photo" in k.lower()]
    check("no image fields on listing rows", leaked, [])

print("\n" + "=" * 60)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("all checks passed")
