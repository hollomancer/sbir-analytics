# Production Asset Checks — Tasks

> T1 first; T2 with it (config keys the builders read). T3 and T4 are
> independent of each other after T1+T2. T5 closes the spec. No task touches
> schedules, and nothing here runs on the live host — attachments activate
> whenever the server next materializes the assets, whoever triggers that.

- [ ] 1. Implement `sbir_analytics/asset_checks.py` builders
      (`evaluate_freshness`, `evaluate_row_delta`, `evaluate_completeness`,
      `CheckOutcome`) plus unit tests on fixture frames covering pass/fail
      boundaries, missing-metadata failure, and cold-start pass.
  - Verify: builder unit tests pass in the fast lane; ruff clean.
  - Requirements: 1.1, 1.2, 1.3, 1.4

- [ ] 2. Add `data_quality.operational_checks` thresholds to
      `config/base.yaml` and loader access (mirroring the fiscal
      `quality_thresholds` pattern).
  - Verify: config loads through `get_config()`; a unit test reads each key;
    no call site hardcodes a number.
  - Requirements: 3.1, 3.2

- [ ] 3. Attach blocking freshness + row-floor checks to `raw_sbir_awards`,
      `raw_usaspending_recipients`, `raw_usaspending_transactions`, and
      `raw_sam_gov_entities`; add `row_count` and `source_as_of` output
      metadata where missing.
  - Verify: `Definitions.validate_loadable` passes; a hermetic
    `materialize()` test shows a stale/short fixture failing the check and
    blocking a downstream asset, and a healthy fixture passing.
  - Requirements: 2.1, 2.3, 2.4

- [ ] 4. Attach blocking row-delta + completeness checks to
      `enriched_sbir_awards`.
  - Verify: two-materialization `materialize()` test proves the second run
    reads the first run's `row_count` and fails on a >20% drop; completeness
    check fails when a required column's non-null rate dips below the
    existing `data_quality.completeness` thresholds.
  - Requirements: 2.2, 2.3, 2.4

- [ ] 5. Runbook triage subsection (what a blocked materialization means,
      reading check metadata, bypass-by-config-commit only) and spec
      closeout in `specs/status.md`.
  - Verify: `make docs-check` passes; status entry reflects the shipped
    state.
  - Requirements: 4.1, 4.2

Second tranche (explicitly not in this spec's definition of done): USPTO
ingestion checks once cadence thresholds have operator input; AlertCollector
wiring after the first real blocking event demonstrates what the alert should
carry; threshold tightening as config-only follow-ups.
