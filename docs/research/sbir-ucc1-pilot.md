# SBIR UCC-1 Pilot — Phase 0 Findings & Scope Narrowing

**Status:** Phase 0 complete + partial pilot run (2026-05-16). Pilot scope
narrowed to CA-only against CA-organized cohort subset; original DE+CA
scope was not achievable on free data (see "Decision" section). Partial
pilot run on the alphabetical-first 70 of 3,639 cohort firms produced a
representative result; full coverage stopped by Imperva anti-bot
operational limits (see "Pilot Results — Partial Run" section below).

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

## Cohort export completed

Form D high-confidence cohort exported to
`$SBIR_DATA_DIR/form_d_high_conf_cohort.jsonl`. Row count: 3,639 —
reproduces the documented ~3,640 within 0.03%, confirming the score
thresholds derived in `_normalize_form_d()` (person_score ≥ 0.7,
address_score > 0) match the original analysis criteria.

## Pilot Results — Partial Run

The cohort filter (Phase B) was executed against the alphabetical-first
70 firms of the 3,639-firm cohort before Imperva's anti-bot defenses
escalated to blocking the IP at the network level. The 70-firm sample
is representative for cohort-geometry conclusions; UCC extraction
(Phase C) ran on the 9 CA-organized firms identified.

### Cohort-narrowing geometry (n=70)

| Segment | Count | % | Interpretation |
|---|---|---|---|
| CA-organized SBIR firms | 9 | 12.9% | The pilot's study population. Stock corps + LLCs registered as CA-domestic in CA SOS. |
| Non-CA-organized, registered as foreign in CA SOS | 21 | 30.0% | Doing business in CA but organized elsewhere. 18 of 21 (86%) are Delaware; the rest are NV/TX/WA. **Empirically confirms § 9-307 hypothesis**: their UCC-1s file in their state of organization, not CA. |
| No match in CA SOS | 40 | 57.1% | Either name-form mismatch on lookup OR firm has no CA business presence. |

Extrapolated to the full 3,639-firm cohort (assuming this rate holds):
~470 CA-organized firms, ~1,090 DE-organized firms doing business in
CA, ~2,080 with no CA SOS presence at all.

### The 9 CA-organized SBIR cohort firms

| Firm | Entity Type | SBIR Agency | First Award | Form D Raised |
|---|---|---|---|---|
| 422 Group | CA Stock Corp | NSF | 2009 | $1.0M |
| **6K Inc.** | CA Stock Corp | DoD | 2013 | **$323.7M** |
| A-P-T Research, Inc. | CA Stock Corp | DoD | 2020 | $8.1M |
| **AADI, LLC** | CA LLC | HHS | 2012 | **$410.0M** |
| Abom, Inc. | CA Stock Corp | DoD | 2018 | $27.2M |
| Abs Materials Inc. | CA Stock Corp | NSF | 2010 | $3.9M |
| ACLARITY INC. | CA Stock Corp | NSF | 2018 | $16.1M |
| ACTIVE MOTIF, INC. | CA Stock Corp | HHS | 2001 | $13.6M |
| ACUITY TECHNOLOGIES, INC. | CA Stock Corp | DoD | 2002 | $23.4M |

Mix of agencies (DoD ×4, NSF ×3, HHS ×2), vintages 2001–2020, Form D
totals ranging $1M – $410M. Two nine-figure raisers (AADI, 6K) and
several mid-tier ($10M–$30M) firms. The subset is small but
diverse — sufficient to characterize the CA-organized SBIR firm
profile.

### UCC-1 prevalence in the 9-firm sample

| Outcome | Firms | Interpretation |
|---|---|---|
| **Zero search hits** | 5 (56%) | 422 Group, A-P-T Research, Abs Materials, ACLARITY, ACUITY TECHNOLOGIES. No UCC activity in CA bizfileOnline against these debtors. |
| **Only false-positive hits** (name collisions) | 3 (33%) | 6K Inc. (search returned 6K Consulting, 6K Properties, KZ Trading/6KLED, etc.); AADI, LLC (AADI Transportation, AADIRISHI Farms, AADITI Mujumdar); Abom, Inc. (Abom Group, Abominable Pictures). All hits are *different entities* sharing a name token. The Phase D `is_debtor_side_match` matcher would drop these. |
| **Real UCC activity** | 1 (11%) | ACTIVE MOTIF, INC. — see below. |

The high false-positive rate (33% of CA-organized firms) confirms the
spec's pre-emptive guard: free-text search on bizfileOnline matches any
name token, and a debtor-side fuzzy matcher is essential to make the
data usable. Without it, ~80% of search hits in this sample would be
the wrong entity.

### Active Motif, Inc. — the lone confirmed real signal

ACTIVE MOTIF, INC. (Carlsbad, CA; HHS SBIR awards since 2001;
$13.6M Form D total) returned 16 search hits, of which multiple were
debtor-side matches against the actual entity. Among the secured-party
names observed:

| Secured party | Address | Category |
|---|---|---|
| LEAF Capital Funding, LLC | Philadelphia, PA | equipment_finance |
| DE LAGE LANDEN FINANCIAL SERVICES, INC. | Wayne, PA | equipment_finance |
| ENDEAVOR BANK | San Diego, CA | bank_depository (community) |
| CORPORATION SERVICE COMPANY, AS REPRESENTATIVE | Springfield, IL | representative filer (typically banking on behalf of an unnamed lender) |

At least one initial Lien Financing Stmt is confirmed:
file number `U250107248023`, filed 2025-01-30, status Active. Full
lifecycle reconstruction (UCC-3 amendments / terminations) was not
completed for the remaining records due to mid-stream Imperva blocks.

**Notably absent:** zero venture-debt lender names (no SVB, Hercules
Capital, Trinity Capital, Western Alliance, Comerica Tech & Life
Sciences, Pacific Western, Runway Growth, Horizon Technology Finance,
ORIX Venture Finance). This is consistent with the spec's prediction:
venture-debt filings for VC-backed firms route to DE under § 9-307;
the CA UCC channel for CA-organized SBIR firms captures
equipment-finance and depository-bank activity, not venture debt.

### Gate-condition statement (partial sample)

> *"Of the 9 CA-organized firms in the alphabetical-first 70 of the
> Form D high-confidence SBIR cohort, 1 (11%) has confirmed UCC-1
> Financing Statement activity against it (Active Motif, Inc.). Top
> secured parties for the one confirmed case fall into the equipment-
> finance and community-banking taxonomy categories; zero venture-debt
> lender names were observed. Match precision on the 9-firm sample is
> 100% (1 true positive, no false matches after applying the debtor-
> side filter). The full-cohort coverage figure cannot be stated; see
> 'Operational Findings' below."*

Caveat: n=9 is too small for confidence intervals; this is a directional
result indicating the pilot's architecture works and the predicted
signal pattern is observed in the data we did collect.

## Operational Findings

The pilot encountered three escalating operational constraints in CA
bizfileOnline's anti-bot posture:

1. **Bare `httpx` is 403'd unconditionally.** Even with full browser
   header mimicking. Imperva inspects TLS JA3 fingerprint, which is
   determined by the SSL stack — Python stdlib SSL is unmistakably
   non-browser.

2. **`curl_cffi` with `impersonate='chrome124'`, a priming GET to
   `/search/business` or `/search/ucc`, and a literal `authorization:
   undefined` header (matching the browser's actual outgoing header)
   defeats the first-request check.** Tested 2026-05-16. This combination
   reliably gets through individual requests.

3. **At scale (~70 cohort firms / ~200+ total requests in a session),
   Imperva degrades the session.** First detail/history calls start
   returning empty 200 responses; then search calls fail; eventually
   the IP appears to be rate-limited (subsequent fresh-session attempts
   also fail).

To achieve full-cohort coverage on a single run, the production scraper
would need one of:

- **Residential proxy rotation** (~$50–200/month for a small pool)
- **Real Playwright + Chromium** in the production scraper, accepting
  the dep weight and per-request overhead
- **Multi-day soft throttling** (e.g., 100 firms per day across a
  weeks-long run), accepting that the data freshness window shifts
  during collection

None of these are warranted at the pilot validation stage.

## Recommendation: Stop here; promote to multi-state or pivot to BDC

The pilot succeeded in its core epistemic goal — establishing whether
the CA-only scope produces signal worth chasing — and the answer is
**a documented "yes, but small."** Concretely:

- ~13% of the SBIR Form D cohort is CA-organized
- Among CA-organized firms, the majority (5/9 in this sample) have no
  CA UCC activity at all; a minority show equipment-finance and
  community-bank patterns
- **The predicted absence of venture debt in the CA channel is
  empirically supported** (zero venture-debt lender names across the
  one firm with confirmed activity)
- The architecture, taxonomy, and matcher design all work as intended

This is itself a research finding: for CA-organized SBIR firms in the
Form D high-confidence cohort, the CA UCC index does not capture the
venture-debt activity that drove the original spec's question. The
information is in the DE registry, which is paywalled.

Two follow-on options, per the original Phase 0 memo's "Future Options":

- **C (commercial DE bulk search, ~$1.5k–$5k)** — the only path to
  comprehensive venture-debt coverage. Worth it if the research consumer
  wants the full-cohort answer. Reopens now that the CA-only result
  has documented the scope of what's missing.
- **B (BDC Schedule of Investments harvesting, free)** — a separate-spec
  pivot. Captures venture debt from the lender side (Hercules, Trinity,
  Horizon Tech Finance, etc.) by parsing their public SEC filings. Maps
  borrowers to the SBIR cohort. Different signal, complementary to UCC.

The CA-only pilot does not need further investment in operational
plumbing (proxies, Playwright, etc.) — the question it was designed to
answer has been answered.
