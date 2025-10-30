# Quick Reference

Fast lookup for common patterns, configurations, and code snippets used in the SBIR ETL Pipeline.

## Quality Thresholds Quick Lookup

| Field | Completeness | Validity Range | Notes |
|-------|-------------|----------------|-------|
| `award_id` | 100% | - | Primary key, no duplicates |
| `company_name` | 95% | - | Required for enrichment |
| `award_amount` | 98% | $0 - $5M | Phase II max $5M |
| `naics_code` | 85% | Valid NAICS | Enrichment target |
| `award_date` | 95% | 1983-2025 | SBIR program range |

## Enrichment Confidence Levels

| Level | Range | Sources | Use Case |
|-------|-------|---------|----------|
| **High** | ≥0.80 | Exact matches, API lookups | Production ready |
| **Medium** | 0.60-0.79 | Fuzzy matches, validated proximity | Review recommended |
| **Low** | <0.60 | Agency defaults, sector fallbacks | Manual review required |

## Common Configuration Snippets

### Quality Gates
```yaml
data_quality:
  thresholds:
    max_duplicate_rate: 0.10      # Block if >10% duplicates
    max_missing_rate: 0.15        # Warn if >15% missing
    min_enrichment_success: 0.90  # Target 90% enrichment
```

### Enrichment Batch Processing
```yaml
enrichment:
  batch_size: 100
  max_retries: 3
  timeout_seconds: 30
  rate_limit_per_second: 10.0
```

### Pipeline Performance
```yaml
pipeline:
  chunk_size: 10000
  memory_threshold_mb: 2048
  timeout_seconds: 300
performance:
  batch_size: 1000
  parallel_threads: 4
```

### Neo4j Loading
```yaml
neo4j:
  loading:
    batch_size: 1000
    parallel_threads: 4
    transaction_timeout_seconds: 300
```

## Asset Check Templates

### Completeness Check
```python
@asset_check(asset=my_asset)
def completeness_check(my_asset: pd.DataFrame) -> AssetCheckResult:
    required_fields = ["field1", "field2", "field3"]
    coverage = {
        field: 1.0 - (my_asset[field].isna().sum() / len(my_asset))
        for field in required_fields
    }
    min_coverage = min(coverage.values())
    return AssetCheckResult(
        passed=min_coverage >= 0.95,
        metadata={"min_coverage": min_coverage, "field_coverage": coverage}
    )
```

### Success Rate Check
```python
@asset_check(asset=enriched_data)
def success_rate_check(enriched_data: pd.DataFrame) -> AssetCheckResult:
    success_count = enriched_data["enriched_field"].notna().sum()
    success_rate = success_count / len(enriched_data)
    return AssetCheckResult(
        passed=success_rate >= 0.90,
        metadata={
            "success_rate": success_rate,
            "success_count": success_count,
            "total_count": len(enriched_data)
        }
    )
```

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

### Development
```bash
export SBIR_ETL_ENV=dev
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__NEO4J__PASSWORD="dev_password"
```

### Production
```bash
export SBIR_ETL_ENV=prod
export SBIR_ETL__NEO4J__URI="bolt://prod-neo4j:7687"
export SBIR_ETL__NEO4J__PASSWORD="secure_prod_password"
export SBIR_ETL__ENRICHMENT__SAM_GOV_API_KEY="prod_api_key"
```

### Performance Tuning
```bash
export SBIR_ETL__PIPELINE__CHUNK_SIZE=20000
export SBIR_ETL__PERFORMANCE__BATCH_SIZE=2000
export SBIR_ETL__PERFORMANCE__PARALLEL_THREADS=8
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

### Performance Issues

| Symptom | Likely Cause | Quick Fix |
|---------|--------------|-----------|
| Slow enrichment | API rate limits | Increase batch_size, reduce rate_limit |
| High memory usage | Large chunks | Reduce chunk_size, enable memory monitoring |
| Neo4j timeouts | Large transactions | Reduce batch_size, increase timeout |
| Asset execution slow | Sequential processing | Enable parallel processing |

## Decision Trees

### When to Use Which Pattern?

**Need data validation?**
→ Use asset checks from [pipeline-orchestration.md](pipeline-orchestration.md)
→ Configure thresholds in [configuration-patterns.md](configuration-patterns.md)

**Need external data enrichment?**
→ Use hierarchical enrichment from [enrichment-patterns.md](enrichment-patterns.md)
→ Configure sources in [configuration-patterns.md](configuration-patterns.md)

**Need to load data to Neo4j?**
→ Use batch loading patterns from [neo4j-patterns.md](neo4j-patterns.md)
→ Configure connection in [configuration-patterns.md](configuration-patterns.md)

**Need to optimize performance?**
→ Use chunked processing from [pipeline-orchestration.md](pipeline-orchestration.md)
→ Configure performance settings in [configuration-patterns.md](configuration-patterns.md)

## Related Documents

- **[README.md](README.md)** - Complete navigation guide
- **[configuration-patterns.md](configuration-patterns.md)** - Full configuration examples
- **[data-quality.md](data-quality.md)** - Quality framework details
- **[enrichment-patterns.md](enrichment-patterns.md)** - Enrichment strategy details
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Pipeline patterns details
- **[neo4j-patterns.md](neo4j-patterns.md)** - Graph database patterns details