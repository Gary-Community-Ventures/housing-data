# What the advertised rent doesn't tell you

_Measured across 180 Denver-metro apartment sites that produced data, Aug 2026._

Three separate things move the real monthly cost away from the advertised rent.
We can measure all three, and the industry discloses them in almost exactly
inverse proportion to how much they matter.

## The three distortions, by size

| Distortion | Typical size | Worst observed | Sites disclosing it |
|---|---|---|---|
| **Concession** ("up to 12 weeks free") | **−23%** of rent, median **−$423/mo** | −25% | free text only, never structured |
| **Lease term** | **44%** of units are advertised at a term that is *not* 12 months; taking a standard 12-month lease costs a **median +13%** where it costs more at all | **+58%** | **51.7%** state a term; **37.8%** publish the matrix |
| **Mandatory monthly fees** | **+2.17%** of base rent, median **+$49/mo** (~$589/yr) | +10.6%, +$149/mo | **54–61%** |

**The industry has thoroughly disclosed the smallest of the three.** Mandatory
fees move the number ~2% and are itemised on 60.6% of sites. Lease term can move
it far more and is stated on 51.7%. Concessions move it ~23% and exist only as
marketing prose.

### Correction to an earlier version of this report

An earlier pass reported lease-term disclosure at **8.9%** of sites and matrices at
**2.2%**. Both were wrong, and the cause was our own extractor, not the market:
the Jonah Digital platform publishes the quoted term in `price_entity.term` and a
full matrix in `lease_terms`, and the parser looked for neither. Correct figures
are **51.7%** and **37.8%**. A second bug in the same area mixed price bases --
Jonah's matrix carries BASE rents while its quoted price is ALL-IN, so comparing
them silently erased the mandatory fee. Both are fixed and covered by tests.

The corrected picture is *less* damning of landlords and *more* interesting:
term-based pricing is widely disclosed in machine-readable form. Nobody
aggregates it.

## Disclosure combinations

Of the 180 sites that produced data:

| | Sites | Share |
|---|---|---|
| Discloses **both** fee-inclusive total **and** the lease term it applies to | **89** | **49.4%** |
| Fees only — total is honest, term unstated | 20 | 11.1% |
| Lease term only — term stated, fees not | 4 | 2.2% |
| Neither | 67 | 37.2% |

About half of sites disclose both. The other half leaves a household unable to see
either what the rent includes or which lease length it buys.

## The finding that actually matters: the advertised price is often not a 12-month price

Across **3,517 units** that publish both a term matrix and the term their headline
price applies to:

| Term the advertised price applies to | Units | Share |
|---|---|---|
| 12 months | 1,962 | 55.8% |
| 15 months | 514 | 14.6% |
| 18 months | 320 | 9.1% |
| 13 months | 276 | 7.8% |
| 14 months | 218 | 6.2% |
| 10-11 months | 112 | 3.2% |
| other | 115 | 3.3% |

**44.2% of units advertise a price for something other than a 12-month lease.**

Of those, **41% cost more on a 12-month term than the advertised figure** — a
median **+13%**, p90 **+19.5%**, max **+58.3%**. One verified example: a unit
advertised at $1,455.06 all-in on a 15-month term costs **$2,053.06 on a 12-month
term — a 41% premium** for the standard lease.

**This is dispersion, not a uniform downward bias.** The median premium across all
non-12-month units is −0.2%; the mean is +4.6%. So the correct claim is *not*
"advertised rents understate the market by X%". It is: **for a large minority of
units the advertised price does not describe a standard lease, and the household
that wants one pays materially more with no way to see it coming.** An earlier
draft of this report over-claimed a systematic downward bias; the data does not
support that.

## Who discloses what, by platform

Disclosure is a property of the *software vendor*, not of the landlord.

| Platform | Sites | Base rent split out | Itemised fees | Lease term | Term matrix |
|---|---|---|---|---|---|
| Jonah Digital | 103 | 97 | 98 | **0** | **0** |
| Wood Partners family (browser-only) | 15 | 12 | 0 | **12** | 0 |
| Spaces plugin (Griffis) | 4 | 0 | 0 | 4 | **4** |
| WordPress (various) | 12 | 0 | 0 | 0 | 0 |
| Funnel / Nestio | 4 | 0 | 0 | 0 | 0 |
| ActiveBuilding CMS | 4 | 0 | 0 | 0 | 0 |
| unknown / bespoke | 35 | 0 | 0 | 0 | 0 |

Jonah publishes an excellent fee schedule and **never** a lease term. Spaces
publishes a full 14-term price matrix and **never** a fee. Nobody built both.
A landlord's cost transparency is essentially decided by which CMS they bought.

## How everyone else handles this

### Fees: partially solved, and only because the law forced it

Colorado **HB25-1090, "Protections Against Deceptive Pricing Practices"** (signed
21 Apr 2025, **effective 1 Jan 2026**) requires a landlord to disclose the **total
price** as a single prominent number — in larger type than any component figure —
covering all mandatory fees except government charges and directly-billed
utilities. It also bans some fees outright (common-area utilities, pest control,
property-tax passthroughs) and is enforced through the Colorado Consumer
Protection Act. That statute is almost certainly why the "Total Monthly Leasing
Price" pattern with a dated fee schedule appears at all.

Federally, the **FTC's Junk Fees Rule (16 CFR Part 464, eff. May 2025) explicitly
excludes long-term rental housing** — it reaches live-event ticketing and
short-term lodging only. The FTC opened a **separate rental-housing ANPRM in March
2026**. The July 2023 White House push produced **voluntary** commitments from
exactly three companies: Zillow, Apartments.com and AffordableHousing.com. NCLC
reported in 2025 that the share of renters paying a fee went **up**, 58% -> 60%.

Directly relevant to this dataset: **FTC and the State of Colorado settled with
Greystar for $24M in December 2025**, requiring clear total-price disclosure
whenever it advertises rent. Greystar is the largest operator in our sample.

Aggregator practice, verified from their own announcements:

| Platform | All-in total | Notes |
|---|---|---|
| Rent.com | yes | "Total Costs & Fees" tab, Feb 2024 |
| Apartments.com | yes, **opt-in per property** | expanded nationwide by early 2026 |
| Zillow (+Trulia/HotPads) | yes, **opt-in** | "Cost of Renting Summary" 2023 -> "Total price" badge, driven by MA/CT laws |
| Zumper | yes, opt-in | Total Monthly Leasing Price via Engrain |
| AffordableHousing.com | yes | TMLP, announced 2026 |
| Apartment List | unclear | no product documentation found |
| Redfin | none found | absence of evidence, not proof of absence |

Every one is **opt-in**, and each shipped after a law or a White House event —
none as an independent product bet.

### Lease term: nobody handles it. At all.

- **No law anywhere** — federal, state or municipal — requires disclosing which
  lease term an advertised rent applies to, or that a price came from an
  algorithmic pricing system.
- **No aggregator** offers a term selector or shows term-dependent pricing.
  Apartments.com requires a "Standard Lease Term for Advertised Rent" field
  (mandatory in Massachusetts), but it is a **single static value**, not a matrix.
- Colorado tried twice to regulate algorithmic rent-setting: **HB24-1057** failed,
  and **HB25-1004** passed the legislature and was **vetoed in May 2025**. Several
  cities banned the tools outright, and the Nov 2025 DOJ-RealPage consent decree
  restricts input data — but none of it creates a consumer-facing duty to disclose
  that the same apartment costs 2.7x more on a short lease.

### The data-model excuse expired in January 2025

**MITS** — not RETS — is the schema behind ILS feeds. Historically it had no field
for mandatory fees or term-dependent pricing, which would have made this a
capability problem. But a **Fee Transparency extension (MITS Property/Marketing/ILS
v5.0) shipped 14 January 2025**, adding a Total Monthly Leasing Price concept and
explicitly supporting *"Base Rent w/ all lease term duration options transmitted."*

So the pipe now carries term-by-term pricing. Adoption is voluntary and thin. The
gap is a **display and adoption choice on a very new, sparsely-populated field** —
not a limit of the plumbing.

## A compliance signal, offered as a question rather than a finding

HB25-1090 has been in force since 1 January 2026. Eight months later we can detect
a machine-readable total-price disclosure on **54-61%** of sites.

| Operator | Sites with data | Total price detected |
|---|---|---|
| Kairoi Residential | 24 | **24 (100%)** |
| Greystar | 87 | **78 (90%)** |
| AIR Communities | 22 | **0 (0%)** |
| unattributed / small operators | 27 | 6 (22%) |

Greystar at 90% is consistent with a company operating under a December 2025
consent order. The 9 that we could not detect are worth someone looking at.

**The important caveat:** this measures *structured, machine-readable* disclosure.
A site could satisfy the statute in prose, in an image, or in a PDF we never
parsed. These numbers are a place to start looking, **not** a compliance
determination, and should not be presented as one.

**AIR Communities at 0% illustrates a structural loophole rather than a
violation.** AIR publishes no price on its marketing pages at all — pricing lives
entirely behind its Entrata leasing portal. A disclosure duty attached to
*advertised* prices does not bite on a page that advertises no price. Our coverage
gap and the disclosure gap turn out to be the same gap.

## What this means for the navigator

1. **`comparable_rent` deliberately excludes concessions.** 62% of concessions are
   phrased "up to" and 20% are limited to "select homes", so folding them into the
   headline produces a discount most households will not receive. The
   concession-adjusted figure ships alongside as `comparable_rent_best_case`,
   labelled, with `concession_is_upper_bound` set.
2. **A rent with no stated term is the norm, not an edge case.** 91% of sites.
   Treat the absence as a disclosed unknown rather than assuming 12 months —
   `rent_12mo_method` records `term-unknown-assumed-standard` so it is auditable.
3. **Zero rows are cost-complete**, and that is a finding about the market rather
   than about the collector: 6,557 rows do not state the lease term and 4,216
   publish no mandatory fees.
4. **Lease-term normalization is genuinely novel.** No law requires it, no
   aggregator does it, and the feed standard only gained the field in January
   2025. Publishing a comparable 12-month-equivalent rent would make this tool
   the only consumer-facing source that does — and it is defensible because the
   underlying matrices are published by the landlords themselves.
5. **The fee corpus is the tractable win.** Where fees are published they are
   published *well* — structured, itemised, with an issuance date. 98 sites already
   expose a full schedule. That is a real dataset nobody else has assembled, and it
   is far less contested than asking rent.
