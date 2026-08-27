"""
Rent normalization: make numbers from different sites actually comparable.

Raw asking rents are not comparable across properties, for four independent
reasons found in this dataset:

  1. LEASE TERM. A Griffis unit is $4,133 on a 2-month term and $1,552 on 15
     months -- a 2.7x spread for the same apartment. A rent without its term
     means nothing.
  2. FEE INCLUSION. Some sites quote base rent, others quote base plus all
     mandatory monthly fees (Ten50: $1,710 base -> $1,748.70 all-in).
  3. RENT BASIS. Student housing quotes PER BED. A "$631 five-bedroom" is one
     bed; the unit is ~$3,155.
  4. CONCESSIONS. "Up to 12 weeks free" moves effective rent ~19% on a 12-month
     lease.

Everything is normalized to one canonical figure -- `comparable_rent`: the
all-in monthly cost of the WHOLE UNIT on a 12-MONTH term, net of concessions --
plus per-bed and per-square-foot views. Every derivation records how it was
reached and what was assumed, so a number is never silently invented.
"""
from __future__ import annotations
import json, os, re, sys, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- rent basis -------------------------------------------------------------
PER_BED_PAT = re.compile(r"\b(\d)\s*x\s*\1\b", re.I)
PER_BED_WORDS = re.compile(r"per\s*(?:bed|person|bedroom)|by\s+the\s+bed|"
                           r"individual\s+lease|per-bed", re.I)

# --- concessions ------------------------------------------------------------
WEEKS_FREE = re.compile(r"(?:up\s+to\s+)?(\d+(?:\.\d)?)\s*weeks?\s+free", re.I)
MONTHS_FREE = re.compile(r"(?:up\s+to\s+)?(\d+(?:\.\d)?)\s*months?\s+free", re.I)
DOLLARS_OFF = re.compile(r"\$\s*([\d,]{3,6})\s*(?:off|credit)", re.I)

# --- income restriction (to EXCLUDE from a market-rate comparison set) ------
RESTRICTION_SIGNALS = re.compile(
    r"\b\d{2,3}\s*%\s*(?:of\s*)?ami\b|area\s+median\s+income|income[-\s]restricted|"
    r"income\s+qualified|income\s+limits|lihtc|tax\s+credit|section\s*8|"
    r"housing\s+choice\s+voucher|affordable\s+housing\s+program|"
    r"rent\s+and\s+income\s+limits|set[-\s]aside\s+unit", re.I)

STANDARD_TERM = 12


def detect_basis(row: dict) -> tuple[str, list[str]]:
    """per_unit or per_bed, with the evidence."""
    why = []
    label = " ".join(str(row.get(k) or "") for k in ("plan_name", "unit_number"))
    blob = " ".join(str(row.get(k) or "") for k in
                    ("plan_name", "unit_number", "specials", "property_name"))
    if PER_BED_PAT.search(label):
        why.append("NxN unit code (beds x baths) -- student-housing per-bed lease")
        return "per_bed", why
    if PER_BED_WORDS.search(blob):
        why.append("explicit per-bed/per-person wording")
        return "per_bed", why
    # A large unit priced far below any plausible whole-unit rent is per-bed.
    bd, rent = row.get("bedrooms"), row.get("rent")
    if bd and rent and bd >= 3 and rent < 900:
        why.append(f"{bd:g}bd at ${rent:,.0f} is implausible per-unit; inferred per-bed")
        return "per_bed", why
    return "per_unit", why


def _matrix_all_in(row: dict) -> list[dict]:
    """Term matrix expressed on the SAME basis as the quoted rent.

    Jonah's matrix carries BASE rents while its quoted price is ALL-IN. Mixing
    them erases the mandatory fee. Where the extractor already resolved this it
    stamps `rent_all_in`; otherwise the fee measured at the quoted term is added
    here. Mandatory monthly fees do not vary with lease length.
    """
    matrix = row.get("rent_term_matrix") or []
    if not matrix:
        return []
    quoted, base = row.get("rent"), row.get("base_rent")
    fee = (round(quoted - base, 2)
           if (quoted and base and quoted > base) else 0.0)
    out = []
    for e in matrix:
        if not isinstance(e, dict) or e.get("term_months") is None:
            continue
        if e.get("rent_all_in") is not None:
            rent = e["rent_all_in"]
        else:
            rent = round((e.get("rent") or 0) + fee, 2) or None
        if rent:
            out.append({**e, "rent": rent})
    return out


def term_rent(row: dict) -> tuple[float | None, int | None, str]:
    """Rent for the standard 12-month term, from the matrix when available."""
    matrix = _matrix_all_in(row)
    if matrix:
        exact = next((m for m in matrix if m.get("term_months") == STANDARD_TERM), None)
        if exact:
            return exact["rent"], STANDARD_TERM, "matrix-exact-12mo"
        longer = [m for m in matrix if (m.get("term_months") or 0) >= 9]
        if longer:
            best = min(longer, key=lambda m: abs(m["term_months"] - STANDARD_TERM))
            return best["rent"], best["term_months"], f"matrix-nearest-{best['term_months']}mo"
    t = row.get("lease_term_months")
    if row.get("rent") is None:
        return None, t, "no-rent"
    if t == STANDARD_TERM:
        return row["rent"], STANDARD_TERM, "quoted-at-12mo"
    if t:
        return row["rent"], t, f"quoted-at-{t}mo-not-normalized"
    return row["rent"], None, "term-unknown-assumed-standard"


UPPER_BOUND = re.compile(r"up\s+to", re.I)
SELECT_ONLY = re.compile(r"select\s+(?:homes|units|apartments|floor\s*plans)", re.I)


def concessions(row: dict) -> tuple[float, str | None, bool]:
    """Months of free rent implied by the advertised special.

    Returns (months, text, is_upper_bound). 62% of concessions in this data are
    phrased "up to N weeks free" and 20% apply only to "select homes", so the
    figure is a CEILING for an unknown subset of units -- not a discount any
    given household will actually receive.
    """
    txt = " ".join(str(row.get(k) or "") for k in
                   ("specials", "property_specials", "available_display"))
    if not txt.strip():
        return 0.0, None, False
    bound = bool(UPPER_BOUND.search(txt) or SELECT_ONLY.search(txt))
    m = MONTHS_FREE.search(txt)
    if m:
        return float(m.group(1)), m.group(0), bound
    m = WEEKS_FREE.search(txt)
    if m:
        return round(float(m.group(1)) / 4.345, 2), m.group(0), bound
    return 0.0, None, False


def normalize(row: dict) -> dict:
    notes = []
    bd = row.get("bedrooms")
    sq = row.get("sqft")

    basis, why = detect_basis(row)
    notes += why
    row["rent_basis"] = basis

    rent12, term_used, how = term_rent(row)
    row["rent_12mo"] = rent12
    row["rent_12mo_method"] = how
    if how.endswith("not-normalized"):
        notes.append(f"rent is quoted for a {term_used}-month term and could not be "
                     "converted to 12-month equivalent (no term matrix published)")
    if how == "term-unknown-assumed-standard":
        notes.append("lease term not published; treated as the standard term")

    # whole-unit figure
    per_unit = rent12
    if basis == "per_bed" and rent12 is not None:
        if bd and bd >= 1:
            per_unit = round(rent12 * bd, 2)
            notes.append(f"per-bed rent scaled to whole unit by {bd:g} bedrooms (derived)")
        else:
            per_unit = None
            notes.append("per-bed rent but bedroom count unknown; whole-unit rent not derivable")
    row["rent_per_unit_month"] = per_unit

    # occupancy: a studio still houses someone
    occ = max(bd, 1) if bd is not None else None
    row["rent_per_bed_month"] = round(per_unit / occ, 2) if (per_unit and occ) else None
    row["rent_per_sqft_month"] = round(per_unit / sq, 3) if (per_unit and sq) else None

    # base vs all-in
    base, allin = None, None
    if row.get("rent_includes_fees") and row.get("base_rent"):
        allin, base = per_unit, row["base_rent"]
        if basis == "per_bed" and bd and bd >= 1:
            base = round(base * bd, 2)
    elif row.get("base_rent"):
        base = row["base_rent"]
        allin = per_unit
    else:
        base = per_unit
        notes.append("mandatory monthly fees not published; base and all-in treated as equal "
                     "(all-in is therefore a FLOOR, not the true cost)")
        allin = per_unit
    row["base_rent_month"] = base
    row["all_in_rent_month"] = allin
    row["mandatory_fees_monthly"] = (round(allin - base, 2)
                                     if (allin and base and allin > base) else None)

    # concessions -> effective rent, kept OUT of the headline number
    months_free, conc_text, conc_bound = concessions(row)
    row["concession_months_free"] = months_free or None
    row["concession_text"] = conc_text
    row["concession_is_upper_bound"] = conc_bound or None
    if allin and months_free:
        row["effective_rent_12mo"] = round(
            allin * (STANDARD_TERM - months_free) / STANDARD_TERM, 2)
        if conc_bound:
            notes.append(f"advertised concession ({conc_text}) is an UPPER BOUND and may "
                         "apply only to selected units; effective rent is a best case")
        else:
            notes.append(f"effective rent nets out {months_free} month(s) free "
                         "over a 12-month lease")
    else:
        row["effective_rent_12mo"] = allin

    # The headline comparison number deliberately EXCLUDES concessions.
    # 62% of concessions are phrased "up to" and 20% are limited to "select
    # homes", so folding them in produced a discount most households will not
    # get. The concession-adjusted figure is published alongside, labelled.
    row["comparable_rent"] = allin
    row["comparable_basis"] = ("all-in monthly cost, whole unit, 12-month term, "
                               "before any advertised concession")
    row["comparable_rent_best_case"] = row["effective_rent_12mo"]

    # market-rate vs income-restricted
    hay = " ".join(str(row.get(k) or "") for k in
                   ("property_name", "plan_name", "specials", "unit_amenities"))
    hit = RESTRICTION_SIGNALS.search(hay)
    row["income_restricted"] = bool(hit)
    row["restriction_signal"] = hit.group(0) if hit else None
    row["market_rate"] = not bool(hit)

    # Two independent axes, deliberately kept apart.
    #
    # confidence      = do we believe this IS the rent for this unit?
    #                   driven by WHERE the number came from.
    # cost_completeness = how much of the true monthly cost we actually know.
    #
    # An earlier version folded them together, so "mandatory fees not
    # published" dragged a perfectly-extracted unit-level row down to medium.
    # That made confidence unactionable: the fix for a missing fee schedule is
    # the landlord publishing one, whereas the fix for a guessed HTML number is
    # writing a better extractor.
    method = row.get("extraction_method") or ""
    structured = method.startswith(("L1", "L2", "L5"))

    conf_reasons = []
    if not structured:
        conf_reasons.append("parsed from rendered HTML rather than a structured source")
    if row.get("comparable_rent") is None:
        conf_reasons.append("no comparable rent could be derived")
    if row.get("plausible") is False:
        conf_reasons.append("failed plausibility validation")
    if how.endswith("not-normalized"):
        conf_reasons.append("quoted for a non-standard lease term and not convertible")
    if basis == "per_bed" and per_unit is not None:
        conf_reasons.append("whole-unit rent derived from a per-bed quote")

    blocking = [r for r in conf_reasons
                if "rendered HTML" in r or "no comparable rent" in r
                or "plausibility" in r]
    if blocking:
        row["confidence"] = "low"
    elif conf_reasons:
        row["confidence"] = "medium"
    else:
        row["confidence"] = "high"
    row["confidence_reasons"] = conf_reasons

    gaps = []
    if row.get("mandatory_fees_monthly") is None:
        gaps.append("mandatory monthly fees not published")
    if not row.get("rent_term_matrix"):
        gaps.append("no lease-term price matrix published")
    if row.get("lease_term_months") is None:
        gaps.append("lease term for the quoted rent not stated")
    if not row.get("fee_items"):
        gaps.append("no itemised fee schedule")
    row["cost_completeness"] = ("complete" if not gaps else
                                "partial" if len(gaps) <= 2 else "minimal")
    row["cost_gaps"] = gaps

    row["normalization_notes"] = notes
    return row


def main(paths=("data/listings.jsonl", "data/listings_browser.jsonl")):
    stats = collections.Counter()
    for path in paths:
        if not os.path.exists(path):
            continue
        rows = [normalize(json.loads(l)) for l in open(path) if l.strip()]
        with open(path, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        for r in rows:
            stats[f"conf:{r['confidence']}"] += 1
            stats[f"basis:{r['rent_basis']}"] += 1
            if r.get("comparable_rent") is not None:
                stats["has_comparable_rent"] += 1
            if r.get("mandatory_fees_monthly"):
                stats["fees_known"] += 1
            if r.get("concession_months_free"):
                stats["has_concession"] += 1
            if r.get("income_restricted"):
                stats["income_restricted"] += 1
            if r.get("rent_term_matrix"):
                stats["term_matrix_published"] += 1
        print(f"  normalized {len(rows)} rows in {path}")
    print()
    for k in sorted(stats):
        print(f"  {k:28} {stats[k]}")
    return stats


if __name__ == "__main__":
    main()
