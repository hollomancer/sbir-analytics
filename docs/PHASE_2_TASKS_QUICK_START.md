# Phase 2 Tasks - Quick Start Guide

Complete reference for using the three newly completed tasks: Test Fixtures (1.4), Performance Reporting (2.5), and Regression Detection (4.2).

---

## Task 1.4: Test Fixtures

### Location
`tests/fixtures/enrichment_scenarios.json`

### Loading Fixtures in Tests

```python
import json
from pathlib import Path

# Load all scenarios
with open("tests/fixtures/enrichment_scenarios.json") as f:
    scenarios = json.load(f)

# Access by category
good_scenarios = scenarios["good_scenarios"]["scenarios"]      # 5 scenarios
bad_scenarios = scenarios["bad_scenarios"]["scenarios"]        # 6 scenarios
edge_cases = scenarios["edge_cases"]["scenarios"]              # 4 scenarios
```

### Using in Unit Tests

```python
import pytest
from tests.fixtures.enrichment_scenarios import load_enrichment_scenarios

@pytest.fixture
def enrichment_scenarios():
    """Provide enrichment test scenarios."""
    scenarios = load_enrichment_scenarios()
    return scenarios

def test_good_scenario_passes_quality_gate(enrichment_scenarios):
    """Verify good scenarios pass quality gates."""
    for scenario in enrichment_scenarios["good_scenarios"]["scenarios"]:
        sbir = scenario["sbir_company"]
        usaspending = scenario["usaspending_recipient"]
        
        # Run enrichment
        result = enrich_single_company(sbir, usaspending)
        
        # Verify high confidence match
        assert result["confidence"] >= scenario["expected_confidence"]

def test_bad_scenario_fails_quality_gate(enrichment_scenarios):
    """Verify bad scenarios fail quality gates."""
    for scenario in enrichment_scenarios["bad_scenarios"]["scenarios"]:
        sbir = scenario["sbir_company"]
        usaspending = scenario["usaspending_recipient"]
        
        # Run enrichment
        result = enrich_single_company(sbir, usaspending)
        
        # Should not match or low confidence
        assert result["match_method"] is None or result["confidence"] < 75
```

### Scenario Structure

Each scenario has:
- `id`: Unique identifier
- `name`: Human-readable name
- `sbir_company`: Test SBIR company data
- `usaspending_recipient`: Test USAspending recipient data (or null)
- `expected_match_method`: Expected match type (exact_uei, exact_duns, fuzzy_name, or null)
- `expected_confidence`: Expected confidence score
- `description`: What the scenario tests

---

## Task 2.5: Performance Reporting

### Location
`src/utils/performance_reporting.py`

### Basic Usage

```python
from src.utils.performance_reporting import (
    PerformanceReporter,
    PerformanceMetrics,
)
from pathlib import Path

# Create reporter with default thresholds
reporter = PerformanceReporter()

# Load metrics from benchmark JSON
with open("reports/benchmarks/benchmark_20240115_120000.json") as f:
    benchmark_data = json.load(f)

metrics = PerformanceMetrics.from_benchmark(benchmark_data)

# Generate Markdown report
markdown_report = reporter.format_metrics_markdown(metrics)
print(markdown_report)
```

### Comparing Against Baseline

```python
import json
from src.utils.performance_reporting import PerformanceReporter, PerformanceMetrics

reporter = PerformanceReporter(
    time_failure_threshold=25.0,        # 25% slower = failure
    time_warning_threshold=10.0,        # 10% slower = warning
    memory_failure_threshold=50.0,      # 50% more memory = failure
    memory_warning_threshold=20.0,      # 20% more memory = warning
    match_rate_failure_threshold=-5.0   # 5% worse match rate = failure
)

# Load baseline and current
with open("reports/benchmarks/baseline.json") as f:
    baseline_data = json.load(f)
with open("reports/benchmarks/benchmark_latest.json") as f:
    current_data = json.load(f)

baseline = PerformanceMetrics.from_benchmark(baseline_data)
current = PerformanceMetrics.from_benchmark(current_data)

# Compare
comparison = reporter.compare_metrics(baseline, current)
print(f"Status: {comparison.regression_severity}")
print(f"Time delta: {comparison.time_delta_percent:+.1f}%")
print(f"Memory delta: {comparison.memory_delta_percent:+.1f}%")

for issue in comparison.regression_messages:
    print(f"- {issue}")
```

### Generating Reports

```python
from pathlib import Path
from src.utils.performance_reporting import PerformanceReporter
import json

reporter = PerformanceReporter()

with open("reports/benchmarks/benchmark_latest.json") as f:
    benchmark_data = json.load(f)

# Save Markdown report
md_path = reporter.save_markdown_report(
    benchmark_data,
    Path("reports/enrichment_benchmark.md")
)

# Save HTML report
html_path = reporter.save_html_report(
    benchmark_data,
    Path("reports/enrichment_benchmark.html"),
    title="Enrichment Pipeline Benchmark"
)

print(f"Markdown: {md_path}")
print(f"HTML: {html_path}")
```

### Loading Metrics from Dagster Assets

```python
from src.utils.performance_reporting import PerformanceMetrics

# From asset metadata
asset_metadata = {
    "performance_total_duration_seconds": 15.5,
    "performance_records_per_second": 645.0,
    "performance_peak_memory_mb": 512.0,
    "performance_avg_memory_delta_mb": 200.0,
    "enrichment_match_rate": 0.72,
    "enrichment_matched_records": 360,
    "enrichment_total_records": 500,
}

metrics = PerformanceMetrics.from_asset_metadata(asset_metadata)
print(f"Duration: {metrics.total_duration_seconds}s")
print(f"Match Rate: {metrics.match_rate:.1%}")
```

### Historical Trend Analysis

```python
from pathlib import Path
from src.utils.performance_reporting import (
    load_historical_metrics,
    analyze_performance_trend,
)

# Load all benchmarks from directory
benchmarks_dir = Path("reports/benchmarks")
metrics_list = load_historical_metrics(benchmarks_dir)

print(f"Loaded {len(metrics_list)} historical benchmarks")

# Analyze trends
trend = analyze_performance_trend(metrics_list)
print(f"Duration trend: {trend['duration']['trend']}")
print(f"  Min: {trend['duration']['min']:.2f}s")
print(f"  Max: {trend['duration']['max']:.2f}s")
print(f"  Avg: {trend['duration']['avg']:.2f}s")

print(f"Memory trend: {trend['memory']['trend']}")
print(f"  Min: {trend['memory']['min']:.0f}MB")
print(f"  Max: {trend['memory']['max']:.0f}MB")
print(f"  Avg: {trend['memory']['avg']:.0f}MB")
```

---

## Task 4.2: Regression Detection

### Location
`scripts/detect_performance_regression.py`

### Basic Usage

```bash
# Run regression detection and fail if regression detected
python scripts/detect_performance_regression.py --fail-on-regression

# Generate all report formats
python scripts/detect_performance_regression.py \
  --output-json reports/regression.json \
  --output-markdown reports/regression.md \
  --output-html reports/regression.html

# Use custom thresholds
python scripts/detect_performance_regression.py \
  --time-failure-threshold 20 \
  --memory-failure-threshold 40 \
  --fail-on-regression
```

### Command Line Options

```
--sample-size N           Number of SBIR records to benchmark (default: all)
--baseline PATH          Path to baseline benchmark (default: reports/benchmarks/baseline.json)
--output-json PATH       Save JSON summary
--output-markdown PATH   Save Markdown report
--output-html PATH       Save HTML report
--output-github-comment PATH  Save GitHub PR comment format
--time-warning-threshold PCT   Time increase % for warning (default: 10)
--time-failure-threshold PCT   Time increase % for failure (default: 25)
--memory-warning-threshold PCT Memory increase % for warning (default: 20)
--memory-failure-threshold PCT Memory increase % for failure (default: 50)
--fail-on-regression     Exit with code 1 on regression
```

### Python Integration

```python
from scripts.detect_performance_regression import (
    run_enrichment_benchmark,
    load_baseline,
    generate_regression_summary,
)
from src.utils.performance_reporting import PerformanceReporter
from pathlib import Path
import pandas as pd

# Load data
sbir_df = pd.read_csv("data/raw/sbir_dump.csv").head(1000)
usaspending_df = pd.read_parquet("data/processed/usaspending_recipients.parquet")

# Run benchmark
benchmark = run_enrichment_benchmark(sbir_df, usaspending_df)

# Load baseline
baseline = load_baseline(Path("reports/benchmarks/baseline.json"))

# Generate summary
reporter = PerformanceReporter()
summary = generate_regression_summary(benchmark, baseline, reporter)

# Check results
if summary["regression_detected"]:
    print(f"Regression detected: {summary['severity']}")
    for issue in summary["issues"]:
        print(f"  - {issue}")
```

### GitHub Actions Integration

```yaml
name: Performance Regression Check

on:
  pull_request:
    paths:
      - 'src/enrichers/**'
      - 'src/assets/**'
      - 'src/utils/performance_monitor.py'

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -e .
      
      - name: Run Performance Regression Detection
        id: regression
        run: |
          python scripts/detect_performance_regression.py \
            --sample-size 500 \
            --output-json /tmp/regression.json \
            --output-github-comment /tmp/comment.md \
            --fail-on-regression || true
      
      - name: Comment on PR with Results
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            if (fs.existsSync('/tmp/comment.md')) {
              const comment = fs.readFileSync('/tmp/comment.md', 'utf8');
              github.rest.issues.createComment({
                issue_number: context.issue.number,
                owner: context.repo.owner,
                repo: context.repo.repo,
                body: comment
              });
            }
      
      - name: Fail if regression detected
        run: |
          if grep -q '"regression_detected": true' /tmp/regression.json; then
            if grep -q '"severity": "FAILURE"' /tmp/regression.json; then
              echo "❌ Performance regression detected!"
              cat /tmp/comment.md
              exit 1
            fi
          fi
```

### Interpreting Results

**JSON Output Format:**
```json
{
  "timestamp": "2024-01-15T12:00:00.000000",
  "current_metrics": {
    "duration_seconds": 15.5,
    "throughput_records_per_sec": 645.0,
    "peak_memory_mb": 512.0,
    "match_rate": 0.72
  },
  "regression_detected": false,
  "severity": "PASS",
  "issues": [],
  "baseline_comparison": {
    "baseline_duration_seconds": 14.2,
    "time_delta_percent": 9.2,
    "memory_delta_percent": -5.0
  }
}
```

**Severity Levels:**
- `PASS` - No regressions detected
- `WARNING` - Time +10-25% or Memory +20-50%
- `FAILURE` - Time >25% or Memory >50% or Match Rate -5%

---

## Integration Example: Full Pipeline

```python
"""
Example: Run full enrichment with reporting and regression detection
"""
import json
from pathlib import Path
from src.utils.performance_reporting import PerformanceReporter
from scripts.benchmark_enrichment import (
    load_sample_data,
    load_usaspending_lookup,
    run_enrichment_benchmark,
    load_baseline,
    save_benchmark,
)

# 1. Load data
sbir_df, total = load_sample_data(sample_size=1000)
usaspending_df = load_usaspending_lookup()

# 2. Run benchmark
benchmark = run_enrichment_benchmark(sbir_df, usaspending_df)

# 3. Load baseline if exists
baseline = load_baseline()

# 4. Create reporter
reporter = PerformanceReporter(
    time_failure_threshold=25.0,
    memory_failure_threshold=50.0
)

# 5. Compare metrics
if baseline:
    from src.utils.performance_reporting import PerformanceMetrics
    
    baseline_metrics = PerformanceMetrics.from_benchmark(baseline)
    current_metrics = PerformanceMetrics.from_benchmark(benchmark)
    
    comparison = reporter.compare_metrics(baseline_metrics, current_metrics)
    
    # Generate comparison report
    report = reporter.format_comparison_markdown(comparison)
    print(report)

# 6. Save outputs
benchmark_path = save_benchmark(benchmark)
reporter.save_markdown_report(benchmark, Path("reports/latest_report.md"))
reporter.save_html_report(benchmark, Path("reports/latest_report.html"))

print(f"✅ Benchmark saved to {benchmark_path}")
```

---

## Common Tasks

### Create a new baseline
```bash
python scripts/benchmark_enrichment.py --save-as-baseline
```

### Run regression check in CI
```bash
python scripts/detect_performance_regression.py \
  --fail-on-regression \
  --output-markdown /tmp/regression.md
```

### Generate pretty HTML report
```bash
python scripts/benchmark_enrichment.py --output reports/latest.json

# Then in Python
from src.utils.performance_reporting import PerformanceReporter
import json

with open("reports/latest.json") as f:
    data = json.load(f)

reporter = PerformanceReporter()
reporter.save_html_report(data, Path("reports/report.html"))
```

### Analyze performance trends over time
```python
from pathlib import Path
from src.utils.performance_reporting import (
    load_historical_metrics,
    analyze_performance_trend,
)

metrics = load_historical_metrics(Path("reports/benchmarks"))
trend = analyze_performance_trend(metrics)

print(f"Performance trend: {trend['duration']['trend']}")
print(f"Duration range: {trend['duration']['min']:.2f}s - {trend['duration']['max']:.2f}s")
```

---

## Troubleshooting

### "No baseline found" warning
This is normal on first run. Create a baseline:
```bash
python scripts/benchmark_enrichment.py --save-as-baseline
```

### Regression detection too strict/lenient
Adjust thresholds:
```bash
python scripts/detect_performance_regression.py \
  --time-failure-threshold 30 \
  --memory-failure-threshold 60
```

### Memory spike in reports
Check `peak_memory_mb` - may indicate data loading overhead. Sample with smaller `--sample-size`:
```bash
python scripts/detect_performance_regression.py --sample-size 100
```

### Missing USAspending data
Regression detection still works but with empty lookup. To fix:
1. Ensure `data/processed/usaspending_recipients.parquet` exists, or
2. Ensure `data/raw/usaspending/recipients.csv` exists

---

## Performance Targets

Expected baseline metrics (for reference):
- Duration: 10-20s (for 500-1000 records)
- Throughput: 50-100 records/sec
- Peak Memory: 300-600 MB
- Match Rate: >70%

Adjust thresholds based on your hardware and data characteristics.

---

## Next Steps

1. **Integrate fixtures into existing smoke tests**
   - Update `tests/e2e/test_dagster_enrichment_pipeline.py`
   
2. **Set up CI/CD workflow** (Task 4.5)
   - Create GitHub Actions with regression detection
   
3. **Create performance documentation** (Task 4.4)
   - Document baseline expectations
   - Create runbooks for operators

4. **Implement chunked processing** (Task 3.2)
   - Support full 3.3M+ record dataset
   - Use regression detection to validate