# Modular Analysis Platform — Requirements

**Target epistemic tier:** `pipelines`

- **Research question:** none directly. Operational obligation: adding a
  configured technology-census or transition-cohort profile must not require
  bespoke CLI, Dagster, or snapshot-directory code. Existing calibrated
  outputs stay unchanged unless an explicitly versioned methodology change is
  made. Serves the same consumers as
  [tech-area-transition-report](../tech-area-transition-report/requirements.md)
  (B / C1) without rewriting those classifiers. See
  [docs/research-questions.md](../../docs/research-questions.md).
- **Status:** active
- **Out of scope:** HTTP or MCP adapters (ADR-004); weekly-awards
  `analysis_kind`; rewriting census or transition matching; promoting
  profiles to the evidence tier; `cross-agency-taxonomy` scheduled assets;
  one API/enum member per profile.

## Done when

> An operator adds a profile YAML plus a registry row and can run
> `uv run python scripts/data/run_analysis.py --profile <id>` (and, when
> `dagster_asset: true`, materialize a generated Dagster asset) with no new
> Python module. Snapshot compare refuses silent methodology or source-hash
> drift. Drone/UAS census goldens and the frozen Method A sizes in
> `specs/tech-area-transition-report/validation.md` still pass.

## Requirements

### Requirement 1 — Shared contracts

THE System SHALL expose `AwardCorpus`, `ReportingWindow`, `SourceManifest`,
`AnalysisSpec`, and `AnalysisRun` under `sbir_etl/analysis/` at the
`pipelines` tier. `analysis_kind` SHALL be one of `tech_census` or
`transition_cohort`. Every spec SHALL record `taxonomy_version` and
`methodology_version`.

### Requirement 2 — Profile registry

THE System SHALL load profiles from `config/analysis_profiles/registry.yaml`.
Adding a profile SHALL NOT require a new Python enum member.

### Requirement 3 — Runner without a new methodology

WHEN `materialize_analysis` runs, THE System SHALL dispatch to the existing
census or cohort engine through an injected strategy (pipelines code SHALL
NOT import those exploratory engines). THE System SHALL pin methodology,
taxonomy, source, and config hashes on the run. IF hashes differ from a
frozen snapshot AND `--allow-methodology-change` is absent, THEN THE System
SHALL refuse the run.

### Requirement 4 — Evidence stages and metric ids

THE System SHALL use `EvidenceChannelStage` values `computed`,
`unavailable`, and `not_applicable`. Absent transition-signal artifacts
SHALL still render as "Not computed — not zero", never as a zero rate.

### Requirement 5 — Generic adapters

THE System SHALL provide one CLI (`scripts/data/run_analysis.py --profile`),
registry-driven Dagster asset generation for transition-cohort profiles
marked `dagster_asset: true`, and a transport-neutral snapshot store under
`data/reports/analysis_snapshots/<profile_id>/`.
