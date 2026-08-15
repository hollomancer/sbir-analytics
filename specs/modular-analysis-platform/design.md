# Modular Analysis Platform — Design (#441)

**Target epistemic tier:** `pipelines`

## Current and proposed flow

Census (`sbir_etl/utils/tech_census.py`) and transition cohort
(`sbir_etl/reporting/tech_area_cohort.py`) already exist as separate
exploratory engines with YAML profiles. Dagster still hard-codes
`TECH_AREAS` in `packages/sbir-analytics/sbir_analytics/assets/transition_report.py`.

```text
registry.yaml
    -> AnalysisSpec
    -> materialize_analysis(spec, strategy=...)
        -> existing run_census / materialize_tech_area_cohort
    -> AnalysisRun + snapshot JSON
```

Pipelines modules in `sbir_etl/analysis/` hold contracts, registry I/O,
snapshot compare, and the runner shell. Exploratory engines are injected at
the CLI / Dagster composition boundary so `check_tier_boundaries` stays
clean.

## Components

- `sbir_etl/analysis/contracts.py` — types and `EvidenceChannelStage`
- `sbir_etl/analysis/registry.py` — load `config/analysis_profiles/registry.yaml`
- `sbir_etl/analysis/runner.py` — hash pinning + strategy dispatch
- `sbir_etl/analysis/snapshots.py` — write/compare
- `scripts/data/run_analysis.py` — CLI
- Registry-driven factory replacing `TECH_AREAS`

HTTP is not part of this design (ADR-004). Weekly awards stay on
`WeeklyAwardsReportBuilder`.

## Calibration lock

Do not change census admission rules or transition Method A/B/C matching.
Verify:

- `tests/unit/utils/test_tech_census.py`
- `tests/unit/scripts/test_build_tech_area_cohort.py`
- frozen Method A sizes in `specs/tech-area-transition-report/validation.md`
