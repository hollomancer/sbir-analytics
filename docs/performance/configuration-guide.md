# Enrichment Performance Configuration Guide

**Last Updated:** January 2024  
**Audience:** DevOps, System Administrators, Performance Engineers

---

## Overview

The enrichment pipeline provides configurable performance tuning parameters to optimize for your specific hardware and workload requirements. All parameters are located in `config/base.yaml` under the `enrichment.performance` section.

---

## Configuration Parameters

### `chunk_size`

**Type:** Integer  
**Default:** 25000  
**Range:** 1000 - 100000  
**Unit:** Records per chunk

**Description:**  
Number of records to process in memory at once during enrichment. Larger chunks are faster but consume more memory.

**Effect:**
- **Higher values (50000+):** Faster processing, higher throughput, more memory consumption
- **Lower values (5000-10000):** Slower processing, lower memory usage, more I/O overhead
- **Too high:** Risk of out-of-memory errors
- **Too low:** Increased processing time and I/O overhead

**Tuning Guide:**

For memory-constrained systems (4GB RAM):
```yaml
enrichment:
  performance:
    chunk_size: 5000
```

For balanced systems (8GB RAM):
```yaml
enrichment:
  performance:
    chunk_size: 25000  # Default
```

For high-performance systems (16GB+ RAM):
```yaml
enrichment:
  performance:
    chunk_size: 100000
```

**Impact:**
- Throughput: Roughly linear with chunk size (larger = faster)
- Memory: Linear with chunk size
- I/O: Inverse with chunk size (smaller = more I/O operations)

---

### `memory_threshold_mb`

**Type:** Integer  
**Default:** 2048  
**Unit:** Megabytes (MB)

**Description:**  
Memory threshold at which the enrichment process triggers memory conservation measures (reduce chunk size, spill to disk, or fail gracefully).

**Effect:**
- If memory usage > threshold: System reduces chunk size or spills to disk
- Prevents out-of-memory errors
- Allows predictable memory consumption

**Tuning Guide:**

For memory-constrained systems (< 4GB available):
```yaml
enrichment:
  performance:
    memory_threshold_mb: 1024  # 1GB
```

For balanced systems (8GB+ available):
```yaml
enrichment:
  performance:
    memory_threshold_mb: 2048  # 2GB (default)
```

For high-memory systems (16GB+ available):
```yaml
enrichment:
  performance:
    memory_threshold_mb: 8192  # 8GB
```

**Recommendation:**
Set to 70-80% of available system memory. For example:
- 4GB available → set to 2048 MB (50% safe margin)
- 8GB available → set to 4096 MB (50% safe margin)
- 16GB available → set to 8192 MB (50% safe margin)

---

### `match_rate_threshold`

**Type:** Float (0.0 - 1.0)  
**Default:** 0.70  
**Unit:** Fraction (0.70 = 70%)

**Description:**  
Quality gate threshold. If the enrichment match rate falls below this percentage, the enrichment asset fails and blocks downstream processing.

**Effect:**
- Match rate < threshold: Asset check fails, stops downstream
- Match rate >= threshold: Asset check passes, continues
- Higher threshold = stricter quality requirement
- Lower threshold = more lenient

**Tuning Guide:**

For compliance-focused deployments (high quality required):
```yaml
enrichment:
  performance:
    match_rate_threshold: 0.85  # 85% required
```

For balanced deployments (production default):
```yaml
enrichment:
  performance:
    match_rate_threshold: 0.70  # 70% (default)
```

For exploratory/testing deployments (lenient):
```yaml
enrichment:
  performance:
    match_rate_threshold: 0.60  # 60%
```

**Note:** This threshold should match the quality expectations for your use case. Historical data shows:
- Older SBIR awards (pre-2015): ~60-65% typical match rate
- Recent SBIR awards (2020+): ~70-75% typical match rate
- Average across all years: ~70%

---

### `timeout_seconds`

**Type:** Integer  
**Default:** 300  
**Unit:** Seconds

**Description:**  
Maximum time allowed to process a single chunk. If processing exceeds this time, the chunk fails and triggers retry logic.

**Effect:**
- Processing takes longer than timeout: Chunk fails
- Too short: May fail legitimate slow operations
- Too long: Allows processing to hang indefinitely

**Tuning Guide:**

For fast systems with small chunks (5000 records):
```yaml
enrichment:
  performance:
    timeout_seconds: 120  # 2 minutes
```

For balanced systems with standard chunks (25000 records):
```yaml
enrichment:
  performance:
    timeout_seconds: 300  # 5 minutes (default)
```

For slow systems or complex fuzzy matching:
```yaml
enrichment:
  performance:
    timeout_seconds: 600  # 10 minutes
```

**Expected Processing Times:**
- 5K records: 30-60 seconds
- 25K records: 150-300 seconds (2.5-5 minutes)
- 50K records: 300-600 seconds (5-10 minutes)
- Fuzzy matching adds 50-100% overhead

---

### `retry_backoff`

**Type:** String  
**Default:** exponential  
**Valid Values:** "fixed", "linear", "exponential"

**Description:**  
Retry backoff strategy when a chunk fails to process.

**Strategies:**

**fixed:**
- Wait same amount between retries
- Example: 1s, 1s, 1s
- Use for: Transient network issues

```yaml
enrichment:
  performance:
    retry_backoff: fixed
```

**linear:**
- Wait increases linearly
- Example: 1s, 2s, 3s
- Use for: Moderate resource contention

```yaml
enrichment:
  performance:
    retry_backoff: linear
```

**exponential:**
- Wait increases exponentially
- Example: 1s, 2s, 4s, 8s, 16s
- Use for: Heavy resource contention
- Default (recommended)

```yaml
enrichment:
  performance:
    retry_backoff: exponential
```

---

### `high_confidence_threshold`

**Type:** Integer  
**Default:** 90  
**Range:** 0 - 100  
**Unit:** Similarity score percentage

**Description:**  
Minimum fuzzy matching score to consider a match as "high confidence" and accept it.

**Effect:**
- Score >= threshold: Match accepted (high confidence)
- Score < threshold: Match rejected or requires additional validation
- Higher threshold: Fewer matches but higher quality
- Lower threshold: More matches but potentially lower quality

**Tuning Guide:**

For high-quality requirements (compliance):
```yaml
enrichment:
  performance:
    high_confidence_threshold: 95  # Only very similar names
```

For balanced (production default):
```yaml
enrichment:
  performance:
    high_confidence_threshold: 90  # Default
```

For speed (exploratory analysis):
```yaml
enrichment:
  performance:
    high_confidence_threshold: 85  # More lenient
```

**Impact on Match Rate:**
- Threshold 95: 60-65% match rate
- Threshold 90: 65-72% match rate
- Threshold 85: 72-78% match rate

---

### `low_confidence_threshold`

**Type:** Integer  
**Default:** 75  
**Range:** 0 - 100  
**Unit:** Similarity score percentage

**Description:**  
Minimum fuzzy matching score to report as a possible match (candidate). Scores below this are not considered matches.

**Effect:**
- Score >= threshold: Reported as potential match
- Score < threshold: Discarded
- Higher threshold: Fewer candidates, faster processing
- Lower threshold: More candidates, slower processing

**Tuning Guide:**

For strict matching:
```yaml
enrichment:
  performance:
    low_confidence_threshold: 80  # Only strong candidates
```

For balanced (production default):
```yaml
enrichment:
  performance:
    low_confidence_threshold: 75  # Default
```

For liberal matching (exploratory):
```yaml
enrichment:
  performance:
    low_confidence_threshold: 70  # More candidates
```

**Relationship to high_confidence_threshold:**
- `low_confidence_threshold` < `high_confidence_threshold` (always)
- Typical: 75 < 90
- Range between them: Scores in [75-90) are "medium confidence"

---

### `enable_fuzzy_matching`

**Type:** Boolean  
**Default:** true  
**Valid Values:** true, false

**Description:**  
Enable or disable fuzzy name matching. When disabled, only exact UEI/DUNS matches are used.

**Effect:**
- `true` (default): Use fuzzy matching when exact identifiers don't match
- `false`: Skip fuzzy matching, only use exact identifier matches

**Use Cases:**

Enable fuzzy matching (default):
```yaml
enrichment:
  performance:
    enable_fuzzy_matching: true
```
- Better match coverage
- Higher match rate (70%+)
- More CPU intensive
- Slower processing

Disable fuzzy matching:
```yaml
enrichment:
  performance:
    enable_fuzzy_matching: false
```
- Only exact matches
- Lower match rate (30-40%)
- Faster processing
- Lower CPU usage
- Use for: Speed-critical scenarios

**Impact:**
- With fuzzy enabled: 70-72% typical match rate, 100-150 rec/sec
- With fuzzy disabled: 35-40% typical match rate, 200-300 rec/sec

---

### `enable_memory_monitoring`

**Type:** Boolean  
**Default:** true  
**Valid Values:** true, false

**Description:**  
Enable or disable memory usage tracking and monitoring.

**Effect:**
- `true` (default): Track peak memory, avg memory delta, spill-to-disk
- `false`: Skip memory tracking (slight performance improvement)

**Use Cases:**

Enable (default):
```yaml
enrichment:
  performance:
    enable_memory_monitoring: true
```
- Full observability
- Slightly slower (< 1% overhead)
- Recommended for all environments

Disable:
```yaml
enrichment:
  performance:
    enable_memory_monitoring: false
```
- Fastest possible execution
- No memory metrics in output
- Use for: Performance testing only

---

### `enable_progress_tracking`

**Type:** Boolean  
**Default:** true  
**Valid Values:** true, false

**Description:**  
Enable or disable per-chunk progress reporting and tracking.

**Effect:**
- `true` (default): Log progress after each chunk, save checkpoints
- `false`: No progress logging

**Use Cases:**

Enable (default):
```yaml
enrichment:
  performance:
    enable_progress_tracking: true
```
- Operator visibility
- Can resume from checkpoints
- Minimal overhead
- Recommended for production

Disable:
```yaml
enrichment:
  performance:
    enable_progress_tracking: false
```
- No progress output
- No checkpoints
- Minimal overhead reduction
- Use for: Batch testing only

---

## Common Configuration Profiles

### Profile: Memory-Constrained (4GB RAM)

```yaml
enrichment:
  performance:
    chunk_size: 5000
    memory_threshold_mb: 1024
    match_rate_threshold: 0.70
    timeout_seconds: 300
    retry_backoff: exponential
    high_confidence_threshold: 90
    low_confidence_threshold: 75
    enable_fuzzy_matching: true
    enable_memory_monitoring: true
    enable_progress_tracking: true
```

**Expected Performance:**
- Throughput: 50-70 records/sec
- Memory peak: 1.0-1.2 GB
- Duration (1K records): 15-20 seconds

---

### Profile: Balanced (8GB RAM) - DEFAULT

```yaml
enrichment:
  performance:
    chunk_size: 25000
    memory_threshold_mb: 2048
    match_rate_threshold: 0.70
    timeout_seconds: 300
    retry_backoff: exponential
    high_confidence_threshold: 90
    low_confidence_threshold: 75
    enable_fuzzy_matching: true
    enable_memory_monitoring: true
    enable_progress_tracking: true
```

**Expected Performance:**
- Throughput: 100-130 records/sec
- Memory peak: 1.5-2.0 GB
- Duration (1K records): 8-10 seconds

---

### Profile: High-Performance (16GB+ RAM)

```yaml
enrichment:
  performance:
    chunk_size: 100000
    memory_threshold_mb: 8192
    match_rate_threshold: 0.70
    timeout_seconds: 300
    retry_backoff: exponential
    high_confidence_threshold: 90
    low_confidence_threshold: 75
    enable_fuzzy_matching: true
    enable_memory_monitoring: true
    enable_progress_tracking: true
```

**Expected Performance:**
- Throughput: 150-200 records/sec
- Memory peak: 3.0-4.0 GB
- Duration (1K records): 5-7 seconds

---

### Profile: Maximum Quality (Compliance)

```yaml
enrichment:
  performance:
    chunk_size: 10000
    memory_threshold_mb: 2048
    match_rate_threshold: 0.85
    timeout_seconds: 600
    retry_backoff: exponential
    high_confidence_threshold: 95
    low_confidence_threshold: 80
    enable_fuzzy_matching: true
    enable_memory_monitoring: true
    enable_progress_tracking: true
```

**Expected Performance:**
- Throughput: 70-90 records/sec
- Memory peak: 1.5-2.0 GB
- Duration (1K records): 11-14 seconds
- Match rate: 65-70% (higher quality matches)

---

### Profile: Maximum Speed (Testing)

```yaml
enrichment:
  performance:
    chunk_size: 50000
    memory_threshold_mb: 4096
    match_rate_threshold: 0.60
    timeout_seconds: 120
    retry_backoff: fixed
    high_confidence_threshold: 85
    low_confidence_threshold: 70
    enable_fuzzy_matching: false  # Fastest
    enable_memory_monitoring: false  # Skip tracking
    enable_progress_tracking: false  # No logging
```

**Expected Performance:**
- Throughput: 250-300 records/sec
- Memory peak: 2.0-2.5 GB
- Duration (1K records): 3-4 seconds
- Match rate: 35-40% (exact matches only)

---

## Configuration Change Workflow

### 1. Test Locally

Before applying configuration changes to production:

```bash
# Copy current baseline
cp reports/benchmarks/baseline.json reports/benchmarks/baseline.backup.json

# Run benchmark with new config
python scripts/benchmark_enrichment.py --sample-size 1000

# Compare results
python scripts/detect_performance_regression.py --output-markdown report.md
```

### 2. Review Impact

Check the regression report:
- Did throughput improve/degrade as expected?
- Is match rate acceptable?
- Is memory usage within limits?

### 3. Deploy Incrementally

Make one change at a time:

```bash
# Change 1: Adjust chunk_size
# Test, measure, verify

# Change 2: Adjust memory_threshold_mb
# Test, measure, verify

# etc.
```

### 4. Establish New Baseline

Once satisfied with new configuration:

```bash
python scripts/benchmark_enrichment.py --save-as-baseline
```

### 5. Monitor Production

Watch for:
- Unexpected regressions (use CI/CD alerts)
- Quality gate failures
- Resource spikes
- Error rates

---

## Troubleshooting Configuration Issues

### Problem: Out of Memory

**Diagnosis:**
- Check error: "MemoryError" or kernel OOM killer
- Review peak memory in metrics

**Solution:**
```yaml
enrichment:
  performance:
    chunk_size: 5000  # Reduce from 25000
    memory_threshold_mb: 1024  # Lower threshold
```

### Problem: Too Slow

**Diagnosis:**
- Throughput < 50 records/sec
- Check if system is CPU-bound

**Solution:**
```yaml
enrichment:
  performance:
    chunk_size: 50000  # Increase
    enable_fuzzy_matching: false  # Skip fuzzy if not needed
```

### Problem: Quality Gate Failures (Low Match Rate)

**Diagnosis:**
- Match rate below threshold consistently
- Check if threshold is too strict

**Solution:**
```yaml
enrichment:
  performance:
    match_rate_threshold: 0.65  # Lower requirement
    low_confidence_threshold: 70  # Accept more candidates
```

### Problem: Intermittent Timeouts

**Diagnosis:**
- Occasional chunks fail with timeout
- Check system load

**Solution:**
```yaml
enrichment:
  performance:
    timeout_seconds: 600  # Increase from 300
    chunk_size: 10000  # Reduce for faster processing
```

---

## Monitoring Configuration

After setting up your configuration, monitor these metrics:

```yaml
enrichment_duration_seconds:  # Should match baseline ±10%
enrichment_peak_memory_mb:    # Should stay < memory_threshold_mb
enrichment_match_rate:        # Should stay >= match_rate_threshold
enrichment_throughput_records_per_sec:  # Should be consistent
```

Set up alerts:
- Duration +25% → WARNING
- Memory > 90% of threshold → WARNING
- Match rate < threshold → FAILURE

---

## Best Practices

1. **Start with default profile** (balanced)
   - Works well for most systems
   - Adjust only if needed

2. **Make one change at a time**
   - Easier to identify impact
   - Simpler rollback if needed

3. **Establish baseline before changing**
   - Provides reference point
   - Easier to measure improvement

4. **Monitor closely after changes**
   - Watch for unexpected side effects
   - Be ready to rollback

5. **Document your configuration**
   - Explain why each parameter was chosen
   - Help future maintainers

6. **Review quarterly**
   - Check if tuning is still optimal
   - Adjust for new data characteristics

---

## Configuration Validation

To verify your configuration:

```bash
# Check configuration loads
python -c "from src.config.loader import get_config; print(get_config().enrichment.performance)"

# Run with validation
python scripts/benchmark_enrichment.py --sample-size 100

# Check for warnings
# Look for: "Memory usage above threshold", "Chunk timeout", "Match rate low"
```

---

## Support & Questions

For configuration questions:
1. Check this guide first
2. Review performance documentation: `docs/performance/enrichment-benchmarks.md`
3. Check configuration examples above
4. Review logs for specific errors
5. Create GitHub issue with benchmark data if needed

When reporting issues, include:
- Current configuration (enrichment.performance section)
- Performance metrics (duration, memory, throughput, match rate)
- System specs (RAM, CPU cores, storage type)
- Sample size and data characteristics