# SBIR vs. Private-Capital Comparison — Tasks (agency-parameterized; NSF as initial target)

> **Status (2026-08-09):** Phase 1 implemented — cohort/outcomes/baselines/reconciliation modules and the
> `agency_private_capital_baseline_comparison` Dagster asset live in
> `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/`, with unit tests
> (`tests/unit/agency_private_capital/`) and an integration test (`tests/integration/agency_private_capital/`).
> A pinned NSF real-data report now exists for Phase 1 review. It remains
> non-citable and unsigned because the cohort estimand and identity handling
> require review and four outcome channels are unavailable. A maintained SEC
> DERA CLI now stages a
> bounded Form D identity universe, but its manifest correctly reports
> `complete_sbir_exclusion=false` and `covariates_ready=false`. Phase 2 remains
> open until higher-recall identity exclusion, validated matching covariates,
> and symmetric FPDS/patent/M&A outcomes are wired and validated.

Tasks are grouped by phase. Phase 1 ships independently of PR #286. Phase 2 is
gated on Phase 1 sign-off and its missing real-data input contracts.

## Phase 1 — Published-Baseline Comparison

- [x] 1.1 Add `AgencyCohortBuilder` under
  `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/`. Filter award
  universe to the configured agency (default NSF: ALN ∈ {47.041, 47.084}),
  stratify by vintage (5-yr buckets) + phase. Verify: cohort sizes match
  SBA annual report [L18] NSF totals within 5%.
  — implemented: `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/cohort.py`
  (ALN-first + agency-name fallback matching, 5-yr `vintage_bucket`, `stratum_counts`)
- [x] 1.2 Add `OutcomeMetricsCalculator` that reuses the existing transition
  detector (`packages/sbir-ml/sbir_ml/transition/`). Emits Wilson-CI-bounded
  rates per stratum. M&A exit rate consumes #286's `data/sbir_ma_events.jsonl`
  directly (post-rebase); join is UEI/DUNS-first with normalized-name fallback.
  Five-year survival denominator is unique companies, not award rows. Verify:
  re-running on the follow-on-multiplier fixture set reproduces transition rates
  within tolerance.
  — implemented: `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/outcomes.py`
  (`wilson_interval`, consumes upstream transition scores, exact connected-component
  UEI/DUNS/name identity crosswalk, company-level survival denominator, configurable
  graduation horizon)
- [x] 1.3 Add `PublishedBaselineRegistry` — hard-coded YAML at
  `config/agency_private_capital/published_baselines.yaml` with source citations + as-of
  dates. Initial entries: BLS BED 5-yr survival, Lerner [L10] effect size,
  Howell [L11] follow-on-VC effect, ITIF [L21] framing claims.
  These baselines are agency-agnostic; one file for all
  agencies.
  — implemented: `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/baselines.py`
  + `config/agency_private_capital/published_baselines.yaml` (all 4 cited entries)
- [x] 1.4 Add `ReconciliationNarrative` writer. For each (agency metric,
  baseline) pair, emit JSON record + markdown line. Mirror the structure
  of the existing follow-on-multiplier reconciler.
  — implemented: `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/reconcile.py`
  (per-pair attribution + caveat tables, JSON records via `to_json`, markdown via `to_markdown`)
- [x] 1.5 Wire as a Dagster asset `agency_private_capital_baseline_comparison`
  with `AgencyPrivateCapitalConfig` (agency_code, default "NSF"). Output artifacts:
  `agency_cohort_outcomes.parquet`, `agency_vs_published_baselines.md`,
  `agency_baseline_comparison.json` under
  `data/processed/agency_private_capital/<agency_lower>/`.
  — implemented: `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/asset.py`
  (asset + config + all three artifacts, auto-discovered by `definitions.py`)
- [x] 1.6 Add unit tests under `tests/unit/agency_private_capital/` covering: ALN filter
  correctness (NSF and NIH variants), Wilson CI math, baseline-registry
  loading, reconciliation record shape.
  — implemented: `tests/unit/agency_private_capital/` (`test_cohort.py`, `test_outcomes.py`,
  `test_baselines.py`, `test_reconcile.py`)
- [x] 1.7 Add an integration test against a small NSF fixture (vintage 2015,
  Phase II, n≈100) verifying the full Phase 1 pipeline produces a
  reproducible report.
  — implemented: `tests/integration/agency_private_capital/test_phase1_pipeline.py`
  (vintage-2015 NSF fixture; artifact-production + reproducibility tests)
- [ ] 1.8 **Phase 1 gate:** produce the report, hand to user for review.
  Deliverable language: "BLS reports 5-year establishment survival at ~50%.
  NSF Phase II 5-year survival proxy is [X]% on vintage 2015–2020 (n=Y).
  Difference is attributable to [Z]." Stop here for sign-off before Phase 2.
  Note: patent_rate is deferred to Phase 2 (the configured funding agency,
  with NSF as the initial implementation target, does not wire PATLINK in
  Phase 1).
  **Review artifact materialized 2026-08-09:**
  [NSF Phase I baseline review](../../docs/research/agency-private-capital-phase1-nsf.md)
  reports 672/1,502 (44.7%, 95% Wilson interval 42.2%–47.3%) for the 2015–2019
  vintage with a five-year horizon. The repaired artifact also records
  2/3/5/unbounded sensitivity, UEI/DUNS/name coverage, and output hashes. Keep
  this task open until the estimand and identity approach are accepted and the
  required missing outcome channels are resolved.

## Phase 2 — Agency-vs-Private-Capital Matched Cohort

**Prerequisite:** Phase 1 sign-off. PR #286 is on main and the Phase 2 code
scaffold is present. `scripts/data/build_form_d_control_universe.py` now stages
the closed 2009Q1–2024Q4 official SEC DERA quarterly Form D universe with
deterministic manifests. That output is identity-only and is not ready for the
matched asset: exact normalized-name exclusion has unknown recall, and DERA
provides SIC and Form D industry group rather than NAICS. The scaffold also does
not provide symmetric real FPDS/patent/M&A outcome joins for treated and control
firms. Keep tasks 2.1–2.9 open until their acceptance criteria are demonstrated
on a pinned real-data run.

- [ ] 2.1 Complete and validate `AgencyAwardeeFilter` — apply the configured agency's ALN(s)
  (e.g. NSF: 47.041 / 47.084) across the observed SBIR award history, preserve
  every historical organization name present there, and join it to the
  validated higher-recall CIK/alias union required by task 2.2. Output the
  agency CIK and UEI sets with provenance; do not treat PR #286's heuristic
  matches as a complete resolved set.
- [ ] 2.2 Complete `PrivateCapitalControlCohortBuilder` — **OPEN / PARTIAL
  (2026-08-10).** The maintained CLI now consumes the official SEC DERA
  quarterly bulk ZIPs for the pinned 2009Q1–2024Q4 window and emits: (a) the
  broad issuer universe; (b) candidate SBIR-CIK exclusion evidence from exact
  equality of every historical name present in the SBIR award history and issuer
  names normalized with `CompanyNameProfile.ORGANIZATION_KEY_V1`; and (c)
  filtered, disjoint identity-only controls. Its manifest states
  `complete_sbir_exclusion=false` and `covariates_ready=false`. Retained issuers
  are only not exact-name-matched to observed SBIR history; they are not proven
  to have "no SBIR exposure ever."
  Keep this task open until a higher-recall authoritative CIK/alias union and a
  validated SIC-to-NAICS-2 strategy exist. The pinned
  [real-data identity audit](../../docs/research/agency-private-capital-form-d-control-universe.md)
  materialized 311,809 issuer CIKs and 307,344 provisional retained identities;
  those are audit counts, not a matched cohort.
  The focused
  [identity-crosswalk spec](../sbir-form-d-identity-crosswalk/) now defines the
  atomic awardee-CIK candidate prerequisite. Its exact-name edges remain
  unreviewed and do not yet close this task.
- [ ] 2.3 Complete and validate `CohortMatcher` — coarsened-exact matching on (vintage,
  validated NAICS-2, state). Report balance and unmatched residuals. Document
  matching ratio (agency firm : k matched controls) in the output. The existing
  matched asset must fail closed on the staging universe while
  `complete_sbir_exclusion` or `covariates_ready` is false.
- [ ] 2.4 Complete `MatchedCohortOutcomes` — join both cohorts to FPDS
  contracts, patent evidence, and symmetric M&A evidence. Emit per-cohort rates
  with Wilson CIs. Reuse Phase 1's `OutcomeMetricsCalculator` where applicable;
  phase-graduation and survival metrics are agency-cohort-only (control N/A).
  The current scaffold has no real FPDS or patent input, and #286's
  `sbir_ma_events.jsonl` is SBIR-only rather than control coverage. Record those
  outcomes as unavailable, never zero. Add the symmetric outcome contracts in
  separate follow-on PRs.
- [ ] 2.5 Complete the `ThreatsToValidity` gate — required entries: SAFE/convertible
  undercount, late-stage Form D inclusion, incomplete SBIR-CIK exclusion,
  SIC-to-NAICS-2 mapping validity, technical-merit vs. lawyer-access selection
  bias, and control-cohort timing leak. Headline artifact suppressed if any
  entry is missing or stale.
- [ ] 2.6 Harden the existing Phase 2 Dagster asset
  `agency_private_capital_form_d_matched_comparison`. It must not consume the
  provisional identity-only control output. Target output
  artifacts: `agency_vs_form_d_comparison.parquet`,
  `agency_vs_form_d_comparison.md`, `threats_to_validity.json`.
- [ ] 2.7 Add security-type / offering-size decomposition view. Reuse #286's
  Form D scoring tiers only after verifying compatibility with the DERA schema.
  Cross-check by reproducing #286's published 1.82x SBIR-to-Form-D leverage
  ratio scoped to the configured agency only.
- [ ] 2.8 Extend the unit + integration scaffold tests under
  `tests/unit/agency_private_capital/` and
  `tests/integration/agency_private_capital/` to exercise the validated real
  input contracts. Reuse #286's fixtures only where their source boundary is
  applicable.
- [ ] 2.9 **Phase 2 gate:** produce cohort-vs-cohort report. Deliverable
  language: "On vintage [X], NAICS-2 [Y], state [Z]: NSF Phase II awardees
  transitioned to federal contract at [A]% within 5 years; matched
  non-SBIR Form D issuers transitioned at [B]%. Caveats below." Hand to
  user for review.

## Cross-Phase Tasks

- [ ] X.1 Add `docs/agency-private-capital-comparison/` with methodology, glossary, and
  citation table (mirrors `docs/transition/`).
- [ ] X.2 Update `docs/research-questions.md` to cite this spec under B2/B3
  and A4 (do not invent a new question — annotate existing ones).
- [ ] X.3 After Phase 2 ships with NSF, extend to DoD / NIH / DOE by passing
  a different `agency_code` — no new spec required, just parametrize.

## Existing infrastructure and remaining gaps

PR #286 supplied useful SBIR-focused SEC EDGAR/Form D parsing, heuristic CIK
matching, scoring tiers, and SBIR M&A signal extraction. Its artifacts do not
constitute a maintained broad control-universe producer, a complete resolved
SBIR-CIK set, control-side M&A coverage, or a Phase 2 patent input.

- The maintained official-quarterly DERA producer in task 2.2 is a distinct,
  bounded prerequisite. Its exact-name exclusions remain provisional.
- A higher-recall authoritative CIK/alias union and its precision/recall
  validation remain open; a few known-company spot checks cannot close them.
- FPDS, patent, and M&A evidence must be made symmetric in separate PRs before
  outcome deltas are computed.
- The agency parameterization is already present: `agency_code` defaults to
  `"NSF"` and can later support DoD, NIH, or DOE without a separate spec.
