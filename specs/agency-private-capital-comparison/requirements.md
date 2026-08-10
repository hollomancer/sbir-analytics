# SBIR vs. Private-Capital Comparison — Requirements (agency-parameterized; NSF as initial target)

**Target epistemic tier:** `exploratory`

> **Status (2026-08-09):** Phase 1 is implemented and its pinned NSF real-data
> review artifact is materialized, but it is non-citable and awaits sign-off.
> Phase 2 has a tested scaffold and a maintained, reproducible SEC DERA staging
> producer, not a valid matched comparison. The staged universe has incomplete
> SBIR exclusion and no validated NAICS-2 covariate. A shared date-aware
> event/coverage contract and a CIK-native Form D business-combination filing
> proxy now exist, but FPDS, patent, and verified M&A outcome inputs remain
> missing. Do not materialize or publish Phase 2
> before the Phase 1, identity, covariate, and outcome gates are satisfied.
> Supports inventory questions **F3** (private-capital comparison), **B2** (commercialization outcomes), **B3** (transition rates) in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** F3 / B2 / B3 — SBIR vs. private-capital cohort comparison (NSF initial target)
**Answers for:** entrepreneurial finance researchers, SBIR program managers, policy analysts
**Complexity tier:** Relational → Inferential (Tier 2–3)

---

## Done when

> **Phase 1:** A policy analyst can state: "BLS reports 5-year establishment survival at ~50%. NSF Phase II 5-year survival proxy is [X]% on cohort [vintage range, n=Y]. The difference is attributable to [Z]." Produces the exact reconciliation pattern of `leverage-ratio-analysis`.
>
> **Phase 2:** An entrepreneurial finance researcher can state: "On vintage [X], NAICS-2 [Y], state [Z]: NSF Phase II awardees transitioned to federal contract at [A]% within 5 years; matched non-SBIR Form D issuers transitioned at [B]%. Selection-bias and matching caveats: [see threats-to-validity section]."

---

## User Stories

**As a policy analyst benchmarking NSF's SBIR program against published venture-capital performance metrics,**
I want Phase I→II graduation rates, 5-year survival proxies, and M&A exit rates computed for the NSF cohort and placed alongside BLS/Howell/Lerner baselines with a reconciliation narrative, so that I can report how NSF SBIR performs relative to seed-stage private capital in a form suitable for OSTP or congressional briefings.

**As an entrepreneurial finance researcher studying whether SBIR awardees outperform comparable private-capital-financed firms,**
I want a covariate-matched control cohort of non-SBIR Form D issuers with outcome deltas computed against the NSF SBIR cohort, so that I can assess whether the SBIR treatment effect on commercialization holds after controlling for vintage, NAICS sector, and firm geography.

---

Research-questions tags: **B2/B3** (commercialization), **A4** (private-capital signals),
**[L21]** (ITIF "America's Seed Fund"), **[L10]** (Lerner), **[L11]** (Howell), **[L23]** (Form D).

## Background

ITIF [L21] frames NSF SBIR as the federal analogue of a seed-stage venture fund.
Lerner [L10] and Howell [L11] establish empirically that SBIR awardees grow
faster, attract more follow-on private capital, and produce more patents than
matched non-awardees — but neither study uses a *private-capital cohort* as the
control group. This spec builds that comparison for the configured funding agency,
with NSF as the initial implementation target: how does the SBIR portfolio of
the configured agency perform on commercialization-outcome metrics relative to
firms financed via private capital (Reg D / Form D filers)?

The user-stated framing: "compare NSF SBIR portfolio rank against pre-seed/seed
VCs." Per scope review, we drop the "rank" composite and frame the deliverable
as a **comparison table with reconciliation narrative**, matching the pattern
established by `specs/archive/completed-features/follow-on-multiplier-analysis/`. Form D is intentionally
*not* filtered to seed-only — its broader coverage (debt, later-stage, multiple
instrument types) is treated as feature, not bug, because the policy question
is "what private-capital alternative would these firms otherwise rely on,"
not "what would seed VCs alone do."

## Reuse posture and source boundary

PR #286 (`claude/sbir-ma-exit-analysis`) supplied useful SBIR-focused SEC EDGAR
and Form D parsing, heuristic CIK matching, scoring tiers, and SBIR M&A signal
extraction. Relevant reusable code and artifacts include:

- `sbir_etl/enrichers/sec_edgar/{client,enricher,form_d_scoring}.py`;
- `sbir_etl/models/sec_edgar.py`;
- `packages/sbir-analytics/sbir_analytics/assets/sec_edgar_enrichment.py`; and
- `data/sbir_ma_events.jsonl`, which is SBIR-side M&A evidence.

Those outputs do **not** provide a maintained broad Form D control producer, a
complete authoritative SBIR-CIK resolution set, control-side M&A coverage, or a
PATLINK input for the Phase 2 scaffold. PR #286's heuristic matches can be reused
as candidate evidence, but they cannot define "never SBIR."

The bounded broad-universe prerequisite is now maintained separately by
`scripts/data/build_form_d_control_universe.py`. It consumes the SEC DERA
[quarterly Form D bulk data sets](https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets)
for the closed 2009Q1–2024Q4 window and pins sources and products in deterministic
manifests. The [official Form D](https://www.sec.gov/files/Form_D.pdf) and DERA
files provide SIC and Form D industry group, not NAICS.

## Phasing

This spec ships in two sequential phases, each independently useful.

- **Phase 1 — Published-baseline comparison.** Compute NSF SBIR cohort outcomes
  on metrics with cited public VC baselines. No new data ingest. Independent
  of PR #286.
- **Phase 2 — NSF-vs-private-capital matched cohort.** Build a validated
  high-recall SBIR identity exclusion over the maintained DERA issuer universe,
  establish validated matching covariates, then compute symmetric outcome
  deltas. PR #286 supplies only narrow reusable evidence, not these gates.

Phase 1 is the gating deliverable. Although #286 is now on main, the DERA staging
producer is maintained, and a Phase 2 scaffold exists, a real Phase 2 run remains
gated on Phase 1 sign-off and the missing identity, covariate, and symmetric
outcome contracts described above.

## Phase 1 Requirements

1. **SHALL** isolate the cohort for the configured funding agency using that
   agency's ALN(s) (e.g. NSF uses ALN `47.041` and `47.084`). NSF is the
   initial implementation target.
2. **SHALL** compute the following cohort outcomes, stratified by award
   vintage (5-year buckets) and Phase (I, II):
   - Phase I → Phase II graduation rate, firm-level and pooled across SBIR and
     STTR. Qualifying Phase II awards must be no earlier than Phase I and no
     later than the configured inclusive horizon (current Phase 1 review
     default: 5 years). The review artifact SHALL also report 2-year, 3-year,
     5-year, and unbounded sensitivity.
   - Phase II → first non-SBIR federal contract transition rate (reuse
     existing transition detector, ≥85% precision benchmark)
   - 5-year survival proxy (firm appears as recipient/vendor in any federal
     dataset 5 years post-Phase-II). Denominator is unique companies per
     stratum, not award rows.
   - M&A exit rate — reuses #286's SBIR-side `data/sbir_ma_events.jsonl` for
     this treated-only Phase 1 metric. The agency-filtered slice is a one-line
     join. Join is UEI/DUNS-first; falls back to normalized company name when
     UEI/DUNS are absent.
   - Patent rate — **deferred to Phase 2**. The asset does not accept
     PATLINK as an input in Phase 1; adding PATLINK is out of scope here.
3. **SHALL** present results alongside cited public private-capital and
   small-business baselines:
   - 5-year startup survival (BLS BED, public)
   - Lerner [L10] and Howell [L11] published effect sizes
   - ITIF [L21] qualitative framing
4. **SHALL** produce a reconciliation narrative explaining each delta between
   the cohort metric and the cited VC baseline, including selection-bias
   caveats ("NSF awardees pre-selected on technical merit and proposal
   quality; VC-financed firms self-select on lawyer access and growth
   narrative").
5. **SHOULD** stratify outcomes by CET technology area (reuse CET classifier)
   so the comparison is not blurred by sector mix.
6. **SHALL** resolve firms through an exact connected-component crosswalk over
   every UEI, DUNS, and versioned normalized-name alias present on their award
   rows, and report match rates plus UEI-backed, DUNS-only, name-only, and
   UEI↔DUNS bridge coverage as sensitivity metadata (mirrors
   `follow-on-multiplier-analysis` requirement 7).

### Phase 1 Gate Condition

Can produce a single artifact (notebook or markdown report) that states:
"BLS reports 5-year establishment survival at ~50%. NSF Phase II 5-year
survival proxy is [X]% on cohort [vintage range, n=Y]. The difference is
attributable to [Z]."
Reproduces the exact reconciliation pattern of `follow-on-multiplier-analysis`.

The [2026-08-09 NSF review artifact](../../docs/research/agency-private-capital-phase1-nsf.md)
validates the Phase I→II cohort component (672/1,502, or 44.7%, for 2015–2019)
and pins its inputs in a deterministic manifest. It does **not** close the gate:
the transition, survival, M&A, and patent channels were unavailable, and the
cohort estimand and identity approach still require review.

## Phase 2 Requirements

Phase 2 may reuse narrow PR #286 evidence, but its broad issuer source is the
pinned official DERA quarterly bulk collection. The current producer outputs
provisional identity staging only.

7. **SHALL** filter the observed SBIR award history to the configured agency
   (e.g. NSF: ALN 47.041 / 47.084), retain every historical organization name
   present there, and resolve the treated cohort through the validated
   higher-recall CIK/alias union. PR #286's heuristic matches are candidate
   evidence, not the complete treated identity set.
8. **SHALL** construct a defensible SBIR-excluded Form D control cohort. The
   partial implementation SHALL ingest the official DERA quarterly bulk ZIPs
   for the closed 2009Q1–2024Q4 window and emit deterministic manifests, a broad
   issuer universe, candidate exact-normalized-name SBIR-CIK exclusion evidence,
   and filtered disjoint identity-only controls. Exact comparison SHALL use every
   historical name present in the SBIR award history and
   `CompanyNameProfile.ORGANIZATION_KEY_V1`.
   While exclusion recall is unknown, the manifest SHALL state
   `complete_sbir_exclusion=false`; retained means only not exact-name-matched to
   observed SBIR history, not "never SBIR." Requirement 8 remains open until a
   higher-recall authoritative CIK/alias union is validated.

   A follow-on possible-contamination screen SHALL remain candidate-only unless
   an explicit adjudication record establishes the identity decision. Its
   deterministic manifest SHALL pin the provisional controls, current exact
   exclusions, SBIR award snapshot, name/geography policies, thresholds, and
   output hashes. Missing geography SHALL NOT count as agreement, candidate
   scores SHALL NOT automatically remove a CIK, and the screen SHALL preserve
   `complete_sbir_exclusion=false`, `exclusion_recall="unknown"`,
   `covariates_ready=false`, and `ready_for_matching=false`.
9. **SHALL** match the agency and eligible control cohorts on vintage year,
   validated NAICS-2, and state using coarsened-exact matching; no propensity
   scoring in v1. DERA supplies SIC and Form D industry group, not NAICS. The
   staging producer SHALL NOT infer NAICS and SHALL state
   `covariates_ready=false` until a validated SIC-to-NAICS-2 strategy exists.
   The existing matched asset SHALL refuse staging output while either gate is
   false. Document cohort sizes and balance only after both gates pass.
10. **SHALL** compute applicable outcomes symmetrically for treated and control
    cohorts: federal-contract presence, patent presence, and verified M&A exit
    rate. A common evaluator SHALL use the same exact identity, index date,
    inclusive follow-up horizon, event-date rule, and source-coverage rule for
    both arms. A covered firm with no in-window event is an observed zero;
    missing identity, missing or incomplete source coverage, and insufficient
    follow-up are unavailable and excluded from the denominator.

    The first implemented source contract is the exact CIK-native metric
    `form_d_business_combination_filing_proxy`, derived from the official Form D
    `ISBUSINESSCOMBINATIONTRANS` field with accession and filing-date provenance.
    It is a lower-bound transaction-financing filing proxy, not a verified
    acquisition or M&A exit, and does not satisfy the verified-M&A portion of
    this requirement. The current scaffold has no real FPDS or patent input,
    while #286's `sbir_ma_events.jsonl` contains SBIR-only M&A evidence and
    cannot establish control coverage. The matched asset SHALL NOT consume that
    SBIR-only file. Missing outcome inputs or coverage SHALL be reported as
    unavailable, never zero. Implement remaining source contracts in separate
    follow-on PRs. Survival proxy and Phase-graduation rates do not apply to
    controls and remain N/A.
11. **SHALL** publish a threats-to-validity section before any headline
    finding. Required entries: SAFE/convertible undercount, late-stage Form
    D inclusion, unknown exact-name exclusion recall, alias/rename/acquisition
    leakage, SIC-to-NAICS-2 mapping validity, technical-merit vs. lawyer-access
    selection bias, and control-cohort timing leakage.
12. **SHOULD** decompose results by Form D security-type (equity / debt /
    option / convertible) and offering-size buckets so downstream readers
    can zoom in on the noisy seed-stage subset if they want. Reuse #286's
    scoring tiers only after verifying that they apply to the DERA source schema.
13. **SHOULD** reproduce #286's published 1.82x SBIR-to-Form-D leverage
    ratio scoped to the configured agency only, as a cross-check on the
    dataset slice.

### Phase 2 Gate Condition

Can state: "On vintage [X], NAICS-2 [Y], state [Z]: the configured agency's
Phase II awardees transitioned to federal contract at [A]% within 5 years;
matched non-SBIR Form D issuers transitioned at [B]%. Selection-bias and
matching caveats below." The reconciliation matters more than the headline
number. This gate remains open; the provisional identity-only staging output is
not sufficient to evaluate it.

## Dependencies

- NSF identification (ALN 47.041 / 47.084) — `sbir_etl/models/sbir_identification.py` (EXISTS)
- Transition detection (≥85% precision) — `packages/sbir-ml/sbir_ml/transition/` (EXISTS)
- Entity resolution cascade — UEI/DUNS/CAGE/fuzzy-name (EXISTS)
- Phase 2 patent linkage — NOT WIRED; no PATLINK input is present in the scaffold
- CET classifier (EXISTS, used for Phase 1 stratification)
- Official SEC DERA quarterly Form D bulk data, pinned 2009Q1–2024Q4 — staging
  producer EXISTS; higher-recall exclusion and validated NAICS-2 do not
- **PR #286** — reusable SBIR-focused EDGAR/Form D parsing, heuristic CIK
  evidence, scoring tiers, and SBIR-side M&A events; not a complete Phase 2
  identity or outcome contract
- Authoritative CIK/alias union with demonstrated exclusion recall — MISSING
- Validated SIC-to-NAICS-2 strategy — MISSING
- Shared date-aware event/coverage evaluator — EXISTS
- Symmetric CIK-native Form D business-combination filing proxy — EXISTS;
  matched-risk-set integration remains gated
- Symmetric FPDS, patent, and verified M&A outcome inputs — MISSING

## Out of Scope

- Composite "portfolio rank" / scoring construct — explicitly rejected.
- Crunchbase / PitchBook integration (deferred to a future licensed-data spec).
- Causal-effect estimation. This spec is descriptive comparison only; any
  causal claims require IV / regression-discontinuity machinery beyond scope.
- Patent rate in Phase 1 — deferred to Phase 2 (the asset does not accept
  PATLINK as an input; adding it is out of scope for the current iteration).
- Re-implementation of PR #286's SBIR-focused EDGAR enrichment and scoring.
  The official DERA broad-universe producer and the missing authoritative
  identity, covariate, and symmetric outcome contracts are distinct follow-ons,
  not capabilities already delivered by #286.
