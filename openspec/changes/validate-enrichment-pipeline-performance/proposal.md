# Validate Enrichment Pipeline Performance

## Why
The SBIR-USAspending enrichment pipeline has been implemented with fuzzy matching and Dagster orchestration, but we need to validate end-to-end functionality, measure performance characteristics, and test against full datasets before production deployment. Without comprehensive testing and performance monitoring, we risk:
- Silent failures in the enrichment pipeline that go undetected
- Memory exhaustion or excessive runtime when processing large datasets
- Poor match quality that doesn't meet the 70% coverage target
- Inability to monitor and optimize the system in production

## What Changes
- **End-to-end pipeline validation**: Create comprehensive tests that run the complete Dagster enrichment pipeline from SBIR ingestion through USAspending matching to final enriched output
- **Performance instrumentation**: Add memory/time monitoring to track resource usage during large file processing and enrichment operations
- **Full dataset testing**: Enable and validate enrichment against the complete SBIR dataset (1000+ awards) with full USAspending recipient data
- **Quality metrics**: Implement automated quality checks and reporting for match rates, confidence scores, and enrichment success rates

## Impact
### Affected Specs
- **data-enrichment**: add requirements for pipeline validation, performance monitoring, and full dataset testing
- **pipeline-orchestration**: add requirements for end-to-end testing and performance tracking

### Affected Code / Docs
- `src/assets/sbir_usaspending_enrichment.py`: add performance monitoring and validation checks
- `tests/test_enrichment_pipeline.py` (new): comprehensive pipeline tests
- `src/utils/performance_monitor.py` (new): memory/time tracking utilities
- `scripts/benchmark_enrichment.py` (new): performance benchmarking script
- `docs/performance/enrichment-benchmarks.md` (new): performance testing guide

### Dependencies / Tooling
- Requires access to full USAspending recipient data (3.3M+ rows)
- Memory monitoring requires `psutil` and `memory_profiler` packages
- Performance testing needs representative SBIR dataset (1000+ awards)

### Risks & Mitigations
- **Large dataset processing**: Memory monitoring will help identify bottlenecks before production deployment
- **Test data availability**: Use existing profiling samples for initial validation, escalate for full dataset access
- **Performance regression**: Automated benchmarks will catch performance issues in CI/CD