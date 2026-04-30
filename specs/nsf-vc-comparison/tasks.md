# NSF SBIR vs. Private-Capital Comparison — Tasks

Tasks are grouped by phase. Phase 1 ships independently. Phase 2 is gated on
Phase 1 + Form D ingest scope coordination with the M&A spec.

## Phase 1 — Published-Baseline Comparison

- [ ] 1.1 Add `NSFCohortBuilder` under `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/`.
  Filter award universe to ALN ∈ {47.041, 47.084}, stratify by vintage (5-yr
  buckets) + phase. Verify: cohort sizes match SBA annual report [L18] NSF
  totals within 5%.
- [ ] 1.2 Add `OutcomeMetricsCalculator` that reuses existing transition
  detector (`packages/sbir-ml/sbir_ml/transition/`) and PATLINK. Emits Wilson-
  CI-bounded rates per stratum. Verify: re-running on the leverage-ratio
  fixture set reproduces transition rates within tolerance.
- [ ] 1.3 Add `PublishedBaselineRegistry` — hard-coded YAML at
  `config/nsf_vc/published_baselines.yaml` with source citations + as-of
  dates. Initial entries: NVCA seed→A, BLS BED 5-yr survival, Lerner [L10]
  effect size, Howell [L11] follow-on-VC effect, ITIF [L21] framing claims.
- [ ] 1.4 Add `ReconciliationNarrative` writer. For each (NSF metric,
  baseline) pair, emit JSON record + markdown line. Mirror the structure
  of `LeverageRatioReconciler`.
- [ ] 1.5 Wire as a Dagster asset `nsf_vc_published_baseline_comparison`.
  Output artifacts: `nsf_cohort_outcomes.parquet`,
  `nsf_vs_published_baselines.md`, `nsf_baseline_comparison.json`.
- [ ] 1.6 Add unit tests under `tests/unit/nsf_vc/` covering: ALN filter
  correctness, Wilson CI math, baseline-registry loading, reconciliation
  record shape.
- [ ] 1.7 Add an integration test against a small NSF fixture (vintage 2015,
  Phase II, n≈100) verifying the full Phase 1 pipeline produces a
  reproducible report.
- [ ] 1.8 Phase 1 gate: produce the report, hand to user for review.
  Deliverable language: "NVCA reports seed→A graduation at ~33%. NSF Phase
  I→II graduation is [X]% on vintage 2015–2020 (n=Y). Difference is
  attributable to [Z]." Stop here for sign-off before Phase 2.

## Phase 2 — Form D Matched-Cohort Comparison

Coordinate Form D ingest scope with whoever owns
`specs/merger_acquisition_detection/` before starting; the ingest built here
is the canonical one.

- [ ] 2.1 Enable + implement the `sec_edgar` enrichment source already stubbed
  in `config/base.yaml`. Pull Form D submissions via EDGAR bulk archives
  (preferred) or full-text search API. Persist raw XML to
  `data/raw/sec_edgar/form_d/`.
- [ ] 2.2 Add `FormDParser` — XML → typed records (filer CIK, issuer name +
  address + state, NAICS, filing date, amount sold, total offering, security
  type, industry group, minimum-investment-accepted). Strict on schema
  violations; emit to AlertCollector.
- [ ] 2.3 Persist parsed records to a DuckDB staging table; verify schema
  contract with `sbir_etl/models/quality.py` patterns.
- [ ] 2.4 Build `CIKCrosswalk` — tiered EIN → name+state → fuzzy-name+state+
  city cascade. Each match record carries tier label + confidence.
- [ ] 2.5 Build a hand-labeled backtest set of 200 known SBIR-firm ↔ Form D
  issuer pairs (seed from PR #286 references and public NSF awardees with
  known financings). Compute Tier A+B precision and recall.
- [ ] 2.6 **Phase 2 gate-A:** crosswalk Tier A+B precision ≥0.95, recall
  ≥0.50, and per-vintage match rate ≥30%. If not met, stop-and-discuss
  with user before continuing.
- [ ] 2.7 Build `PrivateCapitalCohortBuilder` — drop Form D issuers matched
  to any SBIR awardee, bucket the remainder by (vintage-year, NAICS-2, state).
- [ ] 2.8 Build `CohortMatcher` — coarsened-exact matching of NSF and
  private-capital cohorts on (vintage, NAICS-2, state). Report balance and
  unmatched residuals.
- [ ] 2.9 Run `OutcomeMetricsCalculator` on the matched private-capital
  cohort (federal-contract transition is computable for any firm in FPDS;
  patents via PATLINK; M&A via M&A spec output if available, else placeholder).
- [ ] 2.10 Build `ThreatsToValidity` gate — required entries: SAFE/convertible
  undercount, late-stage inclusion, NAICS self-report noise, CIK↔UEI
  crosswalk floor, technical-merit vs. lawyer-access selection bias. Headline
  artifact is suppressed if any entry is missing or stale.
- [ ] 2.11 Wire Phase 2 as a Dagster asset
  `nsf_vc_form_d_matched_comparison`. Output artifacts:
  `form_d_filings.parquet`, `cik_uei_crosswalk.parquet`,
  `private_capital_cohort_outcomes.parquet`, `nsf_vs_form_d_comparison.md`,
  `threats_to_validity.json`.
- [ ] 2.12 Add security-type decomposition view (Form D cohort split by
  equity / debt / convertible / option) so downstream readers can isolate
  the noisy seed-stage subset.
- [ ] 2.13 Add unit + integration tests under `tests/unit/nsf_vc/` and
  `tests/integration/nsf_vc/`. Integration test on a small EDGAR fixture
  set (≤50 filings) verifying parser + crosswalk + cohort builder.
- [ ] 2.14 Phase 2 gate: produce the cohort-vs-cohort report. Deliverable
  language: "On vintage [X], NAICS-2 [Y], state [Z]: NSF Phase II
  awardees transitioned to federal contract at [A]% within 5 years; matched
  Form D issuers transitioned at [B]%. Caveats below." Hand to user for
  review.

## Cross-Phase Tasks

- [ ] X.1 Add `docs/nsf-vc-comparison/` with methodology, glossary, and
  citation table (mirrors `docs/transition/`).
- [ ] X.2 Update `docs/research-questions.md` to cite this spec under B2/B3
  and A4 (do not invent a new question — annotate existing ones).
- [ ] X.3 After Phase 2 ships, evaluate whether to extend to DoD / NIH / DOE
  using the same machinery (separate spec, not in this scope).
