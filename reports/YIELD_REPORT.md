# Yield Report

_Generated 2026-10-01 18:33 UTC_

**965 sites attempted.** 276 produced usable rent and/or availability (**28.6%**).

## Outcome by site

| Code | Outcome | Sites | % of attempted |
|---|---|---|---|
| C_nothing | Nothing extracted | 324 | 33.6% |
| A_rent_and_availability | Clean rent + availability | 224 | 23.2% |
| F_dropped_terms_prohibit | Dropped - terms prohibit automated access | 111 | 11.5% |
| D_skipped_vendor_hosted | Skipped - vendor-hosted marketing site | 104 | 10.8% |
| G_unreachable | Unreachable / dead URL | 73 | 7.6% |
| B1_rent_only | Rent only (no availability count) | 48 | 5.0% |
| E_bot_blocked | Bot-blocked | 44 | 4.6% |
| B3_structure_only | Floor plan structure only (no rent, no availability) | 32 | 3.3% |
| B2_availability_only | Availability only (no rent) | 4 | 0.4% |
| H_denylisted | Denylisted domain (never requested) | 1 | 0.1% |

## Records collected

| Measure | Count |
|---|---|
| Listing rows | 8,890 |
| Unit-level rows (individual apartments) | 6,808 |
| Rows with an asking rent | 6,947 |
| Rows with an availability count | 8,032 |
| Rows with lat/long | 7,085 |
| Distinct properties with data | 280 |
| Sites where rent sits behind a denylisted leasing portal | 116 |

## Yield by candidate source

A single blended number is misleading. The OpenStreetMap sweep pulls in senior-living campuses, housing co-ops and other non-market-rate entities, so it should not be judged against the same bar as a curated operator portfolio.

| Source | Attempted | Clean rent+avail | Usable (any) | Usable % | Structure only | Nothing | Blocked | Vendor-hosted | Terms-dropped | Dead URL |
|---|---|---|---|---|---|---|---|---|---|---|
| operator portfolios | 430 | 168 | 185 | 43.0% | 25 | 113 | 15 | 53 | 30 | 9 |
| operator-sitemap | 226 | 25 | 35 | 15.5% | 0 | 116 | 0 | 0 | 66 | 9 |
| OpenStreetMap | 212 | 23 | 37 | 17.5% | 5 | 71 | 17 | 17 | 13 | 51 |
| browser-portfolio | 58 | 4 | 8 | 13.8% | 1 | 6 | 9 | 31 | 0 | 3 |
| Boulder rental licenses (CC0) + browser search | 37 | 3 | 10 | 27.0% | 1 | 18 | 3 | 2 | 2 | 1 |
| Boulder rental licenses (CC0) + web search | 2 | 1 | 1 | 50.0% | 0 | 0 | 0 | 1 | 0 | 0 |

## Collected rent distribution (sanity check)

If these medians did not resemble the Denver market, the extraction would be wrong somewhere.

| Bedrooms | n | Min | p25 | Median | p75 | Max |
|---|---|---|---|---|---|---|
| Studio | 557 | $940 | $1,439 | $1,648 | $1,819 | $6,300 |
| 1 bd | 3,345 | $899 | $1,698 | $1,892 | $2,216 | $15,713 |
| 2 bd | 2,404 | $1,312 | $2,159 | $2,472 | $2,919 | $17,860 |
| 3 bd | 463 | $1,527 | $2,603 | $2,825 | $3,238 | $14,612 |
| 4 bd | 49 | $2,014 | $3,143 | $3,178 | $3,190 | $3,692 |
