# Specification Status Registry

Reviewed: 2026-08-03

This registry is the cleanup checkpoint for top-level specs. It does not replace
the requirements, design, or tasks files; it records whether a spec is a current
implementation target, a gated backlog item, a deferred design, or an archive
candidate. Use `docs/research-questions.md` as the scope gate before promoting
any gated or deferred spec back into active work.

The repository-hygiene guard requires every top-level feature spec to appear in
this registry. That coverage check prevents new spec directories from silently
bypassing lifecycle review; the status and rationale still require human judgment.

## Status Categories

- **Active:** current implementation or cleanup work can proceed from the spec.
- **Maintenance:** core behavior is mostly implemented; remaining work is test,
  documentation, or small cleanup.
- **Gated backlog:** valid research question, but do not implement until the
  named prerequisite or priority decision is satisfied.
- **Deferred:** keep for historical or future context; do not implement as part
  of normal cleanup work.
- **Archive candidate:** move under `specs/archive/` after any live docs are
  updated to point at the archived path.

## Top-Level Specs

- **`actions-migration-followups` — Maintenance.** Setup verification and the
  blocking security scan are restored. The remaining decisions concern periodic
  scanning and whether the large pre-existing Markdown-formatting backlog is worth
  addressing; do not restore the old broad lint job by default.
- **`agency-private-capital-comparison` — Active.** The NSF Phase 1 real-data
  gate is materialized for review but remains non-citable and unsigned. Phase 2
  now has a maintained, deterministic 2009Q1–2024Q4 SEC DERA Form D staging
  producer, but task 2.2 remains open: exact-name SBIR exclusion has unknown
  recall (`complete_sbir_exclusion=false`), DERA has no NAICS and the staging
  covariates are not ready (`covariates_ready=false`), and the existing matched
  asset refuses to consume it (see below). Phase 2 stays gated on Phase 1
  sign-off, a higher-recall authoritative CIK/alias union, a validated
  SIC-to-NAICS-2 strategy, and symmetric FPDS/patent/M&A outcome inputs. Also
  owns Form D input fidelity in its own `form_d_inputs.py` loader (tasks
  F.1-F.3, from PR #691): the staging-input refusal shipped in v0.12.0 and is
  now reinforced by the staging producer's own refusal above; exact
  amendment-chain collapse is blocked on locating the SEC file number. Note
  that v0.12.0 changed `total_form_d_raised` and `offering_count` after the
  Phase 1 artifacts were materialized.
- **`bea-nipa-tax-rates` — Active.** The NIPA provider exists; the remaining
  work is the on-disk cache and removal of hardcoded effective-rate consumers.
- **`company-categorization` — Maintenance.** About 80% complete. Evaluate the
  remaining Neo4j loader and docs against the current `:Organization` graph
  schema before implementation.
- **`cross-agency-taxonomy` — Gated backlog.** M3 research target. Prerequisite
  classifier/tools exist, but this spec's batch run, report, and Dagster wiring
  are not implemented.
- **`dark-majority-resolution` — Maintenance.** Retiered `evidence` → `pipelines`
  (2026-08-15): no four-item evidence contract yet. Core contract, identity,
  liveness, and recovery work is implemented. Remaining work is a bounded web
  liveness sweep plus blocked/deferred external-registry checks.
- **`data-imputation` — Gated backlog.** Foundational E4 work, but zero
  implementation. Start only when missing-field recovery becomes the next
  data-quality priority.
- **`dspy-weekly-awards-prototype` — Gated backlog.** Documentation-only
  evaluation plan for the E6 weekly award-narrative seam. Do not begin Stage 0
  until a named owner, two labelers, an independent sealed-label custodian, and
  an API-spend approver are recorded; SBIR.gov identity reuse and its equality
  test are accepted; and weekly-report refactor T2.3 plus the injected,
  typed-return work in T3.2 are complete. Offline, full-context, and shadow
  gates still precede any production integration.
- **`edgar-event-date-fidelity` — Gated backlog.** From PR #690. EDGAR profiles
  pair an M&A mention *type* with a "latest" date taken across all types, and two
  `scripts/data/` consumers already perform that unsafe join. Declared
  `exploratory` rather than `pipelines`: both named consumers are scripts. Owns
  only `sbir_etl/enrichers/sec_edgar/`. The Form D amendment work reviewed
  alongside it (PR #691) is not here — it lives with the code it changes, as
  `agency-private-capital-comparison` tasks F.1-F.3.
- **`epistemic-tier-enforcement` — Maintenance.** Enforcement follow-on to the
  2026-08 module-labeling sweep (PRs #550–#552). Shipped: the blocking
  tier-aware import guard (`scripts/ci/check_tier_boundaries.py`, in
  `make lint-boundaries` and CI), the workbench/operated doctrine (T4.1), and a
  full burndown of `TIER_IMPORT_ALLOWLIST` to zero — canonical company merge
  promoted into `sbir_etl.identity` under `CanonicalMergePolicy.PRELOAD_V1`
  (T2, byte-identical to the golden corpus), the NSF CET screen inverted out of
  the pipelines defense release into the operated exploratory asset layer (T3),
  the opportunity scorer split into an exploratory pairing module (edge 4), and
  NAICS text-inference registration moved behind an exploratory composition
  point (edges 5-6). No fifth tier and no directory moves. Remaining work is
  ordinary upkeep of declarations as modules are added.
- **`fiscal-tax-impact-v2.md` — Gated backlog.** Valid D2 methodology upgrade.
  Leave inactive until fiscal-model refresh is selected.
- **`follow-on-multiplier-validation` — Active.** Retiered `evidence` →
  `exploratory` (2026-08-15): design-only follow-up without an evidence contract.
  Still called out as an immediate research-plan gap.
- **`iterative-api-enrichment` — Maintenance.** Issue #442 closed the
  shared lifecycle: `SourceAdapter` + `SourceRefreshRunner`, USAspending
  as the reference adapter, and `usaspending_refresh_batch` on the job.
  Per-source adapters stay split (#443 NIH RePORTER, then SAM/PatentsView).
  Tasks 6.1–6.2 remain optional Phase 2 expansion.
- **`ma-discovery-integration` — Deferred.** The #371 toolkit now lives at
  `sbir_etl/enrichers/ma_discovery/` (issue #446, toolkit relocation). Search
  backend, LLM extractor, and collision policy remain unbuilt. Revisit only
  when M&A recall becomes a selected research priority.
- **`modular-analysis-platform` — Maintenance.** Pipelines-tier contracts
  and registry so a new tech-census or transition-cohort profile is
  YAML-only (issue #441). HTTP is out of scope per ADR-004. Weekly awards
  stay on their existing builder. Census and cohort classifiers remain
  exploratory.
- **`modernbert-analysis-layer` — Maintenance.** Core embeddings and similarity
  are implemented. Neo4j loading, quality metrics, and Bayesian routing remain
  scoped follow-ups.
- **`naics-enricher-consolidation` — Maintenance.** Consolidation is largely
  complete. Remaining obsolete audit/golden-file tasks should not be revived as
  written.
- **`ot-consortium-subaward-attribution` — Gated backlog.** Valid A2 research
  question, but the T0 coverage probe must run before implementation.
- **`patent-cost-spillover` — Gated backlog.** M2 analytical layer remains
  missing. Implement only when patent cost/spillover becomes the selected
  sprint.
- **`phase-3-solicitation-alerts` — Maintenance.** Retiered `evidence` →
  `pipelines` (2026-08-15). Retrospective S1 work is
  implemented. SAM.gov Opportunities S2/S3 paths remain backlog.
- **`phase-iii-census` — Active.** Phase 1 is implemented and materialized under
  a reproducible study contract; the control-identity eligibility gate, the
  exact-matching balance gate, and the preregistered fixed-seed placebo
  falsification have all passed (2026-08-03 audits). Matched negative-control
  outcomes are descriptive only — a 2.10x clearing ratio with 0.853 overlap, so
  the frozen criteria do not cleanly discriminate. Hand-labeled validation
  remains required before any undercount or statutory Phase III claim.
- **`phase-iii-source-materialization` — Maintenance.** The schema-verified
  USAspending and SBIR.gov source layer is implemented. Keep it aligned with the
  census and other transition consumers rather than extending it with scoring policy.
- **`phase-iii-hand-label-validation` — Gated backlog.** Design and estimand
  are written but the spec is not yet frozen. Do not implement until the design
  is approved and frozen per the evidence-tier contract.
- **`phase3-candidate-enrichment` — Active.** Retiered `evidence` → `exploratory`
  (2026-08-15). The source-coverage gate stopped
  the text assembler, while the firm-ranking/lineage experiment found a useful
  but hand-weighted lift. Learned weights and a larger independent validation set
  remain before production use.
- **`phase3-match-benchmark` — Maintenance.** Retiered `evidence` → `pipelines`
  (2026-08-15). Corrected estimator and cohort
  rules are implemented; empirical reruns remain blocked on the required inputs.
  Its results remain provisional portfolio-linkage evidence.
- **`phase3-notice-corpus-fusion` — Maintenance.** Retiered `evidence` →
  `pipelines` (2026-08-15). Award-grain recovery,
  reproduction, frozen coefficients, and packet integration landed. Reconcile
  the remaining documentation task and the explicitly missing second label channel.
- **`phase3-transition-groundtruth` — Maintenance.** The independent corpus,
  T6 results, and T7 decision memo landed; the requirements header now says so
  and the spec was retiered evidence → pipelines on 2026-08-07 (corpus
  construction is deterministic; citation requires a future study contract).
- **`phase3-undercount-extension` — Gated backlog.** Valid B3 follow-up, but it
  depends on reusable resolution/self-label components and must keep contract
  undercount separate from provisional non-contract vehicle counts.
- **`procurement-transition-p1-remediation` — Active.** Retiered `evidence` →
  `pipelines` (2026-08-15). Award identity and path
  attribution landed. Cold-start bounds, source-normalization provenance, and
  ranking/auditability phases remain.
- **`sbir-ma-match-rate-by-fy` — Gated backlog.** Analysis-only F2 follow-up on
  completed M&A detection. Start only when FY match-rate reporting is requested.
- **`state-local-tax-rates` — Maintenance.** Existing hardcoded 2024 provider
  works. Remaining work is data-file/provenance cleanup for fiscal v2.
- **`sttr-spinout-linkage` — Active.** Phase 0 design frozen as Revision 1 (exploratory,
  non-citable); implementation (`tasks.md` Phase 1) is unblocked. Proposes a deterministic
  public-data classifier splitting each STTR SBC↔RI relationship into spinout vs.
  subcontract (dedicated B2 inventory entry), a list-based RI partner-type classifier with
  a non-university/non-FFRDC-nonprofit incidence readout (dedicated B1 entry), and a
  design-only matched outcome comparison (F1/F3/A4/B3). Remaining Phase 1 work: seed-list
  capture, the kernel, the cascade run, and the negative-control/blind-adjudication gates —
  citable status stays blocked until those gates pass. The named
  `nih-commercialization-linkage` kernel it was to reuse does not exist and is being built
  as new exploratory-tier code here.
- **`tech-area-transition-report` — Maintenance.** The parameterized cohort and
  report pattern is implemented across nanotechnology, QIS, and hypersonics.
  The remaining task is to add richer headline channels when their evidence exists.
- **`transition-coverage-expansion` — Active.** Retiered `evidence` →
  `exploratory` (2026-08-15). Initial access and coverage
  spikes are recorded. Credible grant/subaward attribution, OT resolution, and a
  channel-by-channel wire-in decision remain.
- **`transition-precision-benchmark` — Active.** Automates the full-corpus
  Phase III retrospective precision benchmark, whose PR-time automation today
  is limited to a fixture-level canary while the full-corpus script is run
  manually. Pins the benchmark corpus by a committed
  hash-plus-coarse-aggregates manifest (bytes stay private/gitignored on a public
  repo), runs the benchmark server-side as an operated Dagster asset with a
  blocking ≥85% check, and keeps the fast PR canary unchanged. Building the
  reproducible measurement and the gate (pipelines); a citable precision claim
  stays gated on the decoy/estimand work in `phase3-transition-groundtruth` and a
  `studies/transition-scoring/` promotion. No GitHub-runner execution, no
  committed corpus bytes, no server schedule.
- **`weekly-awards-report-refactor` — Maintenance.** Monolith is already split
  into weekly reporting modules. Remaining work is injection, coverage, and
  alias cleanup.

## Archive Candidates

`ucc1-financing-analysis` was archived on 2026-08-07 under
`specs/archive/completed-features/` (treated as a completed pilot: it answered
its Phase 0 question and the stop was a deliberate scope decision). All three
archive steps were executed — live-doc links updated, completion record added,
directory moved.

No other top-level spec should be archived from this review because each still
anchors a live research question or an active maintenance cleanup.
