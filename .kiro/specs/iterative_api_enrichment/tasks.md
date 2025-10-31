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

- [ ] 2.2 Update enrichment outputs to persist per-source freshness rows to DuckDB/Parquet (`data/derived/enrichment_freshness.parquet`) and to Neo4j properties.

- [ ] 2.3 Add migration/utility to backfill freshness metadata for existing enriched awards after the first iterative run.

- [ ] 3.1 Implement USAspending API client with async requests (httpx + tenacity backoff, structured logging, instrumentation).
  - Phase 1: USAspending only. Other API clients (SBIR.gov, SAM.gov, NIH RePORTER, PatentsView) will be implemented in Phase 2+.

- [ ] 3.2 Capture USAspending delta identifiers (`modification_number`, `action_date`, `last_modified_date`) and compute deterministic payload hashes for comparison.
  - Phase 1: USAspending only. Other sources will be handled in Phase 2+.

- [ ] 3.3 Store per-source cursors/ETags in `data/state/enrichment_refresh_state.json` (or similar) and ensure the connectors honor If-Modified-Since / pagination tokens where available.

- [ ] 3.4 Add contract/unit tests for each client covering rate-limit handling, retry, and delta skip behavior (mock responses, recorded fixtures).

- [ ] 4.1 Create `src/assets/usaspending_iterative_enrichment.py` defining Dagster assets/ops plus `usaspending_iterative_enrichment_job` that partitions work by award cohort.
  - Phase 1: USAspending only. Generic multi-source orchestrator will be created in Phase 2+.

- [ ] 4.2 Add a Dagster sensor that triggers the job nightly once bulk enrichment assets are healthy and injects the proper partitions.

- [ ] 4.3 Persist checkpoints (cursor, slice window, last success) to DuckDB/Parquet so interrupted runs resume without duplication.

- [ ] 4.4 Implement `scripts/refresh_enrichment.py` / Typer command allowing operators to request ad-hoc refresh windows or replays of failed slices.

- [ ] 5.1 Extend the pipeline metrics framework to emit per-source freshness coverage (% within SLA, attempts, success rate) and log to `artifacts/metrics`.

- [ ] 5.2 Create integration tests that simulate at least one USAspending iterative cycle (using fixtures) to ensure freshness metadata, delta detection, and resume flows behave as expected.
  - Phase 1: USAspending only. Multi-source tests will be added in Phase 2+.

- [ ] 5.3 Document the iterative workflow, credential requirements, and troubleshooting steps in `docs/enrichment/iterative-refresh.md` and update `README.md`/`CONTRIBUTING.md` references.

- [ ] 6.1 Produce a comparison matrix covering OpenCorporates, SEC EDGAR, DLA CAGE/BIS, SAM Exclusions, ORCID/OpenAlex, OpenFEC (and any licensed commercial sources), noting auth model, rate limits, available fields, and incremental query capabilities.

- [ ] 6.2 Prototype connector shims (schema + request/response models) for at least OpenCorporates, EDGAR, and DLA CAGE/BIS using recorded fixtures so they can plug into the iterative refresh orchestrator once credentials are available.

- [ ] 6.3 Extend `config/base.yaml` with optional `enrichment_refresh` entries for each evaluated API, including feature flags so environments can opt-in once legal/data-sharing reviews are completed.

