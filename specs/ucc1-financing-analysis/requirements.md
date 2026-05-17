# UCC-1 Financing Analysis — Requirements

**Research questions:** A4 (private capital signals, foreign-acquisition risk,
M&A exit detection), B3 (Phase II → III latency)

**Status:** Pilot scope, **narrowed after Phase 0** to CA-only against the
CA-organized subset of the Form D cohort. The original DE+CA scope was not
achievable on free data — see
[docs/research/sbir-ucc1-pilot.md](../../docs/research/sbir-ucc1-pilot.md)
for the Phase 0 findings.

## Background

The Form D analysis (`docs/research/sbir-form-d-fundraising-analysis.md`)
measures private *equity* raised by SBIR firms via Reg D — ~$1.82–$2.37 per
$1 of SBIR funding. It misses private *debt* entirely: venture debt
(SVB, Hercules, Trinity, Western Alliance), equipment financing, and
asset-backed lines.

UCC-1 financing statements, filed at state Secretaries of State under UCC
Article 9, are the public record of those secured transactions. Each filing
names a debtor, a secured party (lender), and a collateral description.
UCC-3 amendments (assignment, continuation, collateral change) and
terminations (debt released) record the lifecycle of each UCC-1.

Per UCC § 9-307, a registered organization's UCC-1s are filed in its **state
of organization** (not HQ state). Phase 0 confirmed that Delaware — the
state of organization for the majority of VC-backed C-corps — has no free
public UCC search, while California bizfileOnline is fully viable for the
subset of cohort firms organized in CA.

This spec scopes a **CA-only pilot** answering:

1. *For CA-organized SBIR firms in the Form D high-confidence cohort, what
   fraction took secured debt and from whom?*
2. *Does UCC-3 termination timing line up with known M&A events for that
   subset, making it a usable corroborating / earlier signal?*

## Requirements

1. **SHALL** extract UCC-1 filings (and related UCC-3 amendments,
   continuations, assignments, terminations) from California bizfileOnline
   for the CA-organized subset of the SBIR firms in the Form D
   high-confidence cohort.
2. **SHALL** identify the CA-organized subset by querying state-of-
   organization for each cohort firm (CA SOS Business Search or equivalent
   public source). Firms not registered in CA SOS as a CA-organized entity
   are excluded from the pilot population.
3. **SHALL** match CA UCC debtors to the CA-organized cohort using name
   normalization compatible with the existing entity-resolution approach,
   filtering to debtor-side matches only (CA portal free-text search
   returns hits on both debtor and secured-party fields).
4. **SHALL** classify secured parties into: known venture-debt lenders,
   equipment/inventory financiers, banks (depository), tax authority
   (federal/state — these dominate CA portal results), other / unknown.
5. **SHALL** report, for matched firms, the count of UCC-1 (Financing
   Statement) filings excluding tax/judgment liens, stratified by award
   agency and award vintage.
6. **SHALL** capture UCC-3 amendments and terminations associated with each
   matched UCC-1, and reconstruct each filing's lifecycle state
   (active / terminated / lapsed) as of the analysis run.
7. **SHALL** report, for matched firms with a known M&A event
   (`data/sbir_ma_events.jsonl`, high+medium tier — note: file uses
   `confidence` field, not `tier`), whether a UCC-3 termination fired
   within ±180 days of the event date.
8. **SHALL** report match rates, false-positive sensitivity (top-K
   manually reviewed matches), and the headline coverage gap (CA-organized
   subset size vs. full cohort size).
9. **SHOULD** identify foreign secured parties as a separate flag (national-
   security signal aligned with A4 / CSIS [L17]).
10. **SHOULD NOT** attempt DE coverage, multi-state expansion beyond CA,
    IP-collateral parsing, or Neo4j loading in the pilot. Those are
    explicitly out of scope; revisit after pilot results.

## Gate Condition

Can state, on completion:

> *"Of the N CA-organized firms in the Form D high-confidence SBIR cohort
> (out of the ~3,640 full cohort), X% have at least one UCC-1 (Financing
> Statement) filing against them in CA bizfileOnline. Top secured parties
> by SBIR-firm count are [list]. Match precision on a 50-firm hand-reviewed
> sample is Y%. Of the M CA-organized firms with a known M&A event, T% had
> a UCC-3 termination within ±180 days of the event."*

If X% < 10% or precision < 70%, the pilot still produces a documented
"CA-organized SBIR firms rarely show UCC-1 activity in their organization
state" result — itself a valid finding given the § 9-307 channel logic.
Reconciliation matters more than completeness.

## Non-Goals (pilot)

- DE coverage (no free public search; paid Authorized Searcher or
  commercial bulk feed required — out of pilot scope).
- Multi-state expansion beyond CA (free state portals exist for NY, MA,
  TX, WA, OH, etc., but each catches only its state-of-organization
  population; marginal yield is small for the VC-backed segment that
  dominates the DE-incorporated cohort).
- IP-collateral text parsing (patent / trademark pledges).
- Dagster asset wiring or Neo4j loading.
- Lender-concentration time series.
- Pivot to BDC Schedule of Investments or SEC 10-K credit-facility
  disclosures (worth pursuing as a separate spec; not folded into this
  one).

## Dependencies

- Form D high-confidence cohort — **derivation exists, file does not**.
  Cohort is derivable from `data/form_d_details.jsonl` + SBIR awards
  per the matching rules in `sbir-form-d-fundraising-analysis.md` (high
  confidence tier; firm name match OR SBIR ZIP matches Form D issuer ZIP).
  A discrete export of the cohort is a prerequisite for this pilot.
- SBIR awards table with company name + state — EXISTS
- Fuzzy entity-resolution utilities — EXIST (`sbir_etl` matching helpers)
- M&A events dataset (`data/sbir_ma_events.jsonl`) — EXISTS in the main
  repo at the gitignored path; field is `confidence` (not `tier` as the
  spec previously referenced)
- CA SOS Business Search (`bizfileonline.sos.ca.gov/search/business`) for
  state-of-organization filtering — free public source
