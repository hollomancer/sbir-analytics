# Validate Enrichment Pipeline Performance

## Why
The SBIR-USAspending enrichment pipeline has foundational infrastructure in place (performance monitoring utilities, test suite, profiling capabilities), but critical integration work remains incomplete. Without wiring performance monitoring into Dagster assets and establishing production validation workflows, we cannot safely deploy to production or confidently scale to full datasets. Key risks:
- Performance metrics are collected in CLI tools but not integrated into Dagster orchestration
- No quality gates prevent poor enrichments (match rate < 70%) from flowing downstream
- Missing end-to-end pipeline tests prevent validation before production deployment
- No benchmark baselines or regression detection for performance regression prevention
- Uncertainty on full-dataset (3.3M+ USAspending recipients) handling without memory issues

## What Changes
### Phase 1: Foundation (Critical Path)
- **Dagster asset integration**: Wire performance monitoring into enrichment assets so execution metrics are collected and surfaced in Dagster metadata
- **Quality gate enforcement**: Add Dagster asset checks with match-rate thresholds (≥70%) to block downstream assets on quality failures
- **Benchmarking framework**: Create automated benchmark script and baseline infrastructure for regression detection

### Phase 2: Full Dataset Validation
- **Chunked processing**: Implement chunked/streaming processing within Dagster assets for large datasets (3.3M+ recipient records)
- **End-to-end testing**: Create comprehensive smoke tests that validate complete pipeline execution (ingestion → enrichment → output)
- **Quality reporting**: Add structured quality metrics and reporting for match rates, confidence distributions, and identifier-level breakdowns

### Phase 3: Production Readiness
- **Configuration & tuning**: Add configurable parameters for chunk sizes, memory thresholds, and performance targets
- **Error recovery**: Implement checkpoint-based resumable processing and graceful degradation for memory-constrained environments
- **Deployment validation**: Create production readiness checklist and CI/CD integration for automated performance testing

## Impact

### What IS Implemented
- ✅ Performance monitoring utilities (`src/utils/performance_monitor.py`): time/memory tracking decorators and context managers
- ✅ Unit test suite (`tests/test_enrichment_pipeline.py`): functional enrichment tests with performance instrumentation
- ✅ CLI profiling infrastructure (`scripts/profile_usaspending_dump.py`): chunked processing, progress tracking, timing metrics
- ✅ Enrichment assets exist (`src/assets/sbir_usaspending_enrichment.py`): basic Dagster orchestration in place

### What Remains (Scope of This Change)
- ❌ Dagster asset performance integration (metrics collection during asset execution)
- ❌ Quality gate asset checks (enforce match-rate thresholds)
- ❌ Benchmark script and baseline storage
- ❌ End-to-end pipeline smoke tests
- ❌ Chunked processing in Dagster assets (not just CLI)
- ❌ Production deployment checklist

### Affected Specs
- **data-enrichment**: Add requirements for quality gates, full dataset handling, performance monitoring, and automated regression detection
- **pipeline-orchestration**: Add requirements for asset-level performance tracking, quality validation, and large dataset chunking

### Affected Code / Docs
- `src/assets/sbir_usaspending_enrichment.py`: Add performance monitoring context managers, asset checks, and metadata emission
- `src/assets/sbir_ingestion.py`: Add performance monitoring to raw data extraction
- `src/utils/performance_reporting.py` (new): Benchmark comparison, regression detection, HTML/Markdown reports
- `tests/test_enrichment_pipeline.py`: Add Dagster-native end-to-end smoke tests
- `scripts/benchmark_enrichment.py` (new): Automated performance baseline and regression detection
- `config/base.yaml`: Add performance tuning parameters (chunk sizes, memory thresholds, match-rate targets)
- `docs/performance/enrichment-benchmarks.md` (new): Performance expectations, tuning guide, scaling recommendations
- `docs/DEPLOYMENT_CHECKLIST.md` (new): Pre-production validation requirements

### Dependencies / Tooling
- ✅ `psutil` (already available): memory monitoring
- ✅ Dagster (already in use): asset checks, metadata, context
- ✅ pandas/DuckDB (already in use): data processing
- Performance regression storage: JSON file archive (reports/benchmarks/) initially; can migrate to centralized DB later
- HTML reporting (optional): Plotly or similar for dashboard visualization

### Risks & Mitigations
| Risk | Mitigation |
|------|-----------|
| Large dataset memory exhaustion | Implement chunked processing in Dagster assets (task 3.2) with configurable chunk sizes and memory monitoring |
| Poor match quality not detected | Add quality gate asset checks that block downstream on match-rate < 70% (task 1.2) |
| Performance regressions unnoticed | Establish benchmark baseline and automated regression detection (tasks 4.1, 4.2) |
| Production deployment without validation | Create deployment readiness checklist and smoke tests (tasks 1.3, 5.5) |
| CLI profiling not integrated into ops | Wire performance monitoring into Dagster assets (task 2.4) so metrics flow to production observability |

## Success Criteria
- [ ] Performance metrics collected and surfaced in Dagster asset runs
- [ ] Quality gates enforce ≥70% match rate; downstream assets block on failure
- [ ] Benchmark baseline established; regression detection working in CI/CD
- [ ] End-to-end smoke tests pass (ingestion → enrichment → validation)
- [ ] Chunked processing handles 3.3M+ USAspending recipients without memory exhaustion
- [ ] Production deployment checklist complete and validated