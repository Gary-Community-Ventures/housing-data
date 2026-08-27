# Yield Report

_Generated 2026-08-27 18:36 UTC_

**965 sites attempted.** 265 produced usable rent and/or availability (**27.5%**).

## Outcome by site

| Code | Outcome | Sites | % of attempted |
|---|---|---|---|
| C_nothing | Nothing extracted | 325 | 33.7% |
| A_rent_and_availability | Clean rent + availability | 221 | 22.9% |
| D_skipped_vendor_hosted | Skipped - vendor-hosted marketing site | 116 | 12.0% |
| F_dropped_terms_prohibit | Dropped - terms prohibit automated access | 112 | 11.6% |
| G_unreachable | Unreachable / dead URL | 74 | 7.7% |
| B1_rent_only | Rent only (no availability count) | 42 | 4.4% |
| E_bot_blocked | Bot-blocked | 37 | 3.8% |
| B3_structure_only | Floor plan structure only (no rent, no availability) | 35 | 3.6% |
| B2_availability_only | Availability only (no rent) | 2 | 0.2% |
| H_denylisted | Denylisted domain (never requested) | 1 | 0.1% |

## Records collected

| Measure | Count |
|---|---|
| Listing rows | 7,896 |
| Unit-level rows (individual apartments) | 5,786 |
| Rows with an asking rent | 6,272 |
| Rows with an availability count | 7,059 |
| Rows with lat/long | 6,504 |
| Distinct properties with data | 274 |
| Sites where rent sits behind a denylisted leasing portal | 115 |

## Yield by candidate source

A single blended number is misleading. The OpenStreetMap sweep pulls in senior-living campuses, housing co-ops and other non-market-rate entities, so it should not be judged against the same bar as a curated operator portfolio.

| Source | Attempted | Clean rent+avail | Usable (any) | Usable % | Structure only | Nothing | Blocked | Vendor-hosted | Terms-dropped | Dead URL |
|---|---|---|---|---|---|---|---|---|---|---|
| operator portfolios | 430 | 167 | 178 | 41.4% | 26 | 114 | 17 | 52 | 30 | 13 |
| operator-sitemap | 226 | 24 | 35 | 15.5% | 0 | 117 | 0 | 0 | 67 | 7 |
| OpenStreetMap | 212 | 22 | 34 | 16.0% | 7 | 72 | 15 | 20 | 13 | 50 |
| browser-portfolio | 58 | 4 | 7 | 12.1% | 1 | 4 | 2 | 41 | 0 | 3 |
| Boulder rental licenses (CC0) + browser search | 37 | 3 | 10 | 27.0% | 1 | 18 | 3 | 2 | 2 | 1 |
| Boulder rental licenses (CC0) + web search | 2 | 1 | 1 | 50.0% | 0 | 0 | 0 | 1 | 0 | 0 |

## Collected rent distribution (sanity check)

If these medians did not resemble the Denver market, the extraction would be wrong somewhere.

| Bedrooms | n | Min | p25 | Median | p75 | Max |
|---|---|---|---|---|---|---|
| Studio | 581 | $942 | $1,479 | $1,673 | $1,868 | $6,300 |
| 1 bd | 3,035 | $1,050 | $1,708 | $1,930 | $2,242 | $9,581 |
| 2 bd | 2,082 | $1,346 | $2,203 | $2,551 | $2,973 | $17,860 |
| 3 bd | 384 | $1,936 | $2,653 | $2,895 | $3,187 | $14,652 |
| 4 bd | 52 | $2,591 | $3,153 | $3,163 | $3,190 | $3,455 |
| 6 bd | 2 | $5,556 | $5,556 | $5,556 | $5,556 | $5,556 |
