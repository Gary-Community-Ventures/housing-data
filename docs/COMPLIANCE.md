# Compliance policy

This project feeds a foundation civic tool whose partnerships with state
agencies and an MLS depend on a clean provenance story. The operating bar,
verbatim from the project brief: **"we could probably win that argument" is not
good enough.** Rules are enforced in code, not in a document code can drift from.

## The rules and where they live

| # | Rule | Enforcement |
|---|---|---|
| 1 | Leasing-engine vendors (Yardi/RentCafe/SecureCafe, Entrata/ProspectPortal, RealPage OneSite/onlineleasing, AppFolio, ResMan, MeetElise, SelfTourNow, ActiveBuilding) are never requested, followed, or parsed — including via redirect | `hn/policy.py is_denied()`, re-checked after every redirect |
| 1b | Listing aggregators (Apartments.com, Zillow, Trulia, HotPads, Rent.com, ApartmentGuide, ApartmentList, Zumper, Realtor.com, Redfin, …) are never fetched and never used as enumeration sources | `ILS_DENY` in `hn/policy.py` |
| 2 | No API token is ever harvested from page source (esp. api.rentcafe.com) | no code path reads tokens; host denylisted |
| 3 | If a property's own marketing site IS a vendor product, the property is skipped entirely | host + self-identifying body markers; a mere outbound "Apply Now" link to a vendor does NOT trigger this |
| 4 | Terms-of-use checked per host, **every run**, logged with timestamp; prohibiting hosts dropped and their data deleted | `hn/terms.py` → `logs/terms_audit.jsonl` (versioned) |
| 5 | robots.txt honored; ≥3s between requests to a host; UA identifies the bot with a contact URL | `Fetcher` |
| 6 | No listing photographs collected or stored | extractors strip image fields |
| 7 | CAPTCHAs are never solved or bypassed | browser agents skip and record |

## Judgment calls already made (and why)

- **Clause scope is not argued.** A prohibition naming only an "Investor Portal"
  still dropped all 30 of that operator's properties.
- **UNREADABLE ≠ permitted.** A terms doc that exists but can't be fetched ⇒
  abstain. A dead 404 terms link ⇒ positive evidence of no terms; proceed.
- **Personal-data-scoped prohibitions** ("harvest user data") don't reach
  collecting public listing content (we collect no personal data) — but are
  verdict `PROHIBITS_PERSONAL_DATA_ONLY`, surfaced for human review, never
  silently cleared.
- **Bot-management 403s vs owner policy.** All bot-blocked hosts permit crawling
  in robots.txt; browser recovery of those is documented in ASSESSMENT.md as a
  decision for the foundation, not the scraper. CAPTCHA = unambiguous no.
- **The terms classifier has been wrong twice** (missed stem+bullet drafting;
  missed "automated data collection" phrasing). Each fix triggered a full
  re-audit and retroactive data deletion. Treat the PROHIBITS count as a floor.

## Regulatory context (as of Aug 2026, see reports/DISCLOSURE.md)

- Colorado **HB25-1090** (eff. 2026-01-01): total-price disclosure in rental ads;
  the "Total Monthly Leasing Price" pattern we parse.
- FTC Junk Fees Rule **excludes** long-term rentals; a rental-specific ANPRM
  opened Mar 2026. FTC + Colorado settled with Greystar ($24M, Dec 2025).
- **No law anywhere requires disclosing which lease term an advertised rent
  applies to** — the gap this dataset uniquely measures.

## Attribution obligations

- OpenStreetMap enumeration: © OpenStreetMap contributors, ODbL 1.0 (shown in UI).
- Boulder rental licenses: CC0, attributed to City of Boulder.
- Census geocoder: public domain. Rent/availability: each property's own site,
  per-row `source_url` + timestamp.
