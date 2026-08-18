# Implementation Plan

## Status (2026-07-02)

**18 of 20 tasks complete; the two open items (6.1, 6.2) are Phase 2 expansion work.** Core Phase 1 (USAspending iterative refresh) is implemented and lives under `sbir_etl/` and `packages/sbir-analytics/` (task notes below originally cited `src/` and `openspec/` paths from an earlier repo layout; paths have been corrected). Open: 6.1 — no provider comparison matrix exists anywhere in the repo; 6.2 — OpenCorporates (`sbir_etl/enrichers/opencorporates.py`) and SEC EDGAR (`sbir_etl/enrichers/sec_edgar/`) clients exist with tests, but no DLA CAGE/BIS connector exists, so the task's "at least OpenCorporates, EDGAR, and DLA CAGE/BIS" bar is unmet. Drift note: the `scripts/refresh_enrichment.py` CLI from task 4.4 and the `openspec/` inventory artifacts from task 1.1 have since been removed from the repo.

**Phase 1: USAspending API only.** Other APIs (SAM.gov, NIH RePORTER, PatentsView, etc.) will be evaluated in Phase 2+.

- [x] 1.1 Inventory every external enrichment API referenced in repo docs/config (SBIR.gov, USAspending, SAM.gov, NIH RePORTER, PatentsView, etc.) and document their release cadence + throttling limits.
  - Notes: Originally implemented as `openspec/changes/add-iterative-api-enrichment/inventory.md`, `providers.json`, and `scripts/openspec/fetch_provider_docs.py` — these artifacts have since been removed from the repo (the `openspec/` directory no longer exists). The discovery was run at the time; the surviving output is the `enrichment_refresh` config in `config/base.yaml`.

- [x] 1.2 Add an `enrichment_refresh` section to `config/base.yaml` (and dev/prod overrides) with per-source cadence, batch size, and concurrency knobs.
  - Notes: Added `enrichment_refresh.usaspending` section to `config/base.yaml` with USAspending-specific configuration. Phase 1 focus note included in config comments.

- [x] 1.3 Define SLA defaults (max staleness days per source) and expose them through the config schemas so they are validated at load time.
  - Notes: `EnrichmentSourceConfig` and `EnrichmentRefreshConfig` models live in `sbir_etl/config/schemas/domain.py`. Added to `PipelineConfig` with Phase 1 note.

- [x] 2.1 Extend `sbir_etl/models/enrichment.py` (or add a new module) with data classes for `EnrichmentFreshnessRecord` capturing `award_id`, `source`, `last_attempt_at`, `last_success_at`, `payload_hash`, and `status`.
  - Notes: Created `sbir_etl/models/enrichment.py` with `EnrichmentFreshnessRecord` dataclass, `EnrichmentFreshnessRecordModel` Pydantic model, `EnrichmentStatus` enum, and `EnrichmentDeltaEvent` for delta tracking.

- [x] 2.2 Update enrichment outputs to persist per-source freshness rows to DuckDB/Parquet (`data/derived/enrichment_freshness.parquet`) and to Neo4j properties.
  - Notes: Created `sbir_etl/utils/enrichment/freshness.py` with `FreshnessStore` class for Parquet persistence. Neo4j persistence helper (`persist_to_neo4j`) included.

- [x] 2.3 Add migration/utility to backfill freshness metadata for existing enriched awards after the first iterative run.
  - Notes: Created `scripts/backfill_enrichment_freshness.py` for initializing freshness records from existing enriched data.

- [x] 3.1 Implement USAspending API client with async requests (httpx + tenacity backoff, structured logging, instrumentation).
  - Notes: Created `sbir_etl/enrichers/usaspending/client.py` (`USAspendingAPIClient`) with full async client, rate limiting, retry logic, and delta detection.

- [x] 3.2 Capture USAspending delta identifiers (`modification_number`, `action_date`, `last_modified_date`) and compute deterministic payload hashes for comparison.
  - Notes: Implemented in `USAspendingAPIClient._extract_delta_metadata()` and `_compute_payload_hash()` methods.

- [x] 3.3 Store per-source cursors/ETags in `data/state/enrichment_refresh_state.json` (or similar) and ensure the connectors honor If-Modified-Since / pagination tokens where available.
  - Notes: State management implemented in `USAspendingAPIClient.load_state()` and `save_state()` methods.

- [x] 3.4 Add contract/unit tests for each client covering rate-limit handling, retry, and delta skip behavior (mock responses, recorded fixtures).
  - Notes: Created comprehensive unit tests in `tests/unit/enrichers/usaspending/test_client.py`, `tests/unit/utils/test_enrichment_freshness.py`, `tests/unit/utils/test_enrichment_checkpoints.py`, and `tests/unit/test_enrichment_models.py`. Tests cover rate limiting, retry logic, delta detection, state management, and persistence operations.

- [x] 4.1 Create `packages/sbir-analytics/sbir_analytics/assets/usaspending_iterative_enrichment.py` defining Dagster assets/ops plus `usaspending_iterative_enrichment_job` that partitions work by award cohort.
  - Notes: Created assets module with `usaspending_freshness_ledger`, `stale_usaspending_awards`, and `usaspending_refresh_batch` op. Job defined in `packages/sbir-analytics/sbir_analytics/assets/jobs/usaspending_iterative_job.py`.

- [x] 4.2 Add a Dagster sensor that triggers the job nightly once bulk enrichment assets are healthy and injects the proper partitions.
  - Notes: Created `packages/sbir-analytics/sbir_analytics/assets/sensors/usaspending_refresh_sensor.py` with sensor that checks bulk enrichment status and stale awards.

- [x] 4.3 Persist checkpoints (cursor, slice window, last success) to DuckDB/Parquet so interrupted runs resume without duplication.
  - Notes: Created `sbir_etl/utils/enrichment/checkpoints.py` with `CheckpointStore` for checkpoint persistence.

- [x] 4.4 Implement `scripts/refresh_enrichment.py` / Typer command allowing operators to request ad-hoc refresh windows or replays of failed slices.
  - Notes: Created CLI utility with `refresh-usaspending`, `list-stale`, and `stats` commands. Drift note (2026-07-02): this script no longer exists in the repo; ad-hoc refreshes now go through the Dagster job/sensor.

- [x] 5.1 Extend the pipeline metrics framework to emit per-source freshness coverage (% within SLA, attempts, success rate) and log to `artifacts/metrics`.
  - Notes: Created `sbir_etl/utils/enrichment/metrics.py` with `EnrichmentMetricsCollector` and `EnrichmentFreshnessMetrics` classes. Metrics include coverage rate, success rate, staleness rate, error rate, and unchanged rate. Integrated into `usaspending_refresh_batch` op. Metrics emitted to `reports/metrics/enrichment_freshness.json` (configurable).

- [x] 5.2 Create integration tests that simulate at least one USAspending iterative cycle (using fixtures) to ensure freshness metadata, delta detection, and resume flows behave as expected.
  - Notes: Created `tests/integration/test_usaspending_iterative_enrichment.py` with comprehensive integration tests covering freshness tracking cycle, delta detection, checkpoint/resume flows, and full iterative cycle simulation. Uses mocked API client with fixtures.

- [x] 5.3 Document the iterative workflow, credential requirements, and troubleshooting steps in `docs/enrichment/iterative-refresh.md` and update `README.md` references.
  - Notes: Created comprehensive documentation in `docs/enrichment/usaspending-iterative-refresh.md` covering architecture, configuration, workflow, credentials, delta detection, metrics, troubleshooting, and monitoring. Updated `README.md` with quick start section.

- [ ] 6.1 Produce a comparison matrix covering OpenCorporates, SEC EDGAR, DLA CAGE/BIS, SAM Exclusions, ORCID/OpenAlex, OpenFEC (and any licensed commercial sources), noting auth model, rate limits, available fields, and incremental query capabilities.
  - Notes (2026-07-02): verified not done — no comparison matrix exists in `docs/` or `specs/`.

- [ ] 6.2 Prototype connector shims (schema + request/response models) for at least OpenCorporates, EDGAR, and DLA CAGE/BIS using recorded fixtures so they can plug into the iterative refresh orchestrator once credentials are available.
  - Notes (2026-07-02): partially done — OpenCorporates client exists (`sbir_etl/enrichers/opencorporates.py`, tested in `tests/unit/enrichers/test_opencorporates.py`) and SEC EDGAR client/enricher exist (`sbir_etl/enrichers/sec_edgar/`, wired into `enrichment_refresh.sec_edgar` in `config/base.yaml`). No DLA CAGE/BIS connector exists anywhere in the repo, so the task's minimum bar ("at least ... DLA CAGE/BIS") is unmet; left unchecked.

- [x] 6.3 Extend `config/base.yaml` with optional `enrichment_refresh` entries for each evaluated API, including feature flags so environments can opt-in once legal/data-sharing reviews are completed.
  - Notes: Added `enabled` feature flag to `EnrichmentSourceConfig` schema (`sbir_etl/config/schemas/domain.py`). Environments opt-in via env var (e.g., `SBIR_ETL__ENRICHMENT_REFRESH__SEC_EDGAR__ENABLED=true`). Drift note (2026-07-02): current `config/base.yaml` and `EnrichmentRefreshConfig` carry only `usaspending` and `sec_edgar` (disabled by default); the `opencorporates`/`dla_cage` entries originally added have since been removed.

## Issue #442 — shared source lifecycle

Optional Phase 2 expansion (6.1, 6.2) is **not** required to close #442.

- [x] 7.1 Add `SourceAdapter`, `SourceProvenance`, and `SourceRefreshRunner` in `sbir_etl/enrichers/source_adapter.py`.
  - Verify: mock-adapter contract test covers fetch → normalize → validate → freshness → checkpoint
- [x] 7.2 Wrap `USAspendingAPIClient` as `USAspendingSourceAdapter`.
  - Verify: unit test with a fake client, no network
- [x] 7.3 Convert `usaspending_refresh_batch` to an asset in `usaspending_iterative_enrichment_job` and call `CheckpointStore`.
  - Verify: job selection includes the refresh asset; hermetic e2e with a mocked adapter
- [x] 7.4 Restore `uv run refresh-enrichment --source usaspending`.
  - Verify: CLI `--help` and a mocked dry-run
- [x] 7.5 Update `docs/enrichment/usaspending-iterative-refresh.md`.
  - Verify: `make docs-check`

## Issue #443 — NIH RePORTER source adapter

Per-source adapter for R43/R44/R41/R42. Shared lifecycle stays in
`SourceAdapter` / `SourceRefreshRunner`. Grain: exact `project_num` /
`core_project_num` + FY on known SBIR.gov NIH/HHS awards; windows become
RePORTER criteria. Out of scope: STTR `research_hospitals`, live schedule,
rewriting the Phase III urllib extractor.

- [x] 8.1 Add `sbir_etl/enrichers/nih_reporter/` client, key canonicalizer,
      and normalized record schema. Move `canonicalize_nih_query_key` here;
      Phase III re-exports it.
  - Verify: `tests/unit/enrichers/nih_reporter/` (pagination, windows,
    duplicates, retries) and `tests/unit/phase_iii_negative_controls/test_nih_reporter.py`
- [x] 8.2 Adapter + SBIR.gov request builder + `refresh-enrichment --source nih_reporter`.
  - Verify: mocked CLI dry-run; disabled source exits; no USAspending parquet dependency
  - Notes: `NIHReporterSourceAdapter` + `requests.py` build exact-key lookups
    from the SBIR.gov award frame. `--window` is RePORTER criteria (date or
    `fy:`), not a local award-date filter. First run treats an empty freshness
    ledger as "all eligible NIH/HHS awards." Persist grain is `appl_id` at
    `data/derived/nih_reporter_awards.parquet`. `enabled: false` until a hand
    run succeeds.
- [x] 8.3 Dagster ledger / stale set / refresh batch and job. No sensor.
      Keep `enabled: false`.
  - Verify: job selection includes the refresh asset; hermetic fake adapter
  - Notes: `nih_reporter_iterative_enrichment_job` selects
    `nih_reporter_freshness_ledger`, `stale_nih_reporter_awards`, and
    `nih_reporter_refresh_batch`. First-run / stale selection is shared with
    the CLI (`nih_ids_needing_refresh`). Refresh no-ops while
    `enabled: false`. No sensor and no schedule.
- [ ] 8.4 Docs (`docs/enrichment/nih-reporter-refresh.md`) and E3 freshness
      mention only after a hand run has written a freshness row.
  - Verify: `make docs-check`
