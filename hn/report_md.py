"""Render the data-driven deliverables (yield, platforms, terms) as markdown."""
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def tbl(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    return "\n".join(out)


def main(rep_path="reports/report.json", out_dir="reports"):
    r = json.load(open(rep_path))
    y, stamp = r["yield"], datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ---------------- yield ----------------
    m = [f"# Yield Report\n", f"_Generated {stamp}_\n",
         f"**{y['sites_attempted']} sites attempted.** "
         f"{y['usable_any_data']} produced usable rent and/or availability "
         f"(**{y['usable_pct']}%**).\n",
         "## Outcome by site\n",
         tbl(["Code", "Outcome", "Sites", "% of attempted"],
             [[b["code"], b["label"], b["n"], f"{b['pct']}%"] for b in y["buckets"] if b["n"]]),
         "\n## Records collected\n",
         tbl(["Measure", "Count"], [
             ["Listing rows", f"{y['listing_rows']:,}"],
             ["Unit-level rows (individual apartments)", f"{y['unit_level_rows']:,}"],
             ["Rows with an asking rent", f"{y['rows_with_rent']:,}"],
             ["Rows with an availability count", f"{y['rows_with_availability']:,}"],
             ["Rows with lat/long", f"{y['rows_with_geo']:,}"],
             ["Distinct properties with data", f"{y['distinct_properties_with_data']:,}"],
             ["Sites where rent sits behind a denylisted leasing portal",
              y.get("rent_behind_denylisted_portal", 0)],
         ]),
         "\n## Yield by candidate source\n",
         "A single blended number is misleading. The OpenStreetMap sweep pulls in "
         "senior-living campuses, housing co-ops and other non-market-rate entities, "
         "so it should not be judged against the same bar as a curated operator "
         "portfolio.\n",
         tbl(["Source", "Attempted", "Clean rent+avail", "Usable (any)", "Usable %",
              "Structure only", "Nothing", "Blocked", "Vendor-hosted", "Terms-dropped", "Dead URL"],
             [[x["source"], x["attempted"], x["clean_rent_and_availability"], x["usable_any"],
               f"{x['usable_pct']}%", x["structure_only"], x["nothing"], x["blocked"],
               x["vendor_hosted"], x["terms_dropped"], x["unreachable"]]
              for x in r["yield_by_source"]]),
         ]
    if r.get("rent_stats_by_bedrooms"):
        m += ["\n## Collected rent distribution (sanity check)\n",
              "If these medians did not resemble the Denver market, the extraction "
              "would be wrong somewhere.\n",
              tbl(["Bedrooms", "n", "Min", "p25", "Median", "p75", "Max"],
                  [[("Studio" if s["bedrooms"] == 0 else f"{s['bedrooms']:g} bd"), f"{s['n']:,}",
                    f"${s['min']:,.0f}", f"${s['p25']:,.0f}", f"${s['median']:,.0f}",
                    f"${s['p75']:,.0f}", f"${s['max']:,.0f}"] for s in r["rent_stats_by_bedrooms"]])]
    open(f"{out_dir}/YIELD_REPORT.md", "w").write("\n".join(m) + "\n")

    # ---------------- platforms ----------------
    p = [f"# Platform Fingerprint Breakdown\n", f"_Generated {stamp}_\n",
         "Which site builders expose structured rent and availability, measured by "
         "outcome per detected platform.\n",
         tbl(["Platform / builder", "Sites", "Yielded rent", "Yielded availability",
              "Structure only", "Nothing", "Blocked", "Rent behind portal", "Rows", "Rent yield"],
             [[x["platform"], x["sites"], x["with_rent"], x["with_avail"],
               x.get("structure_only", 0), x["nothing"], x["blocked"],
               x.get("portal_gated", 0), f"{x['rows']:,}", f"{x['usable_rate_pct']}%"]
              for x in r["platforms"]]),
         "\n## Which extraction layer won\n",
         tbl(["Layer", "Sites where it produced the best result"],
             sorted(r["winning_layers"].items(), key=lambda kv: -kv[1])),
         "\n**Layer definitions**\n",
         "- **L1** — platform-specific JSON island. Jonah Digital publishes a complete "
         "`<script type=\"application/json\" id=\"jd-fp-data-script-app\">` blob with one "
         "record per *available apartment*: unit number, exact rent, base rent, square "
         "footage, available date, building.\n"
         "- **L2** — generic framework/JSON island scan (`__NEXT_DATA__`, `__NUXT__`, "
         "any `application/json` script) matched heuristically on rent-ish + bed-ish keys.\n"
         "- **L3** — schema.org JSON-LD, walked recursively. Floor plan structure and "
         "availability counts; rarely carries rent.\n"
         "- **L4** — rendered-HTML card parse. Lowest confidence, used as a fallback.\n",
         ]
    open(f"{out_dir}/PLATFORM_FINGERPRINTS.md", "w").write("\n".join(p) + "\n")

    # ---------------- terms ----------------
    t = r["terms"]
    lines = [f"# Terms Audit Log\n", f"_Generated {stamp}_\n",
             f"{t['sites_checked']} distinct hosts checked this run. This check runs on "
             "**every** collection pass, not once: terms can be added at any time, and a "
             "site that begins prohibiting automated access is dropped on the next run "
             "with the reason recorded.\n",
             "## Verdicts\n",
             tbl(["Verdict", "Hosts"], sorted(t["verdicts"].items(), key=lambda kv: -kv[1])),
             "\n**Verdict meanings**\n",
             "- `PROHIBITS` — terms document found and it forbids automated access. Site dropped; no data retained.\n"
             "- `SILENT` — terms document found and read; contains no prohibition on automated access.\n"
             "- `NO_TERMS_FOUND` — no terms document discoverable from footer links or common paths (or the linked one is a dead 404).\n"
             "- `UNREADABLE` — a terms document may exist but could not be fetched. We do not assert that an unread document permits collection, so we abstain.\n"]
    if t["prohibiting_sites"]:
        lines += ["\n## Sites dropped — terms prohibit automated access\n"]
        for s in t["prohibiting_sites"]:
            lines.append(f"### `{s['site']}`\n")
            if s.get("terms_url"):
                lines.append(f"Terms document: {s['terms_url']}\n")
            for sn in s.get("snippets", []):
                lines.append(f"> {sn}\n")
    lines.append("\n**The prohibiting count is a floor, not a ceiling.** The classifier was "
                 "broadened after the last collection pass to catch phrasings such as "
                 "\"automated data collection\", \"systematic retrieval\" and \"text and data "
                 "mining\", so a re-run may drop hosts recorded here as SILENT. Re-run before "
                 "treating this audit as current.\n")
    lines.append("\nThe complete per-host log, with timestamps, is at `logs/terms_audit.jsonl` "
                 "and is browsable in the internal UI under **Terms Audit**.\n")
    open(f"{out_dir}/TERMS_AUDIT.md", "w").write("\n".join(lines) + "\n")

    # ---------------- normalization ----------------
    nz = r.get("normalization") or {}
    n = [f"# Rent Normalization & Confidence\n", f"_Generated {stamp}_\n",
         "Raw asking rents from different sites are not comparable. Four independent "
         "traps appear in this data, each of which produces wrong advice to a household "
         "if ignored.\n",
         tbl(["Trap", "Observed", "Handled by"], [
             ["Lease term", "A Griffis unit is $4,133 on a 2-month term and $1,552 on 15 months — 2.7x for the same apartment",
              "`rent_12mo`, `rent_term_matrix`, `rent_12mo_method`"],
             ["Fee inclusion", "Ten50 quotes $1,748.70 all-in; base rent is $1,710.00",
              "`base_rent_month`, `all_in_rent_month`, `mandatory_fees_monthly`"],
             ["Rent basis", "A \"$631 five-bedroom\" is one bed in a 5x5 student lease; the unit is ~$3,155",
              "`rent_basis`, `rent_per_unit_month`, `rent_per_bed_month`"],
             ["Concessions", "\"Up to 12 weeks free\" cuts effective rent ~19%",
              "`concession_months_free`, `effective_rent_12mo`"],
         ]),
         "\n## The one comparable number\n",
         "**`comparable_rent`** = all-in monthly cost, whole unit, 12-month term, net of "
         "concessions. Alongside it: `rent_per_bed_month` and `rent_per_sqft_month` for "
         "comparing across unit formats, and `market_rate` / `income_restricted` so a "
         "restricted unit never lands silently in a market-rate median.\n",
         "Nothing is assumed silently. `normalization_notes` records every derivation, and "
         "a rent quoted on a non-standard term with no published matrix is **flagged, not "
         "converted**.\n",
         "\n## Coverage of the normalized fields\n",
         tbl(["Measure", "Rows"], [
             ["Total rows", f"{nz.get('rows', 0):,}"],
             ["With a comparable rent", f"{nz.get('with_comparable_rent', 0):,}"],
             ["Lease-term price matrix published", f"{nz.get('term_matrix_published', 0):,}"],
             ["Mandatory monthly fees known", f"{nz.get('mandatory_fees_known', 0):,}"],
             ["Concession detected", f"{nz.get('with_concession', 0):,}"],
             ["Per-bed rent normalized to whole unit", f"{nz.get('per_bed_normalized', 0):,}"],
             ["Income-restricted (excluded from market-rate views)", f"{nz.get('income_restricted', 0):,}"],
         ]),
         "\n## Two confidence axes, kept apart\n",
         "- **`confidence`** — do we believe this is the rent for this unit? Driven by "
         "*where the number came from*. The fix is a better extractor.\n"
         "- **`cost_completeness`** — how much of the true monthly cost we know. The fix "
         "requires the landlord to publish a fee schedule.\n\n"
         "Folding these together made confidence unactionable: a perfectly extracted "
         "unit-level row was dragged to medium purely because its landlord publishes no "
         "fee schedule.\n",
         tbl(["confidence", "Rows"], sorted(
             (nz.get("confidence") or {}).items(), key=lambda kv: -(kv[1] or 0))),
         "",
         tbl(["cost_completeness", "Rows"], sorted(
             (nz.get("cost_completeness") or {}).items(), key=lambda kv: -(kv[1] or 0))),
         ]
    if nz.get("top_confidence_blockers"):
        n += ["\n## What is holding rows below high confidence\n",
              tbl(["Reason", "Rows"], list(nz["top_confidence_blockers"].items()))]
    if nz.get("top_cost_gaps"):
        n += ["\n## What cost information is missing\n",
              tbl(["Gap", "Rows"], list(nz["top_cost_gaps"].items()))]
    open(f"{out_dir}/NORMALIZATION.md", "w").write("\n".join(n) + "\n")

    print("wrote YIELD_REPORT.md, PLATFORM_FINGERPRINTS.md, TERMS_AUDIT.md, NORMALIZATION.md")


if __name__ == "__main__":
    main()
