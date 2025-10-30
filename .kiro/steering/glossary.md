# Glossary

## Confidence Levels (Enrichment)

| Level | Range | Sources | Use Case |
|-------|-------|---------|----------|
| High | ≥0.80 | Exact matches, API lookups | Production ready |
| Medium | 0.60-0.79 | Fuzzy matches, validated proximity | Review recommended |
| Low | <0.60 | Agency defaults, sector fallbacks | Manual review required |

## Key Terms

- Asset check: A Dagster validation attached to an asset that enforces quality gates.
- Quality gates: Configurable pass/fail thresholds that block or allow downstream assets.
- Incremental mode: Process only new/changed data while preserving previous outputs.
- Chunked processing: Split large datasets into bounded-size chunks to manage memory.
- Fallback chain: Ordered sequence of enrichment sources, moving to the next on failure.
- Evidence: Metadata supporting an enrichment decision (e.g., similarity scores, API info).
- Confidence: Numeric score (0.0–1.0) indicating reliability of an enrichment result.
- Batch size: Number of records processed per operation (API call, DB write, etc.).
- Env var override: `SBIR_ETL__...` environment variable that overrides YAML config at runtime.


