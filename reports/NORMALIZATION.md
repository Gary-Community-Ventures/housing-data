# Rent Normalization & Confidence

_Generated 2026-10-01 18:33 UTC_

Raw asking rents from different sites are not comparable. Four independent traps appear in this data, each of which produces wrong advice to a household if ignored.

| Trap | Observed | Handled by |
|---|---|---|
| Lease term | A Griffis unit is $4,133 on a 2-month term and $1,552 on 15 months — 2.7x for the same apartment | `rent_12mo`, `rent_term_matrix`, `rent_12mo_method` |
| Fee inclusion | Ten50 quotes $1,748.70 all-in; base rent is $1,710.00 | `base_rent_month`, `all_in_rent_month`, `mandatory_fees_monthly` |
| Rent basis | A "$631 five-bedroom" is one bed in a 5x5 student lease; the unit is ~$3,155 | `rent_basis`, `rent_per_unit_month`, `rent_per_bed_month` |
| Concessions | "Up to 12 weeks free" cuts effective rent ~19% | `concession_months_free`, `effective_rent_12mo` |

## The one comparable number

**`comparable_rent`** = all-in monthly cost, whole unit, 12-month term, net of concessions. Alongside it: `rent_per_bed_month` and `rent_per_sqft_month` for comparing across unit formats, and `market_rate` / `income_restricted` so a restricted unit never lands silently in a market-rate median.

Nothing is assumed silently. `normalization_notes` records every derivation, and a rent quoted on a non-standard term with no published matrix is **flagged, not converted**.


## Coverage of the normalized fields

| Measure | Rows |
|---|---|
| Total rows | 8,890 |
| With a comparable rent | 6,947 |
| Lease-term price matrix published | 3,966 |
| Mandatory monthly fees known | 4,119 |
| Concession detected | 1,899 |
| Per-bed rent normalized to whole unit | 127 |
| Income-restricted (excluded from market-rate views) | 3 |

## Two confidence axes, kept apart

- **`confidence`** — do we believe this is the rent for this unit? Driven by *where the number came from*. The fix is a better extractor.
- **`cost_completeness`** — how much of the true monthly cost we know. The fix requires the landlord to publish a fee schedule.

Folding these together made confidence unactionable: a perfectly extracted unit-level row was dragged to medium purely because its landlord publishes no fee schedule.

| confidence | Rows |
|---|---|
| high | 6271 |
| low | 2425 |
| medium | 194 |

| cost_completeness | Rows |
|---|---|
| partial | 3752 |
| minimal | 2906 |
| complete | 2232 |

## What is holding rows below high confidence

| Reason | Rows |
|---|---|
| no comparable rent could be derived | 1943 |
| parsed from rendered HTML rather than a structured source | 795 |
| whole-unit rent derived from a per-bed quote | 123 |
| quoted for a non-standard lease term and not convertible | 73 |
| failed plausibility validation | 6 |

## What cost information is missing

| Gap | Rows |
|---|---|
| no lease-term price matrix published | 4924 |
| mandatory monthly fees not published | 4771 |
| no itemised fee schedule | 4364 |
| lease term for the quoted rent not stated | 4269 |
