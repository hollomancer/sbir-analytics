# Quick Reference

Fast lookup for common patterns, configurations, and code snippets used in the SBIR analytics repository.

Note: Values shown here are illustrative. The single source of truth for configuration and defaults is `../configuration.md` and `config/base.yaml`.

## Quality Thresholds Quick Lookup

| Field | Completeness | Validity Range | Notes |
|-------|-------------|----------------|-------|
| `award_id` | 100% | - | Primary key, no duplicates |
| `company_name` | 95% | - | Required for enrichment |
| `award_amount` | 98% | $0 - $5M | Phase II max $5M |
| `naics_code` | 85% | Valid NAICS | Enrichment target |
| `award_date` | 95% | 1983-2025 | SBIR program range |

## Enrichment Confidence Levels

See confidence definitions in `glossary.md`.

## Common Configuration Snippets

For full YAML examples, see `../configuration.md`.

- Quality gates: thresholds and actions → `../configuration.md#data-quality-configuration`
- Enrichment: sources, batch processing, confidence → `../configuration.md#enrichment-configuration`
- Pipeline performance: chunking, memory, retries → `../configuration.md#pipeline-orchestration-configuration`
- Neo4j loading: batch size, parallelism, timeouts → `../configuration.md#neo4j-configuration`

## Asset Check Templates

Canonical templates live in `pipeline-orchestration.md#asset-check-implementation`.

## Neo4j Patterns Quick Reference

### Node Creation (Upsert)

Organizations are keyed by the authoritative `organization_id` (e.g.
`org_company_<id>`); `uei` is a regular indexed property, so MERGE on it would
mint duplicates.

```cypher
UNWIND $batch AS row
MERGE (o:Organization {organization_id: row.organization_id})
SET o.organization_type = "COMPANY",
    o.uei = row.uei,
    o.name = row.name,
    o.address = row.address,
    o.updated_at = datetime()
```

### Relationship with Confidence

SBIR awards are `:FinancialTransaction {transaction_type: 'AWARD'}` nodes (keyed
by `transaction_id`) linked to the recipient `:Organization` via `:RECIPIENT_OF`.

```cypher
MERGE (a:FinancialTransaction {transaction_id: $transaction_id})
  ON CREATE SET a.transaction_type = "AWARD", a.award_id = $award_id
MERGE (o:Organization {organization_id: $organization_id})
MERGE (a)-[r:RECIPIENT_OF]->(o)
SET r.confidence = $confidence,
    r.method = $method,
    r.created_at = datetime()
```

### Common Constraints

```cypher
CREATE CONSTRAINT IF NOT EXISTS FOR (o:Organization) REQUIRE o.organization_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (ft:FinancialTransaction) REQUIRE ft.transaction_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (p:Patent) REQUIRE p.grant_doc_num IS UNIQUE;
```

### Performance Indexes

```cypher
CREATE INDEX organization_name IF NOT EXISTS FOR (o:Organization) ON (o.name);
CREATE INDEX organization_uei IF NOT EXISTS FOR (o:Organization) ON (o.uei);
CREATE INDEX financial_transaction_date IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.transaction_date);
```

## Environment Variables Quick Setup

Prefer `SBIR_ETL__...` overrides that mirror YAML structure. See details in `../configuration.md#environment-variable-overrides`.

Example:

```bash
export SBIR_ETL_ENV=dev
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__PIPELINE__CHUNK_SIZE=20000
```

## Common Commands

### Development Setup

```bash
uv sync
make neo4j-up
```

### Code Quality

```bash
ruff format .
ruff check . --fix
mypy sbir_etl/
pytest --cov=sbir_etl
```

### Pipeline Execution

```bash
uv run dagster dev                        # Start Dagster UI
dagster job execute -m sbir_analytics.definitions -j sbir_weekly_refresh_job
dagster job execute -m sbir_analytics.definitions -j fiscal_returns_mvp_job      # Fiscal ROI analysis (core)
dagster job execute -m sbir_analytics.definitions -j fiscal_returns_full_job     # Fiscal ROI with sensitivity
```

### Neo4j Operations

```bash
make neo4j-up      # Start Neo4j
make neo4j-down    # Stop Neo4j
make neo4j-reset   # Fresh instance
```

## Troubleshooting Quick Fixes

### Common Issues

| Issue | Quick Fix | Reference |
|-------|-----------|-----------|
| Quality check failing | Check thresholds in config | [data-quality.md](data-quality.md) |
| Enrichment low success rate | Review API keys and rate limits | [enrichment-patterns.md](enrichment-patterns.md) |
| Neo4j constraint violations | Check for duplicate data | [neo4j-patterns.md](neo4j-patterns.md) |
| Memory issues | Reduce chunk_size | [pipeline-orchestration.md](pipeline-orchestration.md) |
| Asset dependency errors | Check asset function signatures | [pipeline-orchestration.md](pipeline-orchestration.md) |
| Fiscal analysis R errors | Check R/rpy2 installation and StateIO package | [configuration.md](../configuration.md) |

### Performance Issues

| Symptom | Likely Cause | Quick Fix |
|---------|--------------|-----------|
| Slow enrichment | API rate limits | Increase batch_size, reduce rate_limit |
| High memory usage | Large chunks | Reduce chunk_size, enable memory monitoring |
| Neo4j timeouts | Large transactions | Reduce batch_size, increase timeout |
| Asset execution slow | Sequential processing | Enable parallel processing |

## Decision Trees

### When to Use Which Pattern?

### Need data validation?

→ Use asset checks from [pipeline-orchestration.md](pipeline-orchestration.md)
→ Configure thresholds in [configuration.md](../configuration.md)

### Need external data enrichment?

→ Use hierarchical enrichment from [enrichment-patterns.md](enrichment-patterns.md)
→ Configure sources in [configuration.md](../configuration.md)

### Need to load data to Neo4j?

→ Use batch loading patterns from [neo4j-patterns.md](neo4j-patterns.md)
→ Configure connection in [configuration.md](../configuration.md)

### Need to optimize performance?

→ Use chunked processing from [pipeline-orchestration.md](pipeline-orchestration.md)
→ Configure performance settings in [configuration.md](../configuration.md)

## Related Documents

- **[Documentation index](../index.md)** - Complete navigation guide
- **[configuration.md](../configuration.md)** - Full configuration examples
- **[data-quality.md](data-quality.md)** - Quality framework details
- **[enrichment-patterns.md](enrichment-patterns.md)** - Enrichment strategy details
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Pipeline patterns details
- **[neo4j-patterns.md](neo4j-patterns.md)** - Graph database patterns details
