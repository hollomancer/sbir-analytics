# Implementation Plan

**Phase 1: USAspending API only.** Other APIs (SAM.gov, NIH RePORTER, PatentsView, etc.) will be evaluated in Phase 2+.

- [x] 1.1 Inventory every external enrichment API referenced in repo docs/config (SBIR.gov, USAspending, SAM.gov, NIH RePORTER, PatentsView, etc.) and document their release cadence + throttling limits.
  - Notes: Implemented `openspec/changes/add-iterative-api-enrichment/inventory.md` and populated `openspec/changes/add-iterative-api-enrichment/providers.json`. Added `scripts/openspec/fetch_provider_docs.py` to automatically fetch and annotate provider docs (rate-limit headers, auth hints, delta support). Ran the discovery locally and updated `providers.json` with initial findings; follow-up verification of exact quotas/auth details is noted in the inventory.

- [x] 1.2 Add an `enrichment_refresh` section to `config/base.yaml` (and dev/prod overrides) with per-source cadence, batch size, and concurrency knobs.
  - Notes: Added `enrichment_refresh.usaspending` section to `config/base.yaml` with USAspending-specific configuration. Phase 1 focus note included in config comments.

- [x] 1.3 Define SLA defaults (max staleness days per source) and expose them through `src/config/schemas.py` so they are validated at load time.
  - Notes: Created `EnrichmentSourceConfig` and `EnrichmentRefreshConfig` models in `src/config/schemas.py`. Added to `PipelineConfig` with Phase 1 note.

- [x] 2.1 Extend `src/models/enrichment.py` (or add a new module) with data classes for `EnrichmentFreshnessRecord` capturing `award_id`, `source`, `last_attempt_at`, `last_success_at`, `payload_hash`, and `status`.
  - Notes: Created `src/models/enrichment.py` with `EnrichmentFreshnessRecord` dataclass, `EnrichmentFreshnessRecordModel` Pydantic model, `EnrichmentStatus` enum, and `EnrichmentDeltaEvent` for delta tracking.

- [x] 2.2 Update enrichment outputs to persist per-source freshness rows to DuckDB/Parquet (`data/derived/enrichment_freshness.parquet`) and to Neo4j properties.
  - Notes: Created `src/utils/enrichment_freshness.py` with `FreshnessStore` class for Parquet persistence. Neo4j persistence helper function included.

- [x] 2.3 Add migration/utility to backfill freshness metadata for existing enriched awards after the first iterative run.
  - Notes: Created `scripts/backfill_enrichment_freshness.py` for initializing freshness records from existing enriched data.

- [x] 3.1 Implement USAspending API client with async requests (httpx + tenacity backoff, structured logging, instrumentation).
  - Notes: Created `src/enrichers/usaspending_api_client.py` with full async client, rate limiting, retry logic, and delta detection.

- [x] 3.2 Capture USAspending delta identifiers (`modification_number`, `action_date`, `last_modified_date`) and compute deterministic payload hashes for comparison.
  - Notes: Implemented in `USAspendingAPIClient._extract_delta_metadata()` and `_compute_payload_hash()` methods.

- [x] 3.3 Store per-source cursors/ETags in `data/state/enrichment_refresh_state.json` (or similar) and ensure the connectors honor If-Modified-Since / pagination tokens where available.
  - Notes: State management implemented in `USAspendingAPIClient.load_state()` and `save_state()` methods.

- [x] 3.4 Add contract/unit tests for each client covering rate-limit handling, retry, and delta skip behavior (mock responses, recorded fixtures).
  - Notes: Created comprehensive unit tests in `tests/unit/test_usaspending_api_client.py`, `tests/unit/test_enrichment_freshness.py`, `tests/unit/test_enrichment_checkpoints.py`, and `tests/unit/test_enrichment_models.py`. Tests cover rate limiting, retry logic, delta detection, state management, and persistence operations.

- [x] 4.1 Create `src/assets/usaspending_iterative_enrichment.py` defining Dagster assets/ops plus `usaspending_iterative_enrichment_job` that partitions work by award cohort.
  - Notes: Created assets module with `usaspending_freshness_ledger`, `stale_usaspending_awards`, and `usaspending_refresh_batch` op. Job defined in `src/assets/jobs/usaspending_iterative_job.py`.

- [x] 4.2 Add a Dagster sensor that triggers the job nightly once bulk enrichment assets are healthy and injects the proper partitions.
  - Notes: Created `src/assets/sensors/usaspending_refresh_sensor.py` with sensor that checks bulk enrichment status and stale awards.

- [x] 4.3 Persist checkpoints (cursor, slice window, last success) to DuckDB/Parquet so interrupted runs resume without duplication.
  - Notes: Created `src/utils/enrichment_checkpoints.py` with `CheckpointStore` for checkpoint persistence.

- [x] 4.4 Implement `scripts/refresh_enrichment.py` / Typer command allowing operators to request ad-hoc refresh windows or replays of failed slices.
  - Notes: Created CLI utility with `refresh-usaspending`, `list-stale`, and `stats` commands.

- [x] 5.1 Extend the pipeline metrics framework to emit per-source freshness coverage (% within SLA, attempts, success rate) and log to `artifacts/metrics`.
  - Notes: Created `src/utils/enrichment_metrics.py` with `EnrichmentMetricsCollector` and `EnrichmentFreshnessMetrics` classes. Metrics include coverage rate, success rate, staleness rate, error rate, and unchanged rate. Integrated into `usaspending_refresh_batch` op. Metrics emitted to `reports/metrics/enrichment_freshness.json` (configurable).

- [x] 5.2 Create integration tests that simulate at least one USAspending iterative cycle (using fixtures) to ensure freshness metadata, delta detection, and resume flows behave as expected.
  - Notes: Created `tests/integration/test_usaspending_iterative_enrichment.py` with comprehensive integration tests covering freshness tracking cycle, delta detection, checkpoint/resume flows, and full iterative cycle simulation. Uses mocked API client with fixtures.

- [x] 5.3 Document the iterative workflow, credential requirements, and troubleshooting steps in `docs/enrichment/iterative-refresh.md` and update `README.md`/`CONTRIBUTING.md` references.
  - Notes: Created comprehensive documentation in `docs/enrichment/usaspending-iterative-refresh.md` covering architecture, configuration, workflow, credentials, delta detection, metrics, troubleshooting, and monitoring. Updated `README.md` with quick start section and `CONTRIBUTING.md` with file reference.

- [ ] 6.1 Produce a comparison matrix covering OpenCorporates, SEC EDGAR, DLA CAGE/BIS, SAM Exclusions, ORCID/OpenAlex, OpenFEC (and any licensed commercial sources), noting auth model, rate limits, available fields, and incremental query capabilities.

- [ ] 6.2 Prototype connector shims (schema + request/response models) for at least OpenCorporates, EDGAR, and DLA CAGE/BIS using recorded fixtures so they can plug into the iterative refresh orchestrator once credentials are available.

- [ ] 6.3 Extend `config/base.yaml` with optional `enrichment_refresh` entries for each evaluated API, including feature flags so environments can opt-in once legal/data-sharing reviews are completed.

