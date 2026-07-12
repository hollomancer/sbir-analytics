# Specification Status Registry

Reviewed: 2026-07-07

This registry is the cleanup checkpoint for top-level specs. It does not replace
the requirements, design, or tasks files; it records whether a spec is a current
implementation target, a gated backlog item, a deferred design, or an archive
candidate. Use `docs/research-questions.md` as the scope gate before promoting
any gated or deferred spec back into active work.

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

- **`agency-private-capital-comparison` — Gated backlog.** Phase 1 is
  implemented. Phase 2 depends on prioritizing the Form D / private-capital
  control-cohort comparison.
- **`company-categorization` — Maintenance.** About 80% complete. Evaluate the
  remaining Neo4j loader and docs against the current `:Organization` graph
  schema before implementation.
- **`cross-agency-taxonomy` — Gated backlog.** M3 research target. Prerequisite
  classifier/tools exist, but this spec's batch run, report, and Dagster wiring
  are not implemented.
- **`data-imputation` — Gated backlog.** Foundational E4 work, but zero
  implementation. Start only when missing-field recovery becomes the next
  data-quality priority.
- **`follow-on-multiplier-validation` — Active.** Design-only follow-up to the
  completed multiplier asset. Still called out as an immediate research-plan
  gap.
- **`iterative_api_enrichment` — Maintenance.** USAspending refresh is live.
  Remaining source expansion should be split or scheduled intentionally.
- **`modernbert_analysis_layer` — Maintenance.** Core embeddings and similarity
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
- **`phase-3-solicitation-alerts` — Maintenance.** Retrospective S1 work is
  implemented. SAM.gov Opportunities S2/S3 paths remain backlog.
- **`sbir_ma_match_rate_by_fy` — Gated backlog.** Analysis-only F2 follow-up on
  completed M&A detection. Start only when FY match-rate reporting is requested.
- **`state-local-tax-rates` — Maintenance.** Existing hardcoded 2024 provider
  works. Remaining work is data-file/provenance cleanup for fiscal v2.
- **`ucc1-financing-analysis` — Archive candidate.** CA-only pilot is complete
  and extension is explicitly deferred by the research memo.
- **`weekly-awards-report-refactor` — Maintenance.** Monolith is already split
  into weekly reporting modules. Remaining work is injection, coverage, and
  alias cleanup.
- **`fiscal-tax-impact-v2.md` — Gated backlog.** Valid D2 methodology upgrade.
  Leave inactive until fiscal-model refresh is selected.

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
