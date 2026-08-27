# Candidate Coverage — is 647 sites the whole list?

No. 647 is what we could resolve to a **fetchable marketing URL**, which is a much
smaller set than the properties that exist. Measured against real sources:

## Sources used in this pass

| Source | Universe | Attempted | Never attempted |
|---|---|---|---|
| Operator portfolios (21 operators) | — | 430 | — |
| OpenStreetMap, Denver metro named apartments | 3,196 | 251 (those with a `website` tag) | **2,945** |

## Sources verified but NOT used

| Source | Records | Named complexes | Usable for enumeration? |
|---|---|---|---|
| Boulder rental licenses (CC0) | 11,689 | **685 distinct**, 674 not attempted | **Yes** — has `COMPLEXNAME` + `DWELLINGUNITSONCASE` |
| Denver residential rental licenses | 38,553 | none | **No property-name field and no unit count.** `ENTITY_NAME` is the license holder. 599 parcels carry >4 licenses as an inferred proxy only |
| Denver assessor, apartment class `1225` | 1,759 parcels / 127,293 units | none | Addresses + unit counts, no names |

The brief cited ~1,992 parcels / ~140,509 units for the assessor layer. Querying it
directly returns **1,759 / 127,293**. Reporting what reproduced.

## Operators not covered (verified this pass)

| Group | Operators found | CO communities actually counted | Portfolio page server-rendered | Properties on their own domain |
|---|---|---|---|---|
| Market-rate | 20 | **88** (14 operators; 6 more JS-only or blocked) | 10 / 20 | **4 / 20** |
| Affordable / income-restricted | 16 | **184** (14 operators) | 14 / 16 | **1 / 16** |

Verified total: **272 additional communities.** A softer extrapolation lands near 440,
but 272 is the number actually counted on a page.

## The finding that matters more than the counts

**Only 5 of these 36 operators give their properties their own marketing domain.**
The rest keep every community on an operator subpage.

The collector built here assumes one property = one host with a floor-plan page, and
its whole yield advantage comes from platform fingerprinting (Jonah Digital, 97% rent
yield). Operator-subpage properties break both assumptions:

- one host serves dozens of properties, so polite per-host rate limiting serializes them
- the page shape is the *operator's*, not a platform's, so it is one hand-written
  parser per operator rather than one per platform
- Jonah/Funnel fingerprints do not apply at all

So the honest answer to "are there more options" is: **yes, roughly 270–670 more
properties are reachable, but they are structurally harder, not more of the same.**
Each is parser work with no fingerprint leverage.

## The affordable segment deserves separate treatment

It is the most relevant inventory for a navigator that advises on assistance-program
eligibility, and it was excluded entirely by the market-rate framing.

Its pages are *more* readable than market-rate (14 of 16 server-rendered), but probing
six of them returned **zero structured rows** — they are prose directory pages on
WordPress. More importantly, **asking rent is not the right field.** Eligibility turns
on AMI band, unit-mix set-asides, and waitlist status, which these pages express as
sentences, not data.

That is a different collector with a different schema, not an extension of this one.

## Operator-sitemap enumeration — tested, with results

Sitemap discovery was built and run against 42 operator sites.

| Result | Count |
|---|---|
| Operator sites enumerated | 42 |
| Sites yielding property URLs | **17** (25 returned nothing usable) |
| Property URLs found | 243 |
| Not already attempted | 226 |
| Collected: clean rent + availability | **24** |
| Collected: rent only | 11 |
| Collected: nothing extracted | 118 |
| **Dropped — terms prohibit** | **69** (67 of them a single operator, JPI) |
| Unreachable | 4 |

Best yields: Griffis 34 URLs, Volunteers of America 36, Brothers Redevelopment 22,
Colorado Coalition for the Homeless 20, Willow Bridge 20, Camden 13, Archway 11.

**Usable rate: 35 of 226 (15.5%)** — or ~22% once JPI's terms-dropped 67 are
excluded from the denominator. That is materially worse than the 41.9% from curated
operator portfolios, for two reasons that were predictable in hindsight:

- Much of what sitemaps surface on these operators is **affordable/nonprofit
  inventory**, whose pages are prose directories rather than structured floor-plan
  data. They enumerate well and extract badly.
- Sitemaps list *pages*, not *properties with availability*. Many are stub or
  lease-up pages with no pricing published at all.

The standing terms check earned its place here: **JPI was dropped mid-run**, on a
host that had never been seen before. That is the mechanism working as designed
rather than a one-time audit.

## What actually limits coverage

Not the candidate list. Every source above yields **names or addresses**; almost none
yield the **marketing URL** the collector needs. Name → URL resolution is the funnel's
narrow point, and doing it at scale without an aggregator (all of which prohibit
automated access) is the unsolved problem.

Ranked by yield per unit of effort:

1. **Boulder licences → 674 names** — CC0, has unit counts, but mostly small condo LLCs
   unlikely to have marketing sites at all.
2. **20 market-rate operators → 88 confirmed** — needs ~20 per-operator parsers.
3. **Affordable providers → 184 confirmed** — needs a new schema (AMI, waitlists).
4. **OSM 2,945 unnamed-URL features** — needs name→URL resolution first.
5. **Denver licences / assessor** — address-keyed only; useful for *validating* a
   property list, not building one.
