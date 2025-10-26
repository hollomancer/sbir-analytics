# Implementation Tasks

## 1. Freshness Policy & Configuration
- [ ] 1.1 Inventory every external enrichment API referenced in repo docs/config (SBIR.gov, USAspending, SAM.gov, NIH RePORTER, PatentsView, etc.) and document their release cadence + throttling limits.
- [ ] 1.2 Add an `enrichment_refresh` section to `config/base.yaml` (and dev/prod overrides) with per-source cadence, batch size, and concurrency knobs.
- [ ] 1.3 Define SLA defaults (max staleness days per source) and expose them through `src/config/schemas.py` so they are validated at load time.

## 2. Freshness State Modeling
- [ ] 2.1 Extend `src/models/enrichment.py` (or add a new module) with data classes for `EnrichmentFreshnessRecord` capturing `award_id`, `source`, `last_attempt_at`, `last_success_at`, `payload_hash`, and `status`.
- [ ] 2.2 Update enrichment outputs to persist per-source freshness rows to DuckDB/Parquet (`data/derived/enrichment_freshness.parquet`) and to Neo4j properties.
- [ ] 2.3 Add migration/utility to backfill freshness metadata for existing enriched awards after the first iterative run.

## 3. API Connectors & Delta Detection
- [ ] 3.1 Implement async clients for SBIR.gov, NIH RePORTER, and PatentsView plus upgrade the SAM.gov and USAspending clients to share a common base (httpx + tenacity backoff, structured logging, instrumentation).
- [ ] 3.2 Capture source-specific delta identifiers (e.g., USAspending `modification_number`, SAM.gov `lastModifiedDate`, NIH `PROJECT_NUMBER`, PatentsView `patent_date`) and compute deterministic payload hashes for comparison.
- [ ] 3.3 Store per-source cursors/ETags in `data/state/enrichment_refresh_state.json` (or similar) and ensure the connectors honor If-Modified-Since / pagination tokens where available.
- [ ] 3.4 Add contract/unit tests for each client covering rate-limit handling, retry, and delta skip behavior (mock responses, recorded fixtures).

## 4. Iterative Orchestration & Tooling
- [ ] 4.1 Create `src/assets/iterative_enrichment.py` defining Dagster assets/ops plus `iterative_enrichment_refresh_job` that partitions work by source + cohort.
- [ ] 4.2 Add a Dagster sensor that triggers the job nightly once bulk enrichment assets are healthy and injects the proper partitions.
- [ ] 4.3 Persist checkpoints (cursor, slice window, last success) to DuckDB/Parquet so interrupted runs resume without duplication.
- [ ] 4.4 Implement `scripts/refresh_enrichment.py` / Typer command allowing operators to request ad-hoc refresh windows or replays of failed slices.

## 5. Metrics, Validation, and Documentation
- [ ] 5.1 Extend the pipeline metrics framework to emit per-source freshness coverage (% within SLA, attempts, success rate) and log to `artifacts/metrics`.
- [ ] 5.2 Create integration tests that simulate at least one iterative cycle per source (using fixtures) to ensure freshness metadata, delta detection, and resume flows behave as expected.
- [ ] 5.3 Document the iterative workflow, credential requirements, and troubleshooting steps in `docs/enrichment/iterative-refresh.md` and update `README.md`/`CONTRIBUTING.md` references.

## 6. Additional External API Evaluation
- [ ] 6.1 Produce a comparison matrix covering OpenCorporates, SEC EDGAR, DLA CAGE/BIS, SAM Exclusions, ORCID/OpenAlex, OpenFEC (and any licensed commercial sources), noting auth model, rate limits, available fields, and incremental query capabilities.
- [ ] 6.2 Prototype connector shims (schema + request/response models) for at least OpenCorporates, EDGAR, and DLA CAGE/BIS using recorded fixtures so they can plug into the iterative refresh orchestrator once credentials are available.
- [ ] 6.3 Extend `config/base.yaml` with optional `enrichment_refresh` entries for each evaluated API, including feature flags so environments can opt-in once legal/data-sharing reviews are completed.
