# SBIR vs. Private-Capital Comparison — Tasks (agency-parameterized; NSF as initial target)

Tasks are grouped by phase. Phase 1 ships independently of PR #286.
Phase 2 starts after PR #286 merges to main and this branch rebases.

## Phase 1 — Published-Baseline Comparison

- [ ] 1.1 Add `AgencyCohortBuilder` under
  `packages/sbir-analytics/sbir_analytics/assets/agency_vc/`. Filter award
  universe to the configured agency (default NSF: ALN ∈ {47.041, 47.084}),
  stratify by vintage (5-yr buckets) + phase. Verify: cohort sizes match
  SBA annual report [L18] NSF totals within 5%.
- [ ] 1.2 Add `OutcomeMetricsCalculator` that reuses the existing transition
  detector (`packages/sbir-ml/sbir_ml/transition/`). Emits Wilson-CI-bounded
  rates per stratum. M&A exit rate consumes #286's `data/sbir_ma_events.jsonl`
  directly (post-rebase); join is UEI/DUNS-first with normalized-name fallback.
  Five-year survival denominator is unique companies, not award rows. Verify:
  re-running on the leverage-ratio fixture set reproduces transition rates
  within tolerance.
- [ ] 1.3 Add `PublishedBaselineRegistry` — hard-coded YAML at
  `config/agency_vc/published_baselines.yaml` with source citations + as-of
  dates. Initial entries: NVCA seed→A, BLS BED 5-yr survival, Lerner [L10]
  effect size, Howell [L11] follow-on-VC effect, ITIF [L21] framing claims.
  These baselines are agency-agnostic VC-industry data; one file for all
  agencies.
- [ ] 1.4 Add `ReconciliationNarrative` writer. For each (agency metric,
  baseline) pair, emit JSON record + markdown line. Mirror the structure
  of the existing leverage-ratio reconciler.
- [ ] 1.5 Wire as a Dagster asset `agency_vc_published_baseline_comparison`
  with `AgencyVCConfig` (agency_code, default "NSF"). Output artifacts:
  `agency_cohort_outcomes.parquet`, `agency_vs_published_baselines.md`,
  `agency_baseline_comparison.json` under
  `data/processed/agency_vc/<agency_lower>/`.
- [ ] 1.6 Add unit tests under `tests/unit/agency_vc/` covering: ALN filter
  correctness (NSF and NIH variants), Wilson CI math, baseline-registry
  loading, reconciliation record shape.
- [ ] 1.7 Add an integration test against a small NSF fixture (vintage 2015,
  Phase II, n≈100) verifying the full Phase 1 pipeline produces a
  reproducible report.
- [ ] 1.8 **Phase 1 gate:** produce the report, hand to user for review.
  Deliverable language: "NVCA reports seed→A graduation at ~33%. NSF Phase
  I→II graduation is [X]% on vintage 2015–2020 (n=Y). Difference is
  attributable to [Z]." Stop here for sign-off before Phase 2.
  Note: patent_rate is deferred to Phase 2 (the configured funding agency,
  with NSF as the initial implementation target, does not wire PATLINK in
  Phase 1).

## Phase 2 — Agency-vs-Private-Capital Matched Cohort

**Prerequisite:** PR #286 merged to main; this branch rebased on top.
Verify post-rebase that #286's Dagster asset names and JSONL schema
haven't drifted; if they have, fix the dependency references in tasks
2.1–2.4 before continuing.

- [ ] 2.1 Add `AgencyAwardeeFilter` — apply the configured agency's ALN(s)
  (e.g. NSF: 47.041 / 47.084) to #286's resolved SBIR-CIK set produced by
  `sec_edgar_enrichment`. Output: agency-CIK set + agency-UEI set, persisted
  as parquet.
- [ ] 2.2 Add `PrivateCapitalControlCohortBuilder` — read #286's Form D
  index, drop issuers whose CIK appears in the broader SBIR-CIK set
  (control = capital-financed firms with no SBIR exposure ever). Bucket
  by (filing-year, NAICS-2, state).
- [ ] 2.3 Add `CohortMatcher` — coarsened-exact matching on (vintage,
  NAICS-2, state). Report balance and unmatched residuals. Document
  matching ratio (agency firm : k matched controls) in the output.
- [ ] 2.4 Add `MatchedCohortOutcomes` — join both cohorts to FPDS
  contracts, PATLINK patents, and #286's `sbir_ma_events.jsonl`. Emit
  per-cohort rates with Wilson CIs. Reuse Phase 1's `OutcomeMetricsCalculator`
  where applicable; phase-graduation and survival metrics are agency-cohort-
  only (control N/A).
- [ ] 2.5 Add `ThreatsToValidity` gate — required entries: SAFE/convertible
  undercount, late-stage Form D inclusion, NAICS self-report noise, #286
  CIK-recall floor, technical-merit vs. lawyer-access selection bias,
  control-cohort timing-leak. Headline artifact suppressed if any entry
  is missing or stale.
- [ ] 2.6 Wire Phase 2 as a Dagster asset
  `agency_vc_form_d_matched_comparison`. Output artifacts:
  `agency_vs_form_d_comparison.parquet`, `agency_vs_form_d_comparison.md`,
  `threats_to_validity.json`.
- [ ] 2.7 Add security-type / offering-size decomposition view (uses #286's
  Form D scoring tiers directly). Cross-check by reproducing #286's
  published 1.82x SBIR-to-Form-D leverage ratio scoped to the configured
  agency only.
- [ ] 2.8 Add unit + integration tests under `tests/unit/agency_vc/` and
  `tests/integration/agency_vc/`. Integration test reuses #286's existing
  fixtures where available.
- [ ] 2.9 **Phase 2 gate:** produce cohort-vs-cohort report. Deliverable
  language: "On vintage [X], NAICS-2 [Y], state [Z]: NSF Phase II awardees
  transitioned to federal contract at [A]% within 5 years; matched
  non-SBIR Form D issuers transitioned at [B]%. Caveats below." Hand to
  user for review.

## Cross-Phase Tasks

- [ ] X.1 Add `docs/agency-vc-comparison/` with methodology, glossary, and
  citation table (mirrors `docs/transition/`).
- [ ] X.2 Update `docs/research-questions.md` to cite this spec under B2/B3
  and A4 (do not invent a new question — annotate existing ones).
- [ ] X.3 After Phase 2 ships with NSF, extend to DoD / NIH / DOE by passing
  a different `agency_code` — no new spec required, just parametrize.

## Removed Tasks (vs. earlier draft)

The following tasks were in the prior draft but are **no longer needed**
because PR #286 delivers them. Listed here for reviewer visibility:

- ~~Add `sec_edgar` enrichment source~~ — done in #286 (`sbir_etl/enrichers/sec_edgar/`).
- ~~Form D parser~~ — done in #286 (`form_d_scoring.py`, `fetch_form_d_*.py`).
- ~~Form D DuckDB staging~~ — done in #286.
- ~~CIK ↔ UEI/EIN crosswalk~~ — done in #286 (3-layer filter + city co-occurrence).
- ~~Crosswalk backtest set + precision/recall gate~~ — done in #286
  (validated against Physical Optics→Mercury, RMD→Dynasil, Coherent
  Tech→Lockheed).
- ~~Match-rate ≥30% gate~~ — #286 reports ~28% of SBIR companies have any
  EDGAR presence; documented as a threats-to-validity entry rather than
  a hard gate (the gate concept is moot once we're consuming a fixed
  upstream artifact).
- ~~Form D ingest scope coordination with M&A spec~~ — moot; #286
  consolidates both M&A and Form D under one PR.
- ~~NSF-only scope~~ — module renamed from `nsf_vc/` to `agency_vc/`;
  all code now accepts `agency_code` parameter (default "NSF"). The
  configured funding agency, with NSF as the initial implementation target,
  can now be extended to DoD / NIH / DOE without a separate spec.
