# SBIR UCC-1 Pilot — Phase 0 Findings & Scope Narrowing

**Status:** Phase 0 complete (2026-05-16). Pilot scope narrowed to CA-only
against CA-organized cohort subset. Original DE+CA scope is not achievable
on free data. See "Decision" section below.

**Related:** [specs/ucc1-financing-analysis/](../../specs/ucc1-financing-analysis/),
[sbir-form-d-fundraising-analysis.md](sbir-form-d-fundraising-analysis.md),
[sbir-ma-exit-analysis.md](sbir-ma-exit-analysis.md)

## Phase 0 Probe

Goals: confirm UCC-1 + UCC-3 retrievability per state portal, document
schema, identify access blockers before any code.

Method: Playwright-driven manual lookups on DE and CA UCC search portals,
targeting 5 high-confidence Form D cohort firms with known M&A events
(Inhibrx, Pacific Biosciences, Transphorm, AeroVironment, PTC
Therapeutics). All five firms have ≥$100M Form D filings, are CA-or-NJ-HQ,
and were either acquired or are publicly listed.

## Finding 1 — Delaware has no free public UCC search

DE Division of Corporations confirms (`corp.delaware.gov/uccsearch/`):

> *"Effective December 1, 2001, all non 'Search to Reflect' UCC Searches
> will be performed by a Delaware Authorized Searcher."*

The Authorized Searcher list is 25 firms: CSC, CT Corporation, Cogency
Global, Computershare, First Corporate Solutions, etc. These are the same
commercial UCC aggregators the original spec explicitly scoped out as
non-goals.

`icis.corp.delaware.gov/Ecorp/UCC.aspx` is a filing portal only ("Welcome
to e-UCC, the State of Delaware's online system for filing UCC documents")
— it is not a search portal.

What "Search to Reflect" returns was not probed in this Phase 0; it is
documented as a limited search and is not exposed via a public web form on
the DE Division of Corporations site.

**Implication:** DE half of the spec's "DE + CA free indexes" scope is
not viable. Any DE coverage requires either a paid Authorized Searcher
engagement or a commercial bulk data vendor.

## Finding 2 — California bizfileOnline UCC search is fully viable

`bizfileOnline.sos.ca.gov/search/ucc`:

- Public, no login required for search
- Data freshness disclosed in-portal ("UCC Documents have been processed
  through: 05/11/2026" at probe time)
- Result row schema:
  `UCC Type | Debtor Information | File Number | Secured Party Info |
   Status | Filing Date | Lapse Date`
- Expanded detail panel adds: full debtor name, full debtor address
  (street + ZIP+4), full secured party name, full secured party address
- "View History" modal returns the full lifecycle of related filings
  (initial Lien Financing Stmt → Termination, with file number + date
  per event, plus downloadable PDF at
  `/api/report/GetImageByNum/<token>`)
- Advanced search filters: Status (All / Active unlapsed / Active
  lapsed+unlapsed); File Type (All / **Financing Statement** /
  Judgment Lien / State Tax Lien / Federal Tax Lien / Attachment); File
  Date range; Lapse Date range
- No CAPTCHA or rate-limit response observed at ~10 queries / 25 minutes
- Free-text search matches against **both** debtor and secured-party
  fields — role filtering must be done client-side

**Implication:** The CA portal is suitable for the spec's `UCCExtractor`,
`LifecycleReconstructor`, and `MAEventCorroborator` components without
modification.

## Finding 3 — UCC § 9-307 jurisdictional bias dominates

A registered organization's secured-party UCC-1 filings are recorded at
its **state of organization**, not its operational HQ state. Most
VC-backed C-corps are organized in DE regardless of HQ.

Probed against this hypothesis:

| Firm | HQ | Form D total | CA UCC results (debtor-side) |
|---|---|---|---|
| Inhibrx, Inc. | La Jolla, CA | $410M | 1 — California EDD payroll tax lien only. Zero venture-debt or bank UCC-1s. |
| Pacific Biosciences of California, Inc. | Menlo Park, CA | $170M | 1 — California EDD payroll tax lien only. Zero venture-debt or bank UCC-1s. |

Both firms are DE-incorporated. Their secured-party UCC-1 filings (bank
revolvers, venture debt, equipment finance) all live in DE under § 9-307
and are invisible to free CA search.

**Implication:** A CA-only pilot against the *full* Form D cohort would
systematically miss the secured-debt activity of the largest VC-backed
firms — exactly the population the spec most wanted to characterize.

## Finding 4 — Free public-data alternatives do not substitute for UCC

For "all secured debt" (banks, equipment finance, venture debt,
factoring, asset-backed lines), evaluated against UCC-1 as the
comprehensive primary source:

| Free source | Captures | Cannot substitute because |
|---|---|---|
| BDC Schedule of Investments (10-K/10-Q) | Venture-debt loans by publicly-traded BDCs (Hercules, Trinity, Horizon Tech Finance, etc.) | Misses banks, equipment finance, factoring, private credit funds |
| SEC 8-K Item 1.01 + 10-K credit facility disclosures | Material credit agreements at public firms | Only public firms (<5% of SBIR cohort); only material facilities |
| PACER bankruptcy schedules | All secured creditors at distress event | Only dead firms; captures failure mode, not active capital |
| FDIC Call Reports / OCC | Aggregate bank loan composition | No borrower names |
| Form D type=debt | Reg D-exempt debt offerings | Only Reg D-routed debt; misses bank, equipment, factoring |
| Other states' free UCC portals (NY, TX, MA, WA, OH, VA, NJ, IL) | UCC-1s against debtors organized in those states | Same § 9-307 logic — extending coverage by state adds 1–3% of cohort per state for the DE-dominated VC-backed segment |

The BDC and SEC routes complement UCC by giving lender-side and
borrower-side disclosures respectively, but neither replaces UCC-1 for
coverage breadth.

## Decision — narrow to CA-organized cohort

The pilot proceeds with the following revised scope:

- **Population:** the subset of the Form D high-confidence SBIR cohort
  whose state of organization is California
- **Source:** CA bizfileOnline UCC search only
- **Headline question, revised:** *"For CA-organized SBIR firms in our
  Form D high-confidence cohort, what fraction took secured debt
  (UCC-1 filings) and from whom?"*
- **M&A corroboration:** still attempted for the narrow cohort; sample
  size will be small but the signal/null check still applies
- **What this no longer answers:** anything about the DE-incorporated
  majority of the cohort

The narrowing makes the pilot honest about what it can deliver from free
data. It does not pretend to answer the question the original spec
implicitly posed (secured debt against the full ~3,640-firm cohort).

## Gate-condition statement (replacing the original)

Can state, on completion: *"Of the N CA-organized firms in the Form D
high-confidence SBIR cohort, X% have at least one UCC-1 (Financing
Statement) filing against them in CA bizfileOnline. Top secured parties
by SBIR-firm count are [list]. Match precision on a 50-firm hand-reviewed
sample is Y%. Of the M CA-organized firms with a known M&A event, T% had
a UCC-3 termination within ±180 days of the event."*

If X% < 10% or precision < 70%, the pilot still produces a documented
"CA-organized SBIR firms rarely show UCC-1 activity in their organization
state" result, which is itself a valid finding worth publishing.

## Future options (not in pilot scope)

- **Multi-state expansion (free):** add NY, MA, TX, WA, OH free portals
  for incrementally more state-of-organization coverage. Each portal
  needs a custom scraper; marginal yield per additional state is ~1–3%
  of cohort.
- **Commercial DE bulk search (~$1.5k–$5k):** one-shot quote from First
  Corporate Solutions, Cogency Global, or CSC for a bulk debtor lookup of
  the ~3,640-firm cohort against DE UCC. The only path to comprehensive
  coverage; reopens after pilot validates the method on CA.
- **BDC Schedule of Investments harvesting:** parse 10-K/10-Q Schedule
  of Investments from Hercules, Trinity, Horizon Tech Finance, Runway,
  TriplePoint, and ~25 other publicly-traded venture-debt BDCs. Match
  borrower names to the SBIR cohort. Complementary signal (venture-debt
  segment specifically, lender-side disclosure). Would be a separate
  follow-on spec; not bundled with the UCC pilot.
- **DE "Search to Reflect":** not probed in this Phase 0; worth a brief
  follow-on test in case it returns useful information.

## Method note — Playwright access to bizfileOnline

The probe used Playwright MCP. The CA portal is a React SPA; advanced
search and history-modal interactions worked through standard form-fill
and click. The PDF download endpoint
(`/api/report/GetImageByNum/<token>`) returned image bytes without
authentication, suggesting bulk scraping is technically feasible —
respect rate limits and the portal's terms of use in any production run.
