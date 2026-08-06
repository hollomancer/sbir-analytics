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
- **`agency-private-capital-comparison` — Gated backlog.** Phase 1 is
  implemented. Phase 2 depends on prioritizing the Form D / private-capital
  control-cohort comparison.
- **`bea-nipa-tax-rates` — Active.** The NIPA provider exists; the remaining
  work is the on-disk cache and removal of hardcoded effective-rate consumers.
- **`company-categorization` — Maintenance.** About 80% complete. Evaluate the
  remaining Neo4j loader and docs against the current `:Organization` graph
  schema before implementation.
- **`cross-agency-taxonomy` — Gated backlog.** M3 research target. Prerequisite
  classifier/tools exist, but this spec's batch run, report, and Dagster wiring
  are not implemented.
- **`dark-majority-resolution` — Maintenance.** Core contract, identity,
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
- **`fiscal-tax-impact-v2.md` — Gated backlog.** Valid D2 methodology upgrade.
  Leave inactive until fiscal-model refresh is selected.
- **`follow-on-multiplier-validation` — Active.** Design-only follow-up to the
  completed multiplier asset. Still called out as an immediate research-plan
  gap.
- **`iterative_api_enrichment` — Maintenance.** USAspending refresh is live.
  Remaining source expansion should be split or scheduled intentionally.
- **`ma-discovery-integration` — Deferred.** The design depends on an unmerged
  discovery toolkit and missing press-enrichment glue. Revisit only when M&A
  recall becomes a selected research priority.
- **`modernbert_analysis_layer` — Maintenance.** Core embeddings and similarity
  are implemented. Neo4j loading, quality metrics, and Bayesian routing remain
  scoped follow-ups.
- **`naics-enricher-consolidation` — Maintenance.** Consolidation is largely
  complete. Remaining obsolete audit/golden-file tasks should not be revived as
  written.
- **`nvca-yearbook-benchmarks` — Gated backlog.** The baseline registry exists,
  but all remaining work is blocked on verified NVCA Yearbook source access and
  an implementation-priority decision.
- **`ot-consortium-subaward-attribution` — Gated backlog.** Valid A2 research
  question, but the T0 coverage probe must run before implementation.
- **`patent-cost-spillover` — Gated backlog.** M2 analytical layer remains
  missing. Implement only when patent cost/spillover becomes the selected
  sprint.
- **`phase-3-solicitation-alerts` — Maintenance.** Retrospective S1 work is
  implemented. SAM.gov Opportunities S2/S3 paths remain backlog.
- **`phase-iii-census` — Active.** Phase 1 is implemented and materialized under
  a reproducible study contract, and the control-identity eligibility gate passed.
  Control construction/matching, placebo tests, and labeled validation remain
  required before any undercount or statutory Phase III claim.
- **`phase-iii-source-materialization` — Maintenance.** The schema-verified
  USAspending and SBIR.gov source layer is implemented. Keep it aligned with the
  census and other transition consumers rather than extending it with scoring policy.
- **`phase-iii-hand-label-validation` — Gated backlog.** Design and estimand
  are written but the spec is not yet frozen. Do not implement until the design
  is approved and frozen per the evidence-tier contract.
- **`phase3-candidate-enrichment` — Active.** The source-coverage gate stopped
  the text assembler, while the firm-ranking/lineage experiment found a useful
  but hand-weighted lift. Learned weights and a larger independent validation set
  remain before production use.
- **`phase3-match-benchmark` — Maintenance.** Corrected estimator and cohort
  rules are implemented; empirical reruns remain blocked on the required inputs.
  Its results remain provisional portfolio-linkage evidence.
- **`phase3-notice-corpus-fusion` — Maintenance.** Award-grain recovery,
  reproduction, frozen coefficients, and packet integration landed. Reconcile
  the remaining documentation task and the explicitly missing second label channel.
- **`phase3-transition-groundtruth` — Maintenance.** The independent corpus,
  T6 results, and T7 decision memo landed, but the requirements header still
  describes the work as unimplemented. Reconcile the spec before any extension.
- **`phase3-undercount-extension` — Gated backlog.** Valid B3 follow-up, but it
  depends on reusable resolution/self-label components and must keep contract
  undercount separate from provisional non-contract vehicle counts.
- **`production-asset-checks` — Active.** Moves the retired nightly/weekly
  suites' "does the system work on real data" function into the pipeline
  itself: blocking freshness, row-floor, row-delta, and completeness asset
  checks on the ingestion assets and `enriched_sbir_awards`, with thresholds
  in `config/base.yaml`. No schedules are added or changed; checks ride
  whatever materializations run. USPTO checks and AlertCollector wiring are
  named second-tranche work.
- **`procurement-transition-p1-remediation` — Active.** Award identity and path
  attribution landed. Cold-start bounds, source-normalization provenance, and
  ranking/auditability phases remain.
- **`sbir_ma_match_rate_by_fy` — Gated backlog.** Analysis-only F2 follow-up on
  completed M&A detection. Start only when FY match-rate reporting is requested.
- **`state-local-tax-rates` — Maintenance.** Existing hardcoded 2024 provider
  works. Remaining work is data-file/provenance cleanup for fiscal v2.
- **`tech-area-transition-report` — Maintenance.** The parameterized cohort and
  report pattern is implemented across nanotechnology, QIS, and hypersonics.
  The remaining task is to add richer headline channels when their evidence exists.
- **`transition-coverage-expansion` — Active.** Initial access and coverage
  spikes are recorded. Credible grant/subaward attribution, OT resolution, and a
  channel-by-channel wire-in decision remain.
- **`ucc1-financing-analysis` — Archive candidate.** CA-only pilot is complete
  and extension is explicitly deferred by the research memo.
- **`weekly-awards-report-refactor` — Maintenance.** Monolith is already split
  into weekly reporting modules. Remaining work is injection, coverage, and
  alias cleanup.

## Archive Candidates

`ucc1-financing-analysis` is the only top-level archive candidate from this
review. Before moving it:

1. Update `docs/research-questions.md` and `docs/research/sbir-ucc1-pilot.md`
   links to the archived path.
2. Add a completion record summarizing PRs #303 / #305, the CA-only pilot result,
   and the stop/defer rationale.
3. Move the spec under `specs/archive/completed-features/` if treating the pilot
   as complete, or `specs/archive/superseded/` if treating the extension plan as
   dropped.

No other top-level spec should be archived from this review because each still
anchors a live research question or an active maintenance cleanup.
