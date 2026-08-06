# Production Asset Checks — Requirements

**Target epistemic tier:** `pipelines`

- **Research question:** none directly. Operational obligation: the retired
  nightly/weekly suites were the only mechanism answering "does the system
  still work on real data," and they rotted because they tested a synthetic
  copy on a calendar nobody owned. This spec moves that function into the
  production pipeline itself: blocking Dagster asset checks that run whenever
  the real assets materialize, on the real corpus, with failures that stop
  downstream steps. It is the enforcement half of the operated-exploratory
  doctrine (docs/steering/epistemic-tiers.md, "Two populations") and the
  system-health complement to the merge-attached test lanes (PR #556).
- **Status:** active. No hard prerequisites — the asset-check machinery,
  config-threshold convention, and blocking pattern all exist in-tree.
- **Out of scope:** scheduled workflows or any calendar-driven testing;
  enabling or changing any Dagster schedule (stays an operator decision per
  the server runbook); external alerting integrations (Dagster-native run
  failure is the v1 signal; AlertCollector wiring is a named follow-up);
  Neo4j data-level lineage checks; the Phase III census machinery (already
  evidence-tier with its own blocking checks); study manifests.
- **Verification that proves completion:** builder unit tests pass; a local
  `materialize()` of a check-bearing asset with fixtures demonstrates pass,
  fail, and block behavior; `Definitions.validate_loadable` passes; docs-check
  passes with the runbook addition.

## Problem

CI proves the code is internally correct on samples. Nothing now verifies the
system against the real corpus except humans noticing. The pieces exist —
`AssetCheckResult` quality checks on fiscal assets, the census's blocking
check, `data_quality` thresholds in `config/base.yaml`, `row_count` output
metadata — but the ordinary ingestion and core-refresh path has no checks, so
a short download, a stale source file, or a silently shrunken corpus flows
into the graph and the reports without a tripwire.

## R1 — Shared check builders

A small module, `packages/sbir-analytics/sbir_analytics/asset_checks.py`,
holding three pure builders that every attachment reuses.

1.1 **Freshness.** WHEN the checked asset records a source as-of or
    download timestamp, THE check SHALL fail with `ERROR` severity if that
    timestamp is older than the configured maximum age. IF the expected
    metadata is missing, THEN THE check SHALL fail with an explicit
    "missing freshness metadata" reason — absence is a failure, never a
    silent pass.

1.2 **Row-count delta.** WHEN a previous materialization recorded a row
    count, THE check SHALL fail if the current count drops below
    `(1 − max_drop_fraction) × previous`. WHEN no previous count exists
    (first materialization, or metadata not yet emitted), THE check SHALL
    pass with a "baseline recorded" note. The comparison SHALL read the
    prior count from Dagster's materialization event metadata, not from any
    file the check maintains itself.

1.3 **Completeness.** THE check SHALL fail if required columns are missing
    or their non-null rate falls below threshold, reusing the existing
    `data_quality.completeness` thresholds in `config/base.yaml` rather
    than introducing a second completeness vocabulary.

1.4 Builders SHALL be pure functions over `(dataframe/metadata, thresholds,
    previous_count)` so they unit-test without a Dagster instance; only the
    thin attachment layer touches the instance. Every result SHALL carry
    structured metadata: observed value, threshold, previous value where
    applicable.

## R2 — Attachment, first tranche

2.1 **Source/ingestion assets** — `raw_sbir_awards`,
    `raw_usaspending_recipients`, `raw_usaspending_transactions`,
    `raw_sam_gov_entities` — each gains a blocking freshness check and a
    blocking minimum-row-floor check.

2.2 **Core refresh anchor** — `enriched_sbir_awards` gains a blocking
    row-count-delta check and a blocking completeness check on the core
    columns (`award_id`, `company_name`, `award_amount`, `award_date`,
    `program`, matching the existing completeness map).

2.3 All first-tranche checks SHALL be `blocking=True`: a failure halts
    downstream materialization in the same run. There is no warn-only tier
    in v1 — a check either earns blocking or is not added.

2.4 Assets in 2.1–2.2 that do not yet emit `row_count` output metadata
    SHALL start emitting it, following the existing convention in
    `usaspending_database_enrichment.py`.

## R3 — Configuration

3.1 Thresholds live under `data_quality.operational_checks` in
    `config/base.yaml`: per-source `max_age_days`, per-asset `min_rows`,
    and a shared `max_row_drop_fraction`. Access goes through the config
    loader like the fiscal thresholds; no hardcoded numbers at call sites.

3.2 Initial values are deliberately loose (they exist to catch collapse,
    not drift): e.g. `max_age_days` ≈ 2× each source's refresh cadence,
    `min_rows` well below any historical count, `max_row_drop_fraction`
    0.2. Tightening is config-only follow-up work.

## R4 — Operator surface

4.1 A failed blocking check fails the run; the server's existing
    run-failure visibility is the v1 alert path. Check results
    (pass and fail) SHALL be visible per-asset in the Dagster UI with their
    structured metadata.

4.2 The server runbook SHALL gain a short triage subsection: what a blocked
    materialization means, how to read the check metadata, and that the only
    bypass is a committed threshold change — never an ad-hoc override on the
    host.
