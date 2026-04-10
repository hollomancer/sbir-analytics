# Pipeline Orchestration Patterns

## Dagster Asset-Based Architecture

The system uses Dagster's asset-based design for pipeline orchestration, where each data entity is represented as a Dagster asset with explicit dependency declarations.

## Five-Stage ETL Pipeline

```text
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   EXTRACT   │────▶│   VALIDATE  │────▶│  ENRICH     │────▶│  TRANSFORM  │────▶│    LOAD     │
│             │     │             │     │             │     │             │     │             │
│ Download    │     │ Schema      │     │ SAM.gov API │     │ Normalize   │     │ Neo4j       │
│ CSV/API     │     │ Quality     │     │ USPTO Data  │     │ Standardize │     │ Nodes/Edges │
│ Parse       │     │ Dedup       │     │ Text Enrich │     │ Calculate   │     │ Indexes     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
      │                   │                   │                   │                   │
      ▼                   ▼                   ▼                   ▼                   ▼
  raw/*.csv         validated/           enriched/           transformed/        Neo4j Database
  raw/*.json        ├─ pass/             ├─ success/         ├─ companies/
                    └─ fail/             └─ partial/         ├─ awards/
                                                              └─ patents/
```

## Asset Organization

### Asset Dependencies

- Explicit dependency declarations in function signatures
- Automatic execution order resolution by Dagster
- Upstream dependency materialization before asset execution

### Asset Groups

Assets organized by functional area:

- `sbir_ingestion` - SBIR data extraction and validation
- `enrichment` - External data enrichment
- `cet_pipeline` - CET classification
- `patent_loading` - USPTO patent data processing
- `graph_construction` - Neo4j loading and relationship creation

### Asset Naming Conventions

- Stage prefix: `raw_`, `validated_`, `enriched_`, `transformed_`, `loaded_`
- Entity type: `sbir_awards`, `companies`, `patents`, `contracts`
- Clear, descriptive names indicating data state and content

## Quality Gates and Asset Checks

### Asset Check Integration

- Asset checks co-located with assets
- Quality thresholds enforced at each stage
- Failed checks block downstream asset execution
- Quality metrics stored in asset metadata

### Quality Gate Types

- **Completeness checks**: Required field coverage
- **Uniqueness checks**: Primary key constraints
- **Validity checks**: Value range validation
- **Success rate checks**: Enrichment and processing success rates

### Blocking Behavior

- ERROR severity issues block downstream processing
- WARNING severity issues log but allow continuation
- Quality gate failures visible in Dagster UI with clear reasons

## Run Tracking and Metadata

### Run Context

- Unique run ID generation and tracking
- Run timestamp and duration recording
- Run ID accessible to all assets during execution

### Asset Execution Metadata

- Records processed count
- Execution duration and throughput
- Memory usage and performance metrics
- Quality metrics and success rates
- Error counts and issue summaries

### Metadata Visibility

- Asset metadata visible in Dagster UI
- Historical run comparison
- Performance trend analysis
- Quality metric dashboards

## Processing Modes

### Full Refresh Mode

- All assets materialized from scratch
- Existing data replaced completely
- Clean slate processing for data consistency

### Incremental Mode

- Only new or modified source data processed
- Existing processed data preserved
- Efficient updates for large datasets
- Change detection and delta processing

## Performance Optimization

### Chunked Processing

- Large datasets divided into configurable chunks
- Memory-constrained processing support
- Dynamic chunk size adjustment based on available resources
- Progress tracking for long-running operations

### Batch Operations

- Batch writes to Neo4j for performance
- Configurable batch sizes per operation type
- Transaction management for data consistency
- Parallel processing where possible

### Memory Management

- Memory usage monitoring and alerting
- Memory pressure detection and response
- Spill-to-disk strategies for large datasets
- Resource-aware processing decisions

## Configuration

Pipeline processing, performance tuning, and orchestration settings are configured in YAML. See **[configuration-patterns.md](configuration-patterns.md)** for complete configuration examples including:

- Pipeline processing configuration (chunk sizes, memory thresholds, timeouts)
- Performance tuning settings (batch sizes, parallel threads, retry strategies)
- Asset execution configuration
- Memory management settings

## Error Handling and Recovery

### Error Context

- Detailed error logging with context
- Asset execution state preservation
- Partial result protection (no corruption)
- Clear error messages and troubleshooting guidance

### Recovery Strategies

- Automatic retry with exponential backoff
- Graceful degradation on resource constraints
- Resume capability for interrupted processing
- Rollback support for failed transactions

### Monitoring and Alerting

- Pipeline health monitoring
- Performance regression detection
- Quality threshold breach alerts
- Resource utilization monitoring

## Asset Check Implementation

### Quality Gate Integration

Asset checks are co-located with assets and enforce quality thresholds at each pipeline stage. Failed checks block downstream asset execution.

### Completeness Check Pattern

```python
@asset_check(asset=validated_sbir_awards)
def sbir_awards_completeness_check(validated_sbir_awards: pd.DataFrame) -> AssetCheckResult:
    required_fields = ["award_id", "company_name", "award_amount"]
    coverage = {
        field: 1.0 - (validated_sbir_awards[field].isna().sum() / len(validated_sbir_awards))
        for field in required_fields
    }
    min_coverage = min(coverage.values())
    passed = min_coverage >= 0.95

    return AssetCheckResult(
        passed=passed,
        metadata={"min_coverage": min_coverage, "field_coverage": coverage}
    )
```

### Success Rate Check Pattern

```python
@asset_check(asset=enriched_sbir_awards)
def enrichment_success_rate_check(enriched_sbir_awards: pd.DataFrame) -> AssetCheckResult:
    enriched_count = enriched_sbir_awards["sam_gov_data"].notna().sum()
    enrichment_rate = enriched_count / len(enriched_sbir_awards)

    return AssetCheckResult(
        passed=enrichment_rate >= 0.90,
        metadata={
            "enrichment_rate": enrichment_rate,
            "enriched_count": enriched_count,
            "total_count": len(enriched_sbir_awards)
        }
    )
```

### How to Add a New Quality Gate

1. Co-locate the check with the target asset in `src/assets/...`.
2. Name the function `<asset_name>_<check_purpose>_check`.
3. Read thresholds from loaded config (e.g., `config.data_quality.thresholds`).
4. Compute metrics and return `AssetCheckResult(passed=..., metadata=...)`.
5. Use ERROR/WARNING semantics to block or continue downstream assets.
6. Add the check to Dagster jobs if needed and verify in the UI.

### Performance Monitoring Integration

### Asset Execution Metadata

- Records processed count
- Execution duration and throughput
- Memory usage and performance metrics
- Quality metrics and success rates
- Error counts and issue summaries

### Performance Metrics Collection

- Execution time per enrichment source
- Memory usage during processing
- Throughput (records/second)
- API response times and error rates
- Success rate tracking by source

## Best Practices

### Asset Design

- Single responsibility per asset
- Clear input/output contracts
- Idempotent operations
- Comprehensive error handling

### Dependency Management

- Explicit dependency declarations
- Minimal coupling between assets
- Clear data contracts between stages
- Version compatibility considerations

### Performance Considerations

- Resource-aware processing
- Configurable performance parameters
- Memory usage optimization
- Parallel processing where beneficial

### Monitoring and Observability

- Comprehensive logging with context
- Performance metric collection
- Quality metric tracking
- Historical trend analysis

## Related Documents

- **[configuration-patterns.md](configuration-patterns.md)** - Complete pipeline and performance configuration examples
- **[data-quality.md](data-quality.md)** - Quality framework integrated with asset checks
- **[enrichment-patterns.md](enrichment-patterns.md)** - Enrichment performance monitoring patterns
- **[neo4j-patterns.md](neo4j-patterns.md)** - Graph database loading patterns
- **[structure.md](structure.md)** - Code organization and asset structure
- **[quick-reference.md](quick-reference.md)** - Asset check templates and configuration snippets
