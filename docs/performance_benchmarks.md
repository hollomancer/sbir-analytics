# SBIR ETL Performance Benchmarks

This document contains performance benchmarks and optimization recommendations for the SBIR ETL pipeline.

## Executive Summary

- **Validation Performance**: ~12,000 records/second (44 seconds for full 533K dataset)
- **Import Issues**: CSV import functionality needs debugging - both native and incremental methods fail
- **Memory Usage**: Not measured due to dependency constraints
- **Recommendations**: Fix import issues, optimize batch sizes, add progress indicators

## Test Environment

- **Dataset**: 533,599 SBIR award records (533K+ records)
- **Hardware**: 4 CPU cores, 16GB RAM (estimated)
- **Software**: Python 3.11, DuckDB, pandas

## Performance Results

### CSV Import Performance

**Status: BROKEN** - Both native and incremental import methods fail with DuckDB catalog errors.

**Issues Identified:**
- Native DuckDB import: "Table with name X does not exist" after successful import
- Incremental import: Same catalog error despite table creation logs
- Root cause: Likely DuckDB connection/transaction management issue

**Impact:** Unable to load full dataset for performance testing.

### Validation Performance

Validation was tested with synthetic SBIR data matching the expected schema:

| Sample Size | Duration | Throughput | Notes |
|-------------|----------|------------|-------|
| 100 records | 0.01s | 10,045 rec/sec | Small sample |
| 500 records | 0.04s | 13,353 rec/sec | Medium sample |
| 1,000 records | 0.08s | 11,776 rec/sec | Larger sample |
| 5,000 records | 0.38s | 13,333 rec/sec | Validation scaling |

**Average Throughput**: ~12,127 records/second
**Full Dataset Estimate**: ~44 seconds for 533K records

**Validation Rules Tested:**
- Required field validation (Company, Title, Agency, Phase, Program)
- Data type validation (Award Amount as float, Award Year as int)
- Format validation (UEI, DUNS, email, phone, state codes, ZIP codes)
- Business logic validation (date consistency, award year matching)

### Memory Usage

**Status: Not Measured** - Memory profiling requires `psutil` dependency which is not available in current environment.

**Estimated Memory Requirements:**
- Full dataset load: ~500MB-1GB (based on 533K records × 42 columns)
- Validation: Minimal additional memory (in-place processing)
- Chunked processing: Configurable via batch_size parameter

## Optimizations Implemented

### Progress Indicators

Added progress logging to long-running operations:

1. **Validation Progress**: Logs every 1,000 records processed
   ```python
   if (idx + 1) % 1000 == 0:
       logger.info(f"Validated {idx + 1}/{len(df)} records ({(idx + 1) / len(df) * 100:.1f}%)")
   ```

2. **Chunked Extraction**: Logs each chunk yielded
   ```python
   logger.info(f"Yielding chunk with {len(df_chunk)} rows")
   ```

### Batch Size Optimization

**Current Configuration:**
- Default batch size: 10,000 records
- Configurable via `extraction.sbir.batch_size`

**Recommended Batch Sizes:**
- Memory-constrained: 5,000-10,000 records
- Performance-optimized: 25,000-50,000 records
- Large datasets: 100,000+ records (if memory allows)

## Recommendations

### Immediate Actions

1. **Fix CSV Import Issues**
   - Debug DuckDB catalog errors
   - Test with smaller CSV files first
   - Verify DuckDB connection management

2. **Add Memory Profiling**
   - Install `psutil` dependency
   - Measure actual memory usage patterns
   - Identify memory bottlenecks

3. **Implement Progress Bars**
   - Add `tqdm` dependency for visual progress bars
   - Replace logger-based progress with tqdm progress bars
   - Add estimated time remaining

### Performance Optimizations

1. **Parallel Processing**
   - Implement parallel validation for independent chunks
   - Use multiprocessing for CPU-intensive validation rules
   - Maintain single-threaded I/O operations

2. **Streaming Processing**
   - Implement streaming CSV reading for very large files
   - Process records in true streaming fashion
   - Reduce memory footprint for datasets >1M records

3. **Database Optimizations**
   - Add DuckDB indexes on frequently queried columns
   - Optimize SQL queries for better performance
   - Consider persistent DuckDB files vs in-memory

### Monitoring and Alerting

1. **Performance Monitoring**
   - Add timing decorators to all major functions
   - Log performance metrics to structured logs
   - Track performance regressions over time

2. **Resource Monitoring**
   - Monitor memory usage during processing
   - Track CPU utilization
   - Alert on performance degradation

## Future Benchmarks

Once import issues are resolved, additional benchmarks needed:

1. **Full Dataset Import**
   - Native vs incremental import performance
   - Memory usage during import
   - Import time scaling with dataset size

2. **End-to-End Pipeline**
   - Complete pipeline performance (import → validate → transform)
   - Memory usage throughout pipeline
   - I/O vs CPU bottlenecks

3. **Chunked Processing**
   - Optimal batch sizes for different operations
   - Memory vs performance trade-offs
   - Parallel chunk processing

## Configuration Recommendations

```yaml
# Optimal configuration for 533K dataset
extraction:
  sbir:
    batch_size: 25000  # Balanced memory/performance
    database_path: ":memory:"  # Or persistent file for reuse

validation:
  sample_size_for_checks: 10000  # Reasonable sample size
  max_error_percentage: 0.05  # 5% error tolerance

logging:
  level: INFO
  include_timestamps: true
  include_run_id: true
```

## Conclusion

The validation engine performs well with ~12K records/second throughput. The primary bottleneck is the CSV import functionality which needs debugging. Once resolved, the pipeline should handle the full 533K dataset efficiently with proper chunking and progress indicators.