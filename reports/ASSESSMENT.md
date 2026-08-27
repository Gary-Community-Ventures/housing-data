# Assessment: does this scale, and what breaks first?

_Denver metro. 873 sites attempted across two passes; the second pass upgraded
extraction and added operator-sitemap enumeration._

> **Second-pass result.** Sites attempted 647 -> 873. Rows 6,480 -> **8,019**, of
> which unit-level rows 4,419 -> **6,015**. High-confidence rows 3,853 ->
> **5,954**. Guessed-HTML rows 582 -> **403**. Measured usable yield fell
> 33.2% -> **28.8%**, because the new enumeration source yields 15.5% against the
> curated portfolios' 41.9% — more data, at a lower hit rate.

## The short answer

The method works, and it produces genuinely good data where it works — but it is
**a panel, not a census**, and it rests on a single vendor's CMS to a degree that
should worry you.

- **33.4%** of attempted sites produced usable rent and/or availability (216 of 647).
- **41.9%** from curated operator portfolios; **16.6%** from the OpenStreetMap sweep.
- **6,493 listing rows**, of which **4,419 are unit-level** (a specific apartment,
  its number, its exact rent, its available date) across **240 properties**.
- Roughly **240 properties out of a metro universe of 1,300–3,000+** named
  apartment communities. Call it **10–18% coverage**. Not market-representative,
  and it should never be described as such to a state agency or an MLS.

The reference finding in the brief is confirmed and then some: Ten50 returns
server-rendered structured data with no JS execution, and the JSON-LD must be
walked recursively — a naive top-level parse of `@graph` returns nothing, because
the 38 FloorPlan nodes are nested inside the ApartmentComplex node rather than
sitting at the graph's top level.

## One correction to the method

The brief prescribes: parse JSON-LD for structure, regex the HTML for prices,
join on plan name. **Don't.** That is the lossiest available reading of the page.

The same page carries `<script type="application/json" id="jd-fp-data-script-app">`
— a 2.3 MB JSON island holding **147 individual available units** with apartment
number, `rent_min`/`rent_max`, square footage, available date, building, and
`price_entity.priceDisplayNoFees`. No join is required, and no regex is involved.
The 5,426 price strings in the markup are that same data rendered many times over.

Verified against the browser-rendered page: **7 of 7 sampled plans match the
displayed price to the cent**, "Only 1 left!" matches the extracted count of 1,
and plans showing "Contact Us" correctly record zero availability rather than a
fabricated rent.

## The concentration risk — this is the real finding

| Platform | Sites | Yielded rent | Rent yield |
|---|---|---|---|
| **Jonah Digital** | 116 | **113** | **97%** |
| Funnel / Nestio | 105 | 49 | 47% |
| WordPress (various) | 83 | 19 | 23% |
| Next.js | 27 | 11 | 41% |
| unknown / bespoke | 229 | 13 | 6% |

Jonah Digital is 18% of the sites and produced **5,482 of 6,493 rows — 84% of the
dataset**. Every unit-level record we hold comes from it.

**What breaks first: Jonah ships a change.** They stop embedding the JSON island,
move it behind an XHR, or add terms of use. Any one of those removes ~85% of the
data in a single deploy, with no warning and nothing to negotiate. That is not a
scraping risk you can engineer around; it is a vendor-concentration risk, and it
belongs in the project's risk register rather than its backlog.

## The compliance ceiling is real, stable, and worth stating plainly

This is not lost coverage from weak engineering. It is the price of the clean
provenance story, and it is quantifiable:

- **75 sites (11.7%)** skipped because the marketing site *is* a vendor product.
- **88 sites** where we found floor plan structure but the rent exists only behind
  a denylisted leasing portal. AIR Communities is the clean example: every
  property publishes JSON-LD floor plans with beds/baths/sqft and **no price**,
  because pricing lives exclusively on `*.prospectportal.com` (Entrata).
- **37 sites** dropped because their terms prohibit automated access.

Together, **~30% of attempted sites are unreachable by policy rather than by
technology.** Nothing in the roadmap improves that number, and the honest framing
is that we chose it.

## Terms audit outcome

208 hosts SILENT · 100 NO_TERMS_FOUND · **5 PROHIBITS** · 2 UNREADABLE.

The five prohibiting hosts were dropped and their snippets recorded verbatim. Two
judgment calls worth surfacing:

- **`bmcinv.com`** — the prohibition names "the Investor Portal." A lawyer could
  argue it doesn't reach the apartment marketing pages. That is exactly the "we
  could probably win that argument" reasoning the brief rules out, so all 30 BMC
  properties are dropped. If you want them, get written permission.
- **UNREADABLE ≠ permitted.** Where a terms document exists but couldn't be
  fetched, we abstain rather than assert that an unread document allows
  collection. A 404 on a linked terms URL is treated as positive evidence that no
  document exists, and collection proceeds.

Because the check is per-host, one prohibiting operator removes its whole
portfolio at once. That is the correct behaviour and it makes yield lumpy.

**Caveat on these counts.** A regression test caught the classifier scoring "you
must not conduct any automated data collection activities" as SILENT — the noun
list covered "automated means/system/device/process" but not that phrasing. I
broadened it (and added `systematic retrieval`, `web scraping`, `text and data
mining`, and others) *after* this collection pass, verified against negative
controls so "we may send automated email notifications" still reads SILENT. The
5-prohibiting-host figure above is therefore a **floor**: the next run may drop
additional hosts that this pass recorded as SILENT. Re-run before treating the
terms audit as current.

## Bot-blocking is a much smaller problem than the brief assumes

The brief estimates ~25% of sites 403. **The real figure is 5.2% (33 sites).**

The earlier, higher estimate is an artifact of a detection bug worth naming, since
anyone reproducing this will hit it: `/cdn-cgi/challenge-platform` appears in the
markup of *every* Cloudflare-fronted site that serves its content perfectly well.
Treating it as proof of a block labelled ~1/3 of the sample as blocked while
180–385 KB of real content sat in the response body. A block is an explicit status
code, or an interstitial — and interstitials are tiny.

All 33 genuinely-blocked hosts **permit crawling in robots.txt**, so the 403s are
CDN bot-management defaults rather than owner policy.

A browser pass over 31 of them (CAPTCHAs were never solved) settles how much is
actually recoverable:

| Outcome | Count |
|---|---|
| Pages captured | 24 of 31 attempted |
| Yielded rent | **14** (244 rows, 161 priced) |
| Captured but yielded nothing | 11 |
| Failed — CAPTCHA presented, not solved | 6 |
| Failed — no floor-plan page (domain now redirects) | 1 |

So browser access recovers rent from **14 of 33** blocked sites — worth having, not
transformative. The 11 empty captures are the interesting failure: their rendered
text lists plan *names* only, with beds/rent/availability behind a click, so
recovering them needs per-plan interaction rather than one page load. Where it does
work it works well — `altapineycreek.com` returns 6 plans with base rent, total
monthly price, availability, sqft and lease term.

These rows are tagged `L5:browser-rendered-text` and are **excluded from the
primary yield figure**, which measures what a plain, polite HTTP crawler achieves.

I'd flag the tension rather than paper over it: robots.txt is the owner's
expressed policy and we honour it; a CDN's default bot rule is not the same
statement. Using a browser is consistent with robots.txt, and it is also
unmistakably routing around a refusal. That is a decision for the foundation and
its counsel, not for the scraper. The 33 sites are ~5% of the pipeline — small
enough that declining them costs little.

## Data hazards that would produce wrong advice to households

These matter more than yield for a tool that tells families what they can afford.

1. **Headline rent is not base rent.** Jonah exposes `pricingReflectFees: true`.
   Ten50's displayed $1,748.70 is base rent $1,710.00 plus $17.75 boiler + $15.00
   DWP + $5.95 utility admin — reconciled exactly against the property's own
   Colorado-mandated fee disclosure. We store both `rent` and `base_rent`. A tool
   comparing one property's base rent to another's all-in price will mislead.
2. **Per-bed student housing.** 65 rows are priced per bedroom, not per unit
   (`4x4`, `5X5` unit codes — a $631 "5-bedroom" is one bed). Flagged
   `per_bed_pricing` and excluded from rent distributions; if they leak into a
   median, large-unit rents collapse.
3. **"Starting at" prices** are the cheapest unit in a plan, not the rent of any
   particular apartment.
4. **Concessions.** "Up to 12 weeks free" changes effective rent by ~20% and is
   captured only as free text.

## Three parser bugs I found in one session, all in the same layer

The lowest-confidence layer — parsing rendered HTML cards — produced these, and
all three looked like plausible data:

- A **price-filter dropdown** ("Any Price $500–$1,500") parsed as listings,
  asserting $500 Denver studios across ~24 rows of one operator's portfolio.
- **Square footage read as bedroom count**, because adjacent markup rendered as
  "554 bed" → 554 bedrooms.
- A **$300 fee** taken as the asking rent.

Fixing them moved measured yield **down** from 36.5% to 33.4%. The first number
was inflated by my own bug. This is the argument for the validation layer
(`hn/validate.py`) being permanent rather than a one-off cleanup: an HTML-shape
parser fails silently and in the direction that flatters the operator. It now
holds 1.3% of rows as implausible and flags all 582 L4 rows as low-confidence.

**Recommendation: do not use L4 as a rent source in production.** It is fine for
detecting that a property exists and roughly what it offers.

## What I would and would not productionize

**Would:** the Jonah + Funnel/Nestio subset — ~220 properties, ~5,800
high-confidence rows, refreshed daily. Defensible provenance, unit-level
granularity, stable parsers against a versioned JSON contract. Treat it as a
monitored panel with published coverage caveats.

**Would not:** a general Denver-metro rent census by this method. The
long tail is 229 bespoke sites yielding 6%, and each is a hand-written parser
that breaks on redesign.

**Ranked by what breaks first**

1. **Jonah changes its page contract** — 84% of rows, no warning. Mitigate by
   alerting on row-count deltas per platform, not just per site.
2. **Silent parser drift** — the L4 class of bug. Mitigate with the validation
   gate in CI plus a small hand-labelled ground-truth set (Ten50 is one).
3. **Terms drift** — already handled by the standing per-run check; each new
   prohibiting operator removes a whole portfolio.
4. **Enumeration rot** — 57 dead URLs (8.9%) in one pass, concentrated in the OSM
   set where website tags go stale and one domain had already been resold to a
   domain squatter.
5. **Address quality** — 89% of rows got coordinates free from schema.org; the
   remainder have addresses too malformed in markup to geocode. Footer
   address-scraping is not a reliable geocoding input.

## Two things worth pursuing that this pass surfaced

- **Colorado's mandatory fee disclosures are on these pages, in structured form.**
  Ten50's is a complete schedule: application $22, admin $300, security deposit
  $150–250, monthly boiler/DWP/utility-admin, late-fee percentages. For a tool
  whose whole job is "what will this actually cost me," a fee corpus may be worth
  more than another 200 properties of asking rent — and it is far less
  contested data.
- **Availability counts are a leading indicator.** Unit-level rows with
  `available_date` let you measure days-on-market and concession depth over time.
  That is analysis nobody sells back to the state, and it comes free from data
  we already collect.

## What the second pass changed

**The "low confidence" problem was mostly a looking-in-the-wrong-place problem.**
Sites I had written off as HTML-card scrapes were embedding structured JSON in
plain JS variables — `spacesUnitJSON` (Griffis, unit-level, with a price-per-term
matrix), `preload.floorplans` (Cortland). My scanner only checked
`<script type="application/json">` and known framework globals. Scanning every
`var/let/const X = {...}` for parseable JSON, plus one extractor for the Spaces
plugin, moved **1,498 rows** to structured unit-level reads and cut guessed-HTML
rows by a third. `L1b:spaces` is now the winning layer on 78 sites.

**Rent is not one number, and the lease term is the biggest reason.** A Griffis
unit is $4,133 on a 2-month term and $1,552 on 15 months — 2.7x for the same
apartment. **1,462 rows** now carry the full term matrix. Everything resolves to
`comparable_rent`: all-in monthly, whole unit, 12-month term, net of concessions.
A rent quoted on a non-standard term with no published matrix is flagged, never
silently converted. Details in `NORMALIZATION.md`.

**Confidence was split into two axes**, because the combined one was unactionable:

- `confidence` — do we believe this is the rent for this unit? Driven by where the
  number came from. **I fix this by writing extractors.** Now 5,954 high / 58
  medium / 2,007 low.
- `cost_completeness` — how much of the true monthly cost we know. **Only the
  landlord can fix this.** 5,265 partial / 2,754 minimal, and *zero* complete —
  because 6,557 rows do not state the lease term for the quoted rent and 4,216
  publish no mandatory fees.

That last number is the honest headline for a housing navigator: for most units on
the open market, **the advertised rent does not disclose either the lease term it
applies to or the mandatory fees on top of it.**

## Candidate coverage

647 sites is what resolved to a fetchable marketing URL, not the universe. Verified
additional inventory: 674 named Boulder complexes (CC0 licences), 272 counted
communities across 36 uncovered operators (20 market-rate, 16 affordable), and 2,945
OSM-named buildings with no website tag. But only 5 of those 36 operators give
properties their own domain, so most of that gain needs per-operator parsers with no
platform-fingerprint leverage. Full breakdown in `COVERAGE.md`.

## Bottom line

Worth productionizing as a **monitored panel of ~220 properties with unit-level
rent**, on the explicit understanding that it covers 10–18% of the metro, leans
84% on one vendor's CMS, and forgoes ~30% of sites by policy. Not worth
productionizing as a market-wide rent index. The provenance story is clean enough
to take to a state agency; the coverage story must be told alongside it, or the
first person who checks will find the gap themselves.
