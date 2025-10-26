sbir-etl/openspec/changes/validate-enrichment-pipeline-performance/tasks.md
## 1. Pipeline Validation Setup
- [x] 1.1 Create comprehensive test suite for enrichment pipeline (`tests/test_enrichment_pipeline.py`)
  - Notes: Implemented `tests/test_enrichment_pipeline.py` covering unit, integration, and performance checks (includes performance monitor tests and staged large-data scenarios). See `tests/test_enrichment_pipeline.py`.
- [ ] 1.2 Add Dagster asset validation checks for enrichment quality metrics
- [ ] 1.3 Implement automated pipeline smoke tests that run end-to-end
- [ ] 1.4 Create test fixtures with known good/bad enrichment scenarios

## 2. Performance Instrumentation
- [x] 2.1 Create performance monitoring utilities (`src/utils/performance_monitor.py`)
  - Notes: Implemented `src/utils/performance_monitor.py` with `PerformanceMonitor` class, `time_function` and `monitor_memory` decorators, and `time_block` / `monitor_block` context managers. Metrics export and summary helpers included.
- [x] 2.2 Add memory profiling decorators for enrichment functions
  - Notes: `monitor_memory` decorator implemented and used in tests and profiler; falls back to timing-only behavior if `psutil` is not available.
- [x] 2.3 Implement time tracking for file processing operations
  - Notes: Profiling script (`scripts/profile_usaspending_dump.py`) now instruments table sampling with `performance_monitor.monitor_block` and writes timing metrics to per-OID progress files. Also added `time_block` helpers for broader phases.
- [ ] 2.4 Add performance metrics collection to Dagster assets
- [ ] 2.5 Create performance reporting utilities for benchmark results

## 3. Full Dataset Testing Infrastructure
- [ ] 3.1 Update enrichment assets to handle full USAspending recipient data (3.3M+ rows)
- [ ] 3.2 Implement chunked processing for large dataset enrichment
- [x] 3.3 Add progress tracking and resumable processing for long-running enrichment
  - Notes: `scripts/profile_usaspending_dump.py` writes per-OID progress JSON to `reports/progress/<oid>.json` (status, rows scanned, sampled rows, metrics). The profiler supports chunked scanning and can resume/inspect progress via these files.
- [ ] 3.4 Create validation scripts for full dataset match quality assessment
- [ ] 3.5 Add data quality checks for enriched outputs at scale

## 4. Benchmarking and Reporting
- [ ] 4.1 Create benchmarking script (`scripts/benchmark_enrichment.py`) for performance testing
- [ ] 4.2 Implement automated performance regression detection
- [ ] 4.3 Add enrichment quality metrics dashboard/reporting
- [ ] 4.4 Create performance documentation (`docs/performance/enrichment-benchmarks.md`)
- [ ] 4.5 Add CI/CD integration for automated performance testing

## 5. Integration and Validation
- [ ] 5.1 Update existing enrichment assets with performance monitoring
- [ ] 5.2 Add configuration options for performance tuning (chunk sizes, thresholds)
- [ ] 5.3 Implement graceful degradation for memory-constrained environments
- [ ] 5.4 Add comprehensive error handling and recovery for pipeline failures
- [ ] 5.5 Create validation checklist for production deployment readiness