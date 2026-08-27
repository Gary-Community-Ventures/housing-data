"""
Plausibility validation over collected rows.

The collector is optimistic by design -- it will take a number that looks like
rent from rendered markup when nothing better exists. That is the right trade
for coverage and the wrong trade for trust, so every row is scored here and
anything implausible is flagged rather than silently shipped.

Flags are additive metadata; nothing is deleted. A housing navigator can then
choose to show only `plausible` rows while an analyst can still see the rest.
"""
from __future__ import annotations
import json, os, re, sys, collections

BED_MAX = 8
RENT_FLOOR = 500          # below this, almost always a fee or deposit
RENT_CEILING = 25000
PPSF_MIN, PPSF_MAX = 0.40, 14.0

# "4x4", "5X5", "3x3" -- student-housing notation for beds x baths, where the
# advertised price is PER BED, not for the whole unit. Mixing these into a
# whole-unit rent distribution understates large-unit rents badly.
PER_BED_PAT = re.compile(r"\b(\d)\s*x\s*\1\b", re.I)


def validate(r: dict) -> dict:
    flags = []
    bd, rent, sqft = r.get("bedrooms"), r.get("rent"), r.get("sqft")

    if bd is not None and not (0 <= bd <= BED_MAX):
        flags.append(f"bedrooms_implausible({bd:g})")
        r["bedrooms_raw"] = bd
        r["bedrooms"] = None
        bd = None

    if rent is not None:
        if rent < RENT_FLOOR:
            flags.append(f"rent_below_floor({rent:g})")
        elif rent > RENT_CEILING:
            flags.append(f"rent_above_ceiling({rent:g})")

    if rent and sqft:
        ppsf = rent / sqft
        if not (PPSF_MIN <= ppsf <= PPSF_MAX):
            flags.append(f"rent_per_sqft_outlier({ppsf:.2f})")

    label = f"{r.get('plan_name') or ''} {r.get('unit_number') or ''}"
    if PER_BED_PAT.search(label):
        flags.append("per_bed_pricing")

    # A purely numeric plan name is only a square-footage misparse when it
    # EQUALS the square footage -- that was the original Viceroy bug ("554" as
    # both plan name and size). Flagging every numeric plan name caught 201
    # legitimate apartment numbers (Boston Lofts plans "903", "806" with real,
    # different sqft) and wrongly marked them implausible.
    pn = str(r.get("plan_name") or "").strip()
    if pn and re.fullmatch(r"\d{2,5}", pn):
        if sqft is not None and pn == str(sqft):
            flags.append("plan_name_equals_sqft")
        else:
            # looks like a unit designation, not a plan name -- informational
            flags.append("plan_name_is_unit_number")
            if not r.get("unit_number"):
                r["unit_number"] = pn

    if r.get("extraction_method", "").startswith("L4"):
        flags.append("low_confidence_layer")

    r["quality_flags"] = flags
    blocking = [f for f in flags
                if f.startswith(("bedrooms_implausible", "rent_below_floor",
                                 "rent_above_ceiling", "rent_per_sqft_outlier",
                                 "plan_name_equals_sqft"))]
    r["plausible"] = not blocking
    return r


def main(path="data/listings.jsonl"):
    rows = [validate(json.loads(l)) for l in open(path) if l.strip()]
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    c = collections.Counter(f.split("(")[0] for r in rows for f in r["quality_flags"])
    n_bad = sum(1 for r in rows if not r["plausible"])
    print(f"validated {len(rows)} rows | implausible: {n_bad} ({100*n_bad/len(rows):.1f}%)")
    for k, v in c.most_common():
        print(f"  {k:34} {v}")
    return rows


if __name__ == "__main__":
    for path in ("data/listings.jsonl", "data/listings_browser.jsonl"):
        if os.path.exists(path):
            print(f"== {path}")
            main(path)
