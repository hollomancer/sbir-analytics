# Iterative API Enrichment — Source-adapter design (#442)

**Target epistemic tier:** `pipelines`

This note covers the shared lifecycle extracted for issue #442. It does not
replace per-source domain semantics.

## Current and proposed flow

Today `usaspending_iterative_enrichment_job` materializes the freshness ledger
and the stale-award set. `usaspending_refresh_batch` exists as an unused op;
`CheckpointStore` is tested and unwired.

Proposed path:

```text
stale awards
    -> SourceRefreshRunner
        -> SourceAdapter.fetch_page / normalize / validate
        -> FreshnessStore + CheckpointStore + metrics
    -> usaspending_refresh_batch asset
```

HTTP transport stays in `BaseAsyncAPIClient`. The protocol is lifecycle, not
transport. NIH activity codes, UCC portal sessions, restricted-entity screening,
and M&A scoring stay in their domain adapters (not this layer).

## Components

- `SourceAdapter` protocol in `sbir_etl/enrichers/source_adapter.py`
- `SourceProvenance` (source id, retrieval time, content hash, citation URL)
- `SourceRefreshRunner` composing `EnrichmentSourceConfig`, `FreshnessStore`,
  `CheckpointStore`, and `EnrichmentMetricsCollector`
- `USAspendingSourceAdapter` wrapping `USAspendingAPIClient`

Configuration remains `PipelineConfig.enrichment_refresh` /
`EnrichmentSourceConfig`. No parallel YAML tree. Identity stays in
`sbir_etl.identity`.

## Failure behavior

A single-record fetch failure records freshness failure and continues the
partition. Checkpoint `last_processed_award_id` advances only after a record
is attempted (success or recorded failure) so a resume does not replay the
same row forever.

## Out of scope

NIH RePORTER client (#443), restricted-entity lists (#444), national UCC-1
(#445), M&A discovery (#446), provider comparison matrix (task 6.1), DLA
CAGE/BIS (task 6.2).
