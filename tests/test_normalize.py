#!/usr/bin/env python
"""
Tests for rent normalization.

Each case is a real comparability trap found in the collected data. If any of
these regress, the tool starts giving households numbers that cannot be compared
to each other.

Run:  ./.venv/bin/python tests/test_normalize.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hn.normalize import normalize, detect_basis, term_rent, concessions

fails = []


def check(name, got, want):
    ok = (abs(got - want) < 0.02) if isinstance(want, float) and isinstance(got, (int, float)) else got == want
    if not ok:
        fails.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {name}")


print("lease-term normalization ----------------------------------")
# Griffis: same unit, 2-month term $4,133 vs 15-month $1,552
griffis = {
    "rent": 1893.0, "bedrooms": 1.0, "sqft": 700, "lease_term_months": 12,
    "extraction_method": "L1b:spaces-unit-json", "unit_number": "304382",
    "rent_term_matrix": [{"term_months": 2, "rent": 4133.0},
                         {"term_months": 12, "rent": 1893.0},
                         {"term_months": 15, "rent": 1552.0}],
}
r = normalize(dict(griffis))
check("picks the 12-month term, not the cheapest", r["rent_12mo"], 1893.0)
check("method records how", r["rent_12mo_method"], "matrix-exact-12mo")
check("confidence high (extraction is sound)", r["confidence"], "high")
check("cost completeness partial (no fee schedule)", r["cost_completeness"], "partial")

# no 12-month offered -> nearest term >= 9 months, and it is disclosed
near = dict(griffis)
near["rent_term_matrix"] = [{"term_months": 2, "rent": 4000.0},
                            {"term_months": 10, "rent": 1700.0}]
r = normalize(near)
check("falls back to nearest long term", r["rent_12mo"], 1700.0)
check("discloses the fallback", r["rent_12mo_method"], "matrix-nearest-10mo")

# a rent quoted at a short term with no matrix must NOT be silently treated as 12mo
short = {"rent": 3200.0, "bedrooms": 1.0, "lease_term_months": 3,
         "extraction_method": "L1:jonah-json-island"}
r = normalize(short)
check("short-term quote flagged, not converted", r["rent_12mo_method"],
      "quoted-at-3mo-not-normalized")
check("confidence drops to medium", r["confidence"], "medium")

print("\nper-bed vs per-unit --------------------------------------")
# Union on Elizabeth: 5x5, $631 is ONE BED
perbed = {"rent": 631.0, "bedrooms": 5.0, "sqft": 1701, "lease_term_months": 12,
          "plan_name": "5X5 E1", "unit_number": "5X5 E1 (1)",
          "extraction_method": "L1:jonah-json-island"}
r = normalize(perbed)
check("detects per-bed basis", r["rent_basis"], "per_bed")
check("scales to whole unit", r["rent_per_unit_month"], 3155.0)
check("per-bed figure preserved", r["rent_per_bed_month"], 631.0)
check("derivation disclosed in confidence", any("per-bed" in x for x in r["confidence_reasons"]), True)

normal = {"rent": 2000.0, "bedrooms": 2.0, "sqft": 1000, "lease_term_months": 12,
          "plan_name": "B1", "extraction_method": "L1:jonah-json-island"}
r = normalize(normal)
check("normal unit stays per_unit", r["rent_basis"], "per_unit")
check("per-bed view for a 2bd", r["rent_per_bed_month"], 1000.0)
check("studio counts as one occupant",
      normalize({"rent": 1500.0, "bedrooms": 0.0, "sqft": 500,
                 "lease_term_months": 12,
                 "extraction_method": "L1:jonah"})["rent_per_bed_month"], 1500.0)

print("\nbase rent vs all-in --------------------------------------")
# Ten50 #1009: $1,710 base + mandatory fees = $1,748.70
ten50 = {"rent": 1748.70, "base_rent": 1710.0, "rent_includes_fees": True,
         "bedrooms": 0.0, "sqft": 474, "lease_term_months": 12,
         "plan_name": "E1", "unit_number": "1009",
         "extraction_method": "L1:jonah-json-island"}
r = normalize(ten50)
check("all-in preserved", r["all_in_rent_month"], 1748.70)
check("base preserved", r["base_rent_month"], 1710.0)
check("mandatory fees derived", r["mandatory_fees_monthly"], 38.70)
check("comparable uses all-in", r["comparable_rent"], 1748.70)

nofees = {"rent": 2000.0, "bedrooms": 1.0, "lease_term_months": 12,
          "extraction_method": "L1:jonah"}
r = normalize(nofees)
check("unknown fees -> all-in is a floor, and says so",
      any("FLOOR" in x for x in r["normalization_notes"]), True)
check("and it shows up as a cost gap, not low confidence",
      any("fees not published" in g for g in r["cost_gaps"]), True)

print("\nconcessions ----------------------------------------------")
check("12 weeks free -> months", concessions({"specials": "Up to 12 weeks free"})[0], 2.76)
check("'up to' marked as an upper bound", concessions({"specials": "Up to 12 weeks free"})[2], True)
check("'select homes' marked as an upper bound",
      concessions({"specials": "8 weeks free on select homes"})[2], True)
check("unconditional offer is not an upper bound",
      concessions({"specials": "8 Weeks Free"})[2], False)
check("2 months free", concessions({"specials": "2 months free rent!"})[0], 2.0)
check("no special", concessions({"specials": ""})[0], 0.0)
conc = {"rent": 2000.0, "bedrooms": 1.0, "lease_term_months": 12,
        "property_specials": "Up to 12 weeks free on select homes",
        "extraction_method": "L1:jonah"}
r = normalize(conc)
check("effective rent nets the concession", r["effective_rent_12mo"], 1540.0)
check("headline comparable EXCLUDES an 'up to' concession", r["comparable_rent"], 2000.0)
check("best case published separately", r["comparable_rent_best_case"], 1540.0)
check("upper bound flagged", r["concession_is_upper_bound"], True)

print("\nmarket rate vs income restricted -------------------------")
r = normalize({"rent": 900.0, "bedrooms": 1.0, "lease_term_months": 12,
               "property_name": "Somewhere Apartments",
               "specials": "Units restricted to households at 60% AMI",
               "extraction_method": "L1:jonah"})
check("income restriction detected", r["income_restricted"], True)
check("excluded from market rate", r["market_rate"], False)
r = normalize({"rent": 2000.0, "bedrooms": 1.0, "lease_term_months": 12,
               "property_name": "Market Place", "extraction_method": "L1:jonah"})
check("ordinary unit is market rate", r["market_rate"], True)

print("\nconfidence rules -----------------------------------------")
r = normalize({"rent": 1800.0, "bedrooms": 1.0, "sqft": 700,
               "lease_term_months": 12, "extraction_method": "L4:html-card-join"})
check("HTML-parsed row cannot be high confidence", r["confidence"], "low")
r = normalize({"rent": None, "bedrooms": 1.0, "extraction_method": "L1:jonah"})
check("no comparable rent -> low", r["confidence"], "low")
r = normalize({"rent": 1800.0, "bedrooms": 1.0, "sqft": 700, "lease_term_months": 12,
               "plausible": False, "extraction_method": "L1:jonah"})
check("implausible row -> low", r["confidence"], "low")

print("\n" + "=" * 58)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("all normalization checks passed")
