# Data dictionary — `data/listings.jsonl`

One JSON object per line. **One row per available apartment** where the source
exposes unit-level data (`granularity: "unit"`), otherwise one row per floor
plan (`granularity: "floorplan"`).

Start here: if you want one number to compare across properties, use
**`comparable_rent`** filtered to `market_rate: true` and
`confidence: "high"`. Everything else below explains how that number was made
and what it hides.

## Identity & location

| Field | Type | Meaning |
|---|---|---|
| `property_name` | str | Property name, cleaned of SEO decoration ("1, 2 & 3-Bedroom Apartments \| X" → "X") |
| `operator` | str? | Managing/owning operator, from the candidate list |
| `street`, `city`, `state`, `postal_code` | str? | From schema.org where published, else validated footer parse. `city` is checked against a Front Range municipality list; unverifiable values move to `city_unverified` / `street_unverified` rather than being stored as fact |
| `lat`, `lon` | float? | schema.org geo where published (≈89% of rows), else US Census geocoder (`geocode_source` set) |
| `source_url` | str | The exact page the row was extracted from |
| `collected_at` | ISO 8601 | Collection timestamp (UTC) |

## The unit

| Field | Type | Meaning |
|---|---|---|
| `granularity` | `unit` \| `floorplan` | Whether this row is a specific apartment or a plan summary |
| `unit_number` | str? | Apartment number (unit rows) |
| `plan_name`, `plan_type` | str? | Floor plan name / marketing type ("Studio") |
| `bedrooms` | float? | 0 = studio |
| `bathrooms` | float? | Half baths as .5 |
| `sqft` | int? | |
| `building` | str? | |
| `units_available` | int? | Plan-level availability count. Unit rows ARE one available unit each |
| `available_date` | date? | First availability |
| `available_display` | str? | The site's own wording ("Available Now") |
| `unit_amenities` | list | Unit-level tags (e.g. "renovated") |

## Rent — raw observations

| Field | Type | Meaning |
|---|---|---|
| `rent` | float? | The advertised price, as displayed. **Do not compare across properties** — basis, term, and fee inclusion vary |
| `rent_min`, `rent_max` | float? | Advertised range where shown |
| `base_rent` | float? | Rent excluding mandatory monthly fees, where disclosed |
| `rent_includes_fees` | bool? | Whether `rent` is fee-inclusive (Colorado HB25-1090 "Total Monthly Leasing Price" pattern) |
| `lease_term_months` | int? | **The lease term the advertised price applies to.** 44% of matrix-publishing units advertise a non-12-month term |
| `rent_term_matrix` | list | Price by lease term: `{term_months, rent, rent_base?, rent_all_in?, advertised_best?}`. `rent` is always the all-in figure; Jonah's raw matrix is base-rent and is adjusted using the fee measured at the quoted term |
| `fee_items` | list | Itemized fee schedule where published: `{label, amount}` |
| `specials`, `property_specials` | str? | Concession text, unit- and property-level |

## Rent — normalized (all derived; see `normalization_notes`)

| Field | Meaning |
|---|---|
| `rent_basis` | `per_unit` or `per_bed`. Student housing quotes per bed ("5x5" codes); a $631 "5-bedroom" is one bed |
| `rent_12mo` / `rent_12mo_method` | Rent at the standard 12-month term, and exactly how it was derived (`matrix-exact-12mo`, `matrix-nearest-Nmo`, `quoted-at-Nmo-not-normalized`, `term-unknown-assumed-standard`). Non-standard terms without a matrix are **flagged, never converted** |
| `rent_per_unit_month` | Whole-unit rent (per-bed quotes scaled by bedroom count, disclosed) |
| `base_rent_month`, `all_in_rent_month`, `mandatory_fees_monthly` | Base vs fee-inclusive monthly cost; fee is the difference where both are known |
| `concession_months_free`, `concession_text`, `concession_is_upper_bound` | Advertised free rent. 62% are "up to" phrasing and 20% "select homes" — a ceiling, not a promise |
| `effective_rent_12mo` | All-in rent netting the advertised concession over 12 months (best case) |
| **`comparable_rent`** | **The canonical comparison figure: all-in monthly cost, whole unit, 12-month term, BEFORE concessions** |
| `comparable_rent_best_case` | Same, concession-adjusted |
| `comparable_basis` | Human-readable statement of the above |
| `rent_per_bed_month`, `rent_per_sqft_month` | Cross-format views (studio counts as 1 occupant) |

## Market-rate classification

| Field | Meaning |
|---|---|
| `market_rate` / `income_restricted` | AMI/LIHTC/Section-8 signals detected in text → excluded from market-rate views. `restriction_signal` holds the matched phrase |

## Quality — two independent axes

| Field | Meaning |
|---|---|
| `confidence` | `high`/`medium`/`low` — **do we believe this is the rent for this unit?** Driven by extraction source (structured JSON vs guessed HTML). Fix = better extractor. `confidence_reasons` lists why |
| `cost_completeness` | `complete`/`partial`/`minimal` — **how much of the true monthly cost is known.** `cost_gaps` lists what's missing (fees unpublished, term unstated). Fix = landlord discloses more |
| `plausible` / `quality_flags` | Sanity gate (`hn/validate.py`): impossible bedrooms, sub-$500 "rents", per-bed pricing, rent/sqft outliers. Nothing is deleted; rows are flagged |
| `extraction_method` | Which layer produced the row: `L1:jonah-json-island` (unit-level, highest confidence) · `L1b:spaces-unit-json` · `L2:json-island` · `L3:jsonld-graph-walk` · `L4:html-card-join` (lowest — not a production rent source) · `L5:browser-rendered-text` |
| `platform` | Detected site builder (Jonah Digital, Funnel/Nestio, …) |
| `normalization_notes` | Every assumption made deriving the normalized fields, in prose |

## Companion files

- `data/site_results.jsonl` — one row per site attempted: outcome code (A/B/C/D/E/F/G/H), platform fingerprint, terms verdict, layer scores
- `data/properties.jsonl` — property-level metadata (amenities, walk score, phone, office hours, pet policy)
- `logs/terms_audit.jsonl` — per-host terms verdict with timestamp and verbatim prohibition snippets (versioned; this is a compliance deliverable)
- `data/history/<date>/` — gzipped daily snapshots; `reports/timeseries.json` — derived events (listed / unlisted / rent_change)
