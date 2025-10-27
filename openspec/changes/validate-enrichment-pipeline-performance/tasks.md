## 1. Pipeline Validation Setup

- [x] 1.1 Create comprehensive test suite for enrichment pipeline (`tests/test_enrichment_pipeline.py`)
  - **Status:** COMPLETE
  - **Evidence:** Unit and integration tests implemented covering enrichment functionality, performance monitoring integration, and quality metrics validation
  - **Details:** File includes sample SBIR data fixtures, enrichment operation tests, and performance monitor integration tests

- [ ] 1.2 Add Dagster asset validation checks for enrichment quality metrics (block downstream on match-rate thresholds)
  - **Status:** NOT STARTED
  - **Blocker:** None (can start immediately)
  - **Priority:** HIGH
  - **Details:** Requires adding `@asset_check` decorators to `enriched_sbir_awards` asset to enforce match-rate >= 70% threshold and block downstream assets on failure
  - **Acceptance Criteria:** 
    - Asset check validates match_rate >= 0.70
    - Downstream assets blocked when check fails
    - Check metadata visible in Dagster UI

- [ ] 1.3 Implement automated Dagster pipeline smoke tests (`sbir_etl_job` materialization) that run end-to-end
  - **Status:** NOT STARTED
  - **Blocker:** None (can start immediately, complements 1.2)
  - **Priority:** HIGH
  - **Details:** Create `tests/test_dagster_enrichment_pipeline.py` with Dagster context to test complete asset materialization pipeline: `raw_sbir_awards` → `validated_sbir_awards` → `enriched_sbir_awards`
  - **Acceptance Criteria:**
    - All assets materialize successfully
    - Data flows correctly between stages
    - Output validates against quality thresholds

- [ ] 1.4 Create/maintain fixtures with known good/bad enrichment scenarios (feed smoke tests + quality gates)
  - **Status:** NOT STARTED
  - **Blocker:** None (independent task)
  - **Priority:** MEDIUM
  - **Details:** Organize test fixtures in `tests/fixtures/enrichment_scenarios.json` with known good cases (high confidence matches) and bad cases (no matches, low confidence) to feed into smoke tests and quality gate validation
  - **Acceptance Criteria:**
    - Good scenario fixtures pass quality gates
    - Bad scenario fixtures trigger expected failures

## 2. Performance Instrumentation

- [x] 2.1 Create performance monitoring utilities (`src/utils/performance_monitor.py`)
  - **Status:** COMPLETE
  - **Evidence:** Full implementation with PerformanceMonitor class, time_function/monitor_memory decorators, time_block/monitor_block context managers, metrics collection, export, and summary reporting
  - **Details:** Includes graceful fallback behavior when psutil unavailable; global instance and convenience helpers provided

- [x] 2.2 Add memory profiling decorators for enrichment functions
  - **Status:** COMPLETE
  - **Evidence:** `monitor_memory` decorator implemented in PerformanceMonitor class with proper fallback handling
  - **Details:** Used in tests and profiling scripts; falls back to timing-only when psutil unavailable

- [x] 2.3 Implement time tracking for file processing operations
  - **Status:** COMPLETE
  - **Evidence:** `scripts/profile_usaspending_dump.py` instruments operations with `monitor_block()` and `time_block()` context managers
  - **Details:** Per-OID progress files written to `reports/progress/<oid>.json` with timing metrics; supports chunked scanning and resumable processing
  - **Note:** CLI-only implementation; Dagster asset integration is separate task (2.4)

- [ ] 2.4 Wire performance metrics collection into Dagster assets (ingestion + enrichment metadata)
  - **Status:** NOT STARTED
  - **Blocker:** None (foundation in place from 2.1-2.3)
  - **Priority:** CRITICAL
  - **Details:** Update `sbir_usaspending_enrichment.py` and `sbir_ingestion.py` to wrap core operations with `monitor_block()` context managers and emit metrics in asset metadata. Update `sbir_ingestion.py` raw_sbir_awards asset to track extraction performance.
  - **Acceptance Criteria:**
    - Performance metrics collected during asset execution
    - Metrics included in Dagster asset metadata (duration, memory delta, peak memory)
    - Metrics visible in Dagster UI run details
    - No performance overhead from monitoring (< 5% runtime increase)

- [ ] 2.5 Create performance reporting utilities for benchmark results (persist + visualize summaries)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 2.4 (metrics must flow through Dagster)
  - **Priority:** HIGH
  - **Details:** Create `src/utils/performance_reporting.py` to generate markdown reports from metrics, compare vs. historical baselines, and optionally emit HTML summaries. Integrate with benchmark script (4.1).
  - **Acceptance Criteria:**
    - Markdown report generated showing timing and memory stats
    - Benchmark comparison against baseline (if baseline exists)
    - HTML report available (optional: Plotly/similar)

- [ ] 2.6 Aggregate pipeline-level metrics and surface threshold-based alerts (Dagster metadata or external store)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 2.4 (metrics collection) and 2.5 (reporting)
  - **Priority:** MEDIUM
  - **Details:** Implement alert rules in Dagster asset or Sensor: memory delta > 500MB → WARNING; enrichment time > 5s per record → WARNING; match rate < 70% → FAILURE (surfaces as asset check failure)
  - **Acceptance Criteria:**
    - Alerts generated when thresholds exceeded
    - Alerts visible in Dagster UI and/or logs
    - Threshold values configurable in config/base.yaml

## 3. Full Dataset Testing Infrastructure

- [ ] 3.1 Update Dagster enrichment assets to handle full USAspending recipient data (3.3M+ rows) without exhausting memory
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 2.4 (metrics), 3.2 (chunking)
  - **Priority:** HIGH
  - **Details:** Implement chunked loading and streaming enrichment in `enriched_sbir_awards` asset. Load recipient data in batches; process enrichment per batch; combine results. Add memory monitoring to detect and handle resource constraints.
  - **Acceptance Criteria:**
    - Full 3.3M+ recipient dataset loads without OOM
    - Processing completes in < 30 minutes for SBIR sample
    - Memory peak < 2GB on production-size hardware

- [ ] 3.2 Implement chunked/streaming processing for enrichment within Dagster (not just CLI scripts)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 2.4 (metrics collection framework)
  - **Priority:** HIGH
  - **Details:** Refactor `enriched_sbir_awards` asset to use configurable chunk sizes (from config/base.yaml). Add Dagster dynamic outputs or chunked I/O to stream results. Track progress per chunk.
  - **Acceptance Criteria:**
    - Chunking configurable via config/base.yaml
    - Progress tracked per chunk in logs
    - Results correctly combined (no data loss/duplication)

- [x] 3.3 Add progress tracking and resumable processing for long-running enrichment
  - **Status:** COMPLETE (CLI-only)
  - **Evidence:** `scripts/profile_usaspending_dump.py` writes per-OID progress to `reports/progress/<oid>.json` with status, rows scanned, sampled rows, and metrics
  - **Details:** Supports chunked scanning and resume via progress file inspection
  - **Note:** CLI-only; Dagster asset resume capability is separate future enhancement

- [ ] 3.4 Create validation scripts/assets for full dataset match quality assessment (include identifier-level breakdowns)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 3.1 (full dataset processing complete)
  - **Priority:** MEDIUM
  - **Details:** Create `scripts/validate_enrichment_quality.py` to analyze enriched output with breakdowns by: award phase (Phase 1/2), company size, identifier type (UEI vs DUNS). Generate HTML report with charts.
  - **Acceptance Criteria:**
    - Match rates calculated per phase, size, identifier type
    - HTML report generated with tables and charts
    - Runnable via CLI or as Dagster asset

- [ ] 3.5 Add data quality checks for enriched outputs at scale (enforce thresholds, detect regressions)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 3.4 (quality script exists) and 4.2 (baseline storage)
  - **Priority:** HIGH
  - **Details:** Add quality gate logic to enrichment asset: compare current match_rate vs. historical baseline; fail asset if regression > 5%. Store baseline after each successful run.
  - **Acceptance Criteria:**
    - Baseline stored after successful enrichment
    - Current run compared vs. baseline
    - Asset fails/warns on regression > 5%

- [ ] 3.6 Surface progress/resume metadata in Dagster asset metadata for operator visibility
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 3.2 (chunking implementation)
  - **Priority:** MEDIUM
  - **Details:** Add metadata to enrichment asset: progress_records_processed, progress_checkpoint (timestamp), progress_resumable (bool), estimated_time_remaining
  - **Acceptance Criteria:**
    - Progress metadata visible in Dagster UI
    - Operators can monitor long-running enrichments
    - Resume information accurate and actionable

## 4. Benchmarking and Reporting

- [ ] 4.1 Create benchmarking script (`scripts/benchmark_enrichment.py`) for performance testing
  - **Status:** NOT STARTED
  - **Blocker:** None (foundation in place from 2.1)
  - **Priority:** CRITICAL
  - **Details:** Create automated benchmark script that: loads SBIR sample data; runs enrichment with performance monitoring enabled; outputs timing and memory metrics to JSON; optionally compares to historical baseline (if baseline exists)
  - **Acceptance Criteria:**
    - Script runs enrichment on sample data (100-1000 SBIR records)
    - Metrics output: total time, records/sec, peak memory, average memory delta
    - Baseline comparison when baseline file exists
    - Results persisted to `reports/benchmarks/<timestamp>.json`

- [ ] 4.2 Implement automated performance regression detection (compare benchmarks vs historical runs)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 4.1 (benchmark script exists)
  - **Priority:** MEDIUM
  - **Details:** Enhance benchmark script to load historical baseline and flag regressions: time increase > 10% or memory increase > 20% → WARNING; time increase > 25% or memory increase > 50% → FAILURE
  - **Acceptance Criteria:**
    - Historical baseline loaded from file
    - Regressions detected and reported
    - Regression report includes delta and percent change

- [ ] 4.3 Add enrichment quality metrics dashboard/reporting (match rates, confidence distribution)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 3.4 (quality validation script)
  - **Priority:** LOW
  - **Details:** Create HTML/Plotly dashboard showing: match rate trends over time, fuzzy score distribution (histogram), match method breakdown (pie chart), unmatched awards by phase
  - **Acceptance Criteria:**
    - Dashboard generated as HTML file
    - Charts update from latest enrichment run
    - Trends visible across historical runs

- [ ] 4.4 Create performance documentation (`docs/performance/enrichment-benchmarks.md`)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 4.1 (benchmark baselines established)
  - **Priority:** HIGH
  - **Details:** Document baseline performance expectations, tuning recommendations (chunk sizes, memory thresholds), scaling guidance for large datasets, and troubleshooting common performance issues
  - **Acceptance Criteria:**
    - Baseline metrics documented
    - Tuning parameters explained
    - Scaling guidance for 1M, 10M, 100M+ record datasets
    - Troubleshooting section for common issues

- [ ] 4.5 Add CI/CD integration for automated performance testing (record + diff metrics per build)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 4.1 (benchmark script), 4.2 (regression detection)
  - **Priority:** MEDIUM
  - **Details:** Add GitHub Actions workflow to run benchmark script on each PR, compare against main branch baseline, and comment on PR with performance delta
  - **Acceptance Criteria:**
    - Benchmark script runs in CI
    - Results compared to baseline
    - PR comment includes performance delta
    - Build fails if performance regression > 25%

- [ ] 4.6 Persist benchmarking + quality metrics to a long-lived store for historical analysis
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 4.1, 3.4 (metrics generated)
  - **Priority:** MEDIUM
  - **Details:** Archive benchmark and quality metrics to `reports/benchmarks/<date>.json` and `reports/quality/<date>.json`. Implement simple historical analysis script to query and compare metrics across time.
  - **Acceptance Criteria:**
    - Metrics archived with timestamps
    - Historical query script works
    - Trends visible across weeks/months of runs

## 5. Integration and Validation

- [ ] 5.1 Update existing enrichment assets with performance monitoring + metadata emission
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 2.4 (monitoring framework ready)
  - **Priority:** HIGH
  - **Details:** Update all enrichment-related assets (`raw_sbir_awards`, `validated_sbir_awards`, `enriched_sbir_awards`, `sbir_usaspending_enrichment_report`) to wrap core operations with performance monitoring and emit metrics in asset metadata
  - **Acceptance Criteria:**
    - All enrichment assets emit performance metadata
    - Metadata visible in Dagster UI
    - No functional changes to asset outputs

- [ ] 5.2 Add configuration options for performance tuning (chunk sizes, thresholds, retry/backoff)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 3.2 (chunking implemented)
  - **Priority:** MEDIUM
  - **Details:** Add to `config/base.yaml` under `enrichment.performance`: chunk_size (default 10000), memory_threshold_mb (default 2048), match_rate_threshold (default 0.70), timeout_seconds (default 300), retry_backoff (default "exponential")
  - **Acceptance Criteria:**
    - Configuration parameters loaded at startup
    - Assets respect configurable parameters
    - Documentation for each parameter in config file

- [ ] 5.3 Implement graceful degradation for memory-constrained environments (fallback chunk sizes, spill-to-disk)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 3.2 (chunking framework)
  - **Priority:** MEDIUM
  - **Details:** Add logic to enrichment asset to detect memory pressure: if memory usage > 80% available → reduce chunk size by half; if > 95% → spill to disk (parquet temp files in /tmp or configured location)
  - **Acceptance Criteria:**
    - Memory pressure detected correctly
    - Chunk sizes reduced when needed
    - Spill-to-disk works without data loss
    - No performance degradation on well-provisioned systems

- [ ] 5.4 Add comprehensive error handling and recovery for pipeline failures (resume points, retries, notifications)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 3.2 (chunking), 3.3 (progress tracking)
  - **Priority:** MEDIUM
  - **Details:** Implement checkpoint-based recovery in enrichment asset: save progress every N chunks; on failure, resume from last checkpoint; emit Dagster event on recovery. Add retry logic with exponential backoff.
  - **Acceptance Criteria:**
    - Checkpoint saved every 10% or N chunks
    - Resume from checkpoint on retry
    - Duplicate processing avoided
    - Dagster event emitted on recovery

- [ ] 5.5 Create validation checklist for production deployment readiness (smoke tests, quality gates, benchmarks)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 1.2, 1.3, 4.1, 4.4 (all validation components)
  - **Priority:** HIGH
  - **Details:** Create `docs/DEPLOYMENT_CHECKLIST.md` with pre-production requirements: all asset checks passing (>70% match rate), performance baseline recorded, full dataset tested on staging, monitoring/alerting configured, documentation reviewed
  - **Acceptance Criteria:**
    - Checklist document complete
    - All items tied to specific tests/metrics
    - Deployment blocked until all items checked

- [ ] 5.6 Integrate regression alerts with CI notifications (tie into tasks 2.6 & 4.2)
  - **Status:** NOT STARTED
  - **Blocker:** Depends on 2.6 (alert logic), 4.2 (regression detection), 4.5 (CI integration)
  - **Priority:** LOW
  - **Details:** Configure GitHub Actions or Slack integration to send alerts when performance or quality regressions detected. Tie into tasks 2.6 (pipeline metrics) and 4.2 (benchmark regression).
  - **Acceptance Criteria:**
    - Alerts sent on regression detection
    - Alerts include metrics and delta
    - Team can be notified via Slack or GitHub comments

## Summary

**Completion Status:** 4/30 tasks complete = 13%

**Completed Tasks:**
- 1.1 Test suite
- 2.1 Performance monitoring utilities
- 2.2 Memory profiling decorators
- 2.3 Time tracking for file processing (CLI-only)
- 3.3 Progress tracking (CLI-only)

**Critical Path (Unblock Most Work):**
1. 2.4 – Wire performance metrics into Dagster assets (unblocks: 2.5, 2.6, 3.1, 3.2, 5.1, 5.4)
2. 1.2 – Add asset quality checks (unblocks: 1.3, 1.4, 5.5)
3. 4.1 – Create benchmark script (unblocks: 4.2, 4.3, 4.4, 4.5, 4.6)

**Phase Breakdown:**
- **Phase 1 (Foundation):** 2.4, 1.2, 4.1 — enables all subsequent work
- **Phase 2 (Core Validation):** 1.3, 1.4, 3.2, 3.4 — full pipeline and quality validation
- **Phase 3 (Production Ready):** 4.4, 5.2, 5.5, 5.6 — documentation, config, and operational integration
- **Phase 4 (Nice-to-Have):** 4.3, 5.3, 5.4 — dashboards, degradation, error recovery (can defer)