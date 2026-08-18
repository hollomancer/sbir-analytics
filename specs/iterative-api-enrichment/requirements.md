# Requirements — Iterative API Enrichment Refresh

**Target epistemic tier:** `pipelines`

> **Status:** Maintenance — USAspending freshness selection is live; issue #442
> closes the shared source-adapter lifecycle and wires the unused refresh batch
> into the job. Per-source adapters (NIH RePORTER #443, SAM.gov, PatentsView)
> stay split and are not required to close this spec.
> Supports inventory question **E3** (enrichment freshness infrastructure) in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** E3 — incremental enrichment refresh to keep company, award, and patent metadata current
**Answers for:** pipeline engineers
**Complexity tier:** Foundational infrastructure

---

## Done when

> A pipeline engineer can state: "USAspending refresh runs as
> `usaspending_iterative_enrichment_job` (ledger → stale set → batch) through
> one `SourceAdapter` / `SourceRefreshRunner` loop that writes freshness and
> checkpoints. A second source implements `SourceAdapter` and joins the runner
> without copying pagination, retry, or checkpoint code. An operator can
> trigger a targeted refresh via `uv run refresh-enrichment --source
> usaspending` (optional `--window <start>:<end>`)."

---

## Introduction

This specification implements an iterative API enrichment refresh loop to keep company, award, and patent metadata current.

- The current enrichment stage performs a heavy, mostly one-off merge after SBIR bulk ingestion, so company, award, and patent metadata start to drift as soon as external systems publish corrections or new records.
- The external sources we already rely on (SBIR.gov awards API, USAspending v2, SAM.gov entity data, NIH RePORTER, PatentsView, plus the other APIs called out across docs/config) publish updated snapshots daily to monthly; without an iterative refresh we miss compliance actions, debarments, UEI/DUNS changes, new transitions, and patent grants that happen after the initial load.
- Downstream CET classification, transition detection, and commercialization analytics need fresh enrichment signals to remain trustworthy; manually kicking off another full enrichment run takes hours and wastes API quotas instead of incrementally refreshing only what changed.

## Glossary

Feature-local terms only. Do not redefine enrichment confidence bands here —
see [glossary.md](../../docs/steering/glossary.md).

- **`PipelineConfig.enrichment_refresh`** — Config namespace for iterative-refresh
  settings (`sbir_etl/config/schemas/pipeline.py`), e.g.
  `config.enrichment_refresh.usaspending.*`.
- **Freshness ledger** — `data/derived/enrichment_freshness.parquet` (per-source
  freshness metrics).
- **Refresh state** — `data/state/enrichment_refresh_state.json` (per-source
  last-attempt / last-success timestamps).
- **Operator CLI** — `uv run refresh-enrichment --source usaspending` (shared
  runner entry point).
- **Operator docs** — `docs/enrichment/iterative-refresh.md`.

## Requirements

### Requirement 1 — Scheduled incremental refresh loop

**User Story:** As a pipeline engineer maintaining data freshness, I want a Dagster job (`iterative_enrichment_refresh_job`) and sensor that activates once bulk enrichment assets have succeeded and runs on a nightly rolling schedule, so that the pipeline incrementally refreshes only records changed since the last run rather than re-running a full enrichment against all awards.

#### Acceptance Criteria

1. THE System SHALL implement a Dagster job and sensor that activates after bulk enrichment asset materialization succeeds and runs on a configurable schedule (default: nightly).
2. THE System SHALL track per-record enrichment state via `last_attempt_at` and `last_success_at` timestamps so that only stale or failed records are queued for refresh.
3. THE System SHALL be configurable via `PipelineConfig.enrichment_refresh` (e.g., `config.enrichment_refresh.usaspending.*`) per-source toggles and schedule parameters without code changes.

### Requirement 2 — Per-source partitioned processing

**User Story:** As a pipeline engineer managing external API quotas, I want enrichment work partitioned by source and record cohort (e.g., UEI batches for SAM.gov, award-year slices for USAspending), so that each refresh run respects per-source rate limits and individual partition failures can be retried independently without re-processing the full corpus.

#### Acceptance Criteria

1. THE System SHALL partition each refresh run by source (SAM.gov, USAspending, NIH RePORTER, PatentsView) and record cohort (e.g., UEI batches, award-year windows).
2. THE System SHALL respect per-source rate limits using the same retry and back-off semantics as the existing `SAMGovAPIClient`.
3. THE System SHALL make each partition independently retryable; a single-partition failure SHALL NOT abort the remaining partitions.

### Requirement 3 — Freshness telemetry and SLA monitoring

**User Story:** As a pipeline engineer responsible for data quality SLAs, I want per-source freshness metrics persisted to `data/derived/enrichment_freshness.parquet` (with state in `data/state/enrichment_refresh_state.json`) and surfaced as staleness alerts, so that I can identify which enrichment sources have drifted beyond acceptable windows and trigger targeted remediation without a full re-enrichment run.

#### Acceptance Criteria

1. THE System SHALL persist per-source enrichment state to `data/derived/enrichment_freshness.parquet` and `data/state/enrichment_refresh_state.json`, recording attempt count, last success timestamp, and staleness window per source.
2. THE System SHALL alert (via Dagster asset check or log warning) when any source's last successful enrichment exceeds its configured SLA window.
3. THE System SHALL support `uv run refresh-enrichment --source <name>` (optional `--window <start>:<end>`) for manual targeted refreshes.
