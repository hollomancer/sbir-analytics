# Quick Reference

Fast lookup for common patterns, configurations, and code snippets used in the SBIR analytics repository.

Note: Values shown here are illustrative. The single source of truth for configuration and defaults is `configuration-patterns.md` and `config/base.yaml`.

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

For full YAML examples, see `configuration-patterns.md`.

- Quality gates: thresholds and actions → `configuration-patterns.md#data-quality-configuration`
- Enrichment: sources, batch processing, confidence → `configuration-patterns.md#enrichment-configuration`
- Pipeline performance: chunking, memory, retries → `configuration-patterns.md#pipeline-orchestration-configuration`
- Neo4j loading: batch size, parallelism, timeouts → `configuration-patterns.md#neo4j-configuration`

## Asset Check Templates

Canonical templates live in `pipeline-orchestration.md#asset-check-implementation`.

## Neo4j Patterns Quick Reference

### Node Creation (Upsert)

```cypher
UNWIND $batch AS row
MERGE (c:Company {uei: row.uei})
SET c.name = row.name,
    c.address = row.address,
    c.updated_at = datetime()
```

### Relationship with Confidence

```cypher
MERGE (a:Award {award_id: $award_id})
MERGE (c:Company {uei: $uei})
MERGE (a)-[r:AWARDED_TO]->(c)
SET r.confidence = $confidence,
    r.method = $method,
    r.created_at = datetime()
```

### Common Constraints

```cypher
CREATE CONSTRAINT unique_company_uei ON (c:Company) ASSERT c.uei IS UNIQUE;
CREATE CONSTRAINT unique_award_id ON (a:Award) ASSERT a.award_id IS UNIQUE;
CREATE CONSTRAINT unique_patent_grant_num ON (p:Patent) ASSERT p.grant_doc_num IS UNIQUE;
```

### Performance Indexes

```cypher
CREATE INDEX idx_company_name ON (c:Company) ON (c.name);
CREATE INDEX idx_award_date ON (a:Award) ON (a.award_date);
CREATE FULLTEXT INDEX idx_company_name_fulltext ON (c:Company) FOR (c.name);
```

## Environment Variables Quick Setup

Prefer `SBIR_ETL__...` overrides that mirror YAML structure. See details in `configuration-patterns.md#environment-variable-overrides`.

Example:

```bash
export SBIR_ETL_ENV=dev
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__PIPELINE__CHUNK_SIZE=20000
```

## Common Commands

### Development Setup

```bash
poetry install
poetry shell
make neo4j-up
```

### Code Quality

```bash
black .
ruff check . --fix
mypy src/
pytest --cov=src
```

### Pipeline Execution

```bash
poetry run dagster dev                    # Start Dagster UI
dagster job execute -f src/definitions.py -j sbir_ingestion_job
dagster job execute -f src/definitions.py -j fiscal_returns_mvp_job      # Fiscal ROI analysis (core)
dagster job execute -f src/definitions.py -j fiscal_returns_full_job     # Fiscal ROI with sensitivity
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
| Fiscal analysis R errors | Check R/rpy2 installation and StateIO package | [configuration-patterns.md](configuration-patterns.md) |

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
→ Configure thresholds in [configuration-patterns.md](configuration-patterns.md)

### Need external data enrichment?

→ Use hierarchical enrichment from [enrichment-patterns.md](enrichment-patterns.md)
→ Configure sources in [configuration-patterns.md](configuration-patterns.md)

### Need to load data to Neo4j?

→ Use batch loading patterns from [neo4j-patterns.md](neo4j-patterns.md)
→ Configure connection in [configuration-patterns.md](configuration-patterns.md)

### Need to optimize performance?

→ Use chunked processing from [pipeline-orchestration.md](pipeline-orchestration.md)
→ Configure performance settings in [configuration-patterns.md](configuration-patterns.md)

## Related Documents

- **[README.md](README.md)** - Complete navigation guide
- **[configuration-patterns.md](configuration-patterns.md)** - Full configuration examples
- **[data-quality.md](data-quality.md)** - Quality framework details
- **[enrichment-patterns.md](enrichment-patterns.md)** - Enrichment strategy details
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Pipeline patterns details
- **[neo4j-patterns.md](neo4j-patterns.md)** - Graph database patterns details