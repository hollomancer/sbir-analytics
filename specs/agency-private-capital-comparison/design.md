# SBIR vs. Private-Capital Comparison — Design (agency-parameterized; NSF as initial target)

## Architecture

Builds on existing SBIR identification, transition detection, and entity-resolution
pipelines, with narrow reuse of the SBIR-focused SEC EDGAR / Form D / M&A
infrastructure landed by PR #286. PR #286 did not deliver a maintained broad
control producer, a complete SBIR-CIK set, or a Phase 2 PATLINK input. New code
lives in `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/`
(an outcomes-comparison artifact, parallel to `follow_on_multiplier/`).

## Phase 1 — Published-Baseline Comparison

### Data Flow

```
SBIR.gov awards → filter by agency_code (default NSF: ALN ∈ {47.041, 47.084})
                                                       ↓
                                          agency cohort
                                                       ↓
                                          stratify by vintage / phase / CET
                                                       ↓
                                          compute outcome metrics:
                                              - I → II graduation
                                              - II → federal-contract transition
                                              - 5-yr survival proxy
                                              - M&A exit rate (#286 join)
                                              - patent rate (Phase 2 only)
                                                       ↓
                                          present alongside cited published baselines
                                                       ↓
                                          reconciliation narrative
```

### Components

1. **`AgencyCohortBuilder`** — Filters award universe to the configured funding
   agency (default: NSF), stratifies by vintage / phase, attaches CET labels.
   NSF is the initial implementation target; other agencies work via the
   `agency_code` parameter.
2. **`OutcomeMetricsCalculator`** — Reuses existing transition detector and
   #286's `sbir_ma_events.jsonl` for the M&A-exit metric. Emits per-cohort
   rates with Wilson confidence intervals and sample sizes. The firm-level
   graduation identity is an exact connected component across every UEI, DUNS,
   and `ORGANIZATION_KEY_V1` name alias on the award rows. Its inclusive
   follow-up horizon is run configuration (default 5 years; `None` restores
   unbounded behavior), and the review artifact reports 2/3/5/unbounded
   sensitivity. Five-year survival denominator is unique companies (not award
   rows). M&A joins against every alias on the same resolved component.
3. **`PublishedBaselineRegistry`** — Hard-coded table of cited private-capital
   and small-business baselines with source citation + as-of date. These
   baselines are agency-agnostic. Examples:
   - BLS BED: ~50% 5-yr survival, all small firms
   - Lerner [L10]: SBIR awardees grew 27% faster over 10 yrs (effect size)
   - Howell [L11]: early-stage SBIR roughly doubles subsequent-VC probability
4. **`ReconciliationNarrative`** — For each (agency metric, baseline) pair,
   emit a structured comparison record: delta, plausible-cause attribution,
   selection-bias caveat. Output as JSON + markdown, mirroring the
   follow-on-multiplier reconciler.

### Output (under `data/processed/agency_private_capital/<agency_lower>/`)

- `agency_cohort_outcomes.parquet` — long-format metrics table (vintage × phase
  × CET × metric)
- `agency_vs_published_baselines.md` — human-readable reconciliation narrative
- `agency_baseline_comparison.json` — structured comparison records

## Phase 2 — NSF-vs-Private-Capital Matched Cohort

Phase 2 remains gated on Phase 1 sign-off, higher-recall identity exclusion,
validated matching covariates, and symmetric outcomes. It is not a pure analysis
layer over PR #286: the broad issuer universe comes from the maintained official
SEC DERA quarterly bulk source, and PR #286's SBIR-focused CIK evidence is not a
complete resolution set.

### Data Flow

```
Official SEC DERA Form D:                 SBIR awards:
  quarterly ZIPs, 2009Q1–2024Q4             all historical company names
       ↓                                          ↓
broad issuer staging universe            ORGANIZATION_KEY_V1 exact keys
       ↓                                          ↓
candidate exact-name SBIR-CIK exclusion evidence
       ↓
filtered disjoint identity-only controls
  complete_sbir_exclusion=false
  covariates_ready=false
       ↓
       STOP: matched asset must not consume staging
       ↓ after future gates
higher-recall authoritative CIK/alias union + validated SIC→NAICS-2 strategy
       ↓                                          ↓
eligible controls                         configured-agency treated cohort
       ↓                                          ↓
                cohort matching (coarsened-exact)
                        ↓
              symmetric outcome contracts:
                - federal-contract presence (both sides; not yet wired)
                - patent presence (both sides; not yet wired)
                - Form D business-combination filing proxy (CIK-native adapter)
                - verified M&A exit rate (both sides; evidence absent)
                - Phase graduation / survival (agency only, control N/A)
                        ↓
              cohort-vs-cohort delta + threats-to-validity
```

### Components

5. **`AgencyAwardeeFilter`** — Apply the configured agency's ALNs (NSF initially:
   47.041 / 47.084) to the observed SBIR award history, preserve every historical
   organization name present there, and later join to the validated authoritative
   CIK/alias union. Output agency CIK and UEI sets with provenance. PR #286's
   heuristic resolution is candidate evidence, not the canonical complete set.
6. **`PrivateCapitalControlCohortBuilder`** — The bounded prerequisite is
   partially implemented as `scripts/data/build_form_d_control_universe.py`.
   It reads official SEC DERA quarterly Form D bulk ZIPs over the closed
   2009Q1–2024Q4 window and emits deterministic manifests plus:

   - the broad issuer universe;
   - candidate SBIR-CIK exclusion evidence from exact equality after normalizing
     every historical name present in the SBIR award history and all issuer
     names with `CompanyNameProfile.ORGANIZATION_KEY_V1`; and
   - filtered, disjoint identity-only control staging.

   Exact-name exclusion recall is unknown. The manifest therefore states
   `complete_sbir_exclusion=false`; retained means only not exact-name-matched to
   observed SBIR history, not "never SBIR." DERA supplies SIC and Form D industry
   group, not NAICS. The producer performs no NAICS inference and states
   `covariates_ready=false`. Component 6 remains open until a higher-recall
   authoritative CIK/alias union and validated SIC-to-NAICS-2 strategy exist.

   A separate possible-contamination audit screens the provisional retained CIKs
   against every historical SBIR name and the Form D alias/location evidence.
   Its frozen retrieval rules combine near-exact name similarity with state or
   ZIP corroboration and emit a compact review queue. Those rows are candidates,
   not identity decisions: the audit applies no automatic exclusion, preserves
   the original controls, and keeps `complete_sbir_exclusion=false`,
   `exclusion_recall="unknown"`, and `ready_for_matching=false`. Fuzzy evidence
   can prioritize adjudication but cannot establish that a retained firm has no
   SBIR exposure.
7. **`CohortMatcher`** — Coarsened-exact matching on (vintage-year,
   validated NAICS-2, state). Reports cohort balance and unmatched residuals.
   No propensity scoring in v1. The existing asset must reject component 6's
   staging output while either manifest gate is false.
8. **Symmetric outcome contract** —
   `symmetric_event_coverage.evaluate_event_presence` applies one date-aware
   evaluator to both arms. Every risk-set firm has an exact namespaced identity
   and index date; every source supplies traceable dated events plus an explicit
   coverage interval and snapshot. A covered firm with no event in the inclusive
   horizon is an observed zero. Missing identity, missing/incomplete source
   coverage, and insufficient follow-up are unavailable and stay out of the
   denominator.

   The first adapter, `scripts/data/build_form_d_business_combination_events.py`,
   reads the audited DERA issuer universe and emits CIK-native evidence for the
   exact metric `form_d_business_combination_filing_proxy`. It preserves filing
   accession, filing date, quarter, and amendment lineage. This is a lower-bound
   filing proxy for offerings associated with a business-combination transaction;
   it is not a verified acquisition or M&A-exit event. FPDS, patent, and verified
   M&A adapters remain separate follow-ons. The matched asset continues to mark
   the proxy unavailable until an eligible matched risk set and the symmetric
   event/coverage artifacts are supplied.

   The patent follow-on starts one layer below study outcomes. A local
   `PVGPATDIS` contract validates exactly three pinned roles
   (`g_assignee_disambiguated`, `g_patent`, and `g_application`) and reduces
   them to deterministic, assignee-native `patent_grant` events. The source
   release ID is content-derived and independent of local paths, download
   timestamps, and manifest ordering. A separate minimal bridge contract may
   emit exact-name evidence only as `candidate` or `ambiguous`. It cannot emit
   accepted links, firm coverage, availability, denominators, or rates. Bulk
   acquisition, production-scale materialization, real bridge review, and the
   five-year patent outcome adapter remain separate work.
9. **`ThreatsToValidity`** — Emits the structured caveats record. Required
   entries:
   - SAFE/convertible undercount (Form D weak on these)
   - Late-stage Form D inclusion (we are intentionally broader than seed)
   - Unknown recall of exact-name SBIR-CIK exclusion, including aliases and renames
   - Validity of the future SIC-to-NAICS-2 mapping
   - Technical-merit vs. lawyer-access selection bias
   - Control-cohort timing leakage

   This component runs *first* and gates the headline output — if any
   required caveat is missing or stale, the headline is suppressed.

### Target output

These are target outputs after the identity, covariate, and outcome gates pass;
the provisional staging producer must not trigger them.

- `agency_vs_form_d_comparison.parquet` — long-format cohort-vs-cohort metrics
- `agency_vs_form_d_matched_pairs.parquet` — matched treated-control rows
- `agency_vs_form_d_comparison.md` — headline reconciliation narrative
- `match_balance.json` — cohort balance and unmatched residuals
- `threats_to_validity.json` — gating caveats record

## Methodology Notes

### Why Form D, not seed-VC-only

Per user direction: broader Form D coverage (debt, late-stage, multiple
instrument types) is treated as feature. The framing is "private capital
broadly" rather than "seed VC narrowly." This makes the comparison more
robust to SAFE undercount (a seed-stage-specific blind spot) at the cost
of a coarser instrument mix. The DERA source provides SIC and Form D industry
group, not NAICS. PR #286's Form D scoring tiers may be exposed to downstream
readers only after their compatibility with the DERA schema is verified.

### Why no propensity scoring in v1

Coarsened-exact matching is reproducible, debuggable, and matches the
conservative tone of the follow-on-multiplier spec. Propensity scoring requires
firm-level covariates that don't reliably exist on the Form D side
(founding date, founder background, prior funding). Defer to a v2 if v1
yields a publishable result.

### Why no causal claim

The user asked for a comparison; the scope-guard flagged that NSF-vs-
private selection bias is severe and one-way. We deliberately frame the
deliverable as "descriptive comparison with reconciliation narrative" —
same posture as `follow-on-multiplier-analysis`. Causal claims (e.g., "NSF
SBIR causes N% higher transition than private capital would have")
require RDD or IV designs and are out of scope.

### Why exact-name staging is not the identity contract

The staging producer deliberately uses one auditable rule:
`CompanyNameProfile.ORGANIZATION_KEY_V1` followed by exact equality. That rule
produces useful candidate exclusion evidence and disjoint included/excluded CIK
sets, but it misses aliases, renames, acquisitions, and other identity changes.
PR #286's heuristic matching also does not establish complete recall. Phase 2
therefore needs a separately validated, higher-recall authoritative CIK/alias
union before it may call an issuer SBIR-excluded. Whether that union extends
`VendorCrosswalk` or another identity component is a follow-on design decision.

## Risks

- **False control eligibility**: exact normalized-name exclusion has unknown
  recall. Aliases, renames, and acquisitions can leave historical SBIR firms in
  staging. Do not consume it until the authoritative union is validated.
- **Covariate incompatibility**: DERA has SIC and Form D industry group, not
  NAICS. A convenient unvalidated mapping would change the match estimand. Keep
  `covariates_ready=false` until the SIC-to-NAICS-2 strategy passes validation.
- **Outcome asymmetry**: FPDS, patent, and verified M&A inputs are absent. The
  CIK-native Form D filing proxy has symmetric source coverage only for firms
  resolved to Form D CIKs and must not be relabeled as acquisition or exit.
  Missing evidence or incomplete follow-up must remain unavailable, not zero.
- **NSF cohort size**: NSF SBIR is smaller than DoD; vintage-stratified
  Wilson intervals may be wide. Pre-register minimum cohort size (n=50
  per stratum) before reporting stratified rates.
- **Form D control cohort dwarfs NSF cohort**: many more Form D filers
  than NSF awardees. Matched-cohort reporting must match 1:k or use
  weighting; document explicitly.
- **Timing leak in control cohort**: Form D issuers may have filed after receiving
  SBIR. The target authoritative union excludes any observed historical SBIR
  identity; the provisional exact-name stage cannot claim that coverage.
