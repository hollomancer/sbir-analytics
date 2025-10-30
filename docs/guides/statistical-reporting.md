# Statistical Reporting Guide

## Overview

The Statistical Reporting System provides comprehensive, multi-format reports for SBIR ETL pipeline runs, enabling data-driven decisions, quality tracking, and transparent pipeline behavior.

## Key Concepts

### Report Types

**Statistical Report**: Comprehensive report aggregating all pipeline modules with data hygiene metrics, performance insights, and automated recommendations.

**Module Report**: Focused report for individual pipeline components (SBIR enrichment, patent analysis, CET classification, transition detection).

**Data Hygiene Metrics**: Measurements of data quality including clean/dirty data ratios, validation pass rates, and field-level completeness.

### Report Formats

- **HTML**: Interactive web-viewable reports with Plotly visualizations and drill-down capabilities
- **JSON**: Machine-readable reports for programmatic consumption and API integration
- **Markdown**: Concise summaries suitable for PR comments and documentation

## Usage

### Basic Report Generation

```python
from src.utils.statistical_reporter import StatisticalReporter
from src.models.quality import DataHygieneMetrics, ChangesSummary

# Initialize reporter
reporter = StatisticalReporter()

# Generate module report
module_report = reporter.generate_module_report(
    module_name="sbir_enrichment",
    run_id="run_20251030_143022",
    records_processed=50000,
    execution_time=120.5,
    data_hygiene=DataHygieneMetrics(
        total_records=50000,
        clean_records=47500,
        dirty_records=2500,
        validation_pass_rate=0.95
    )
)

# Generate unified report
unified_report = reporter.generate_unified_report(
    run_id="run_20251030_143022",
    module_reports=[module_report]
)

# Generate all formats
output_files = reporter.generate_all_formats(unified_report)
print(f"HTML: {output_files['html']}")
print(f"JSON: {output_files['json']}")
print(f"Markdown: {output_files['markdown']}")
```

### Module-Specific Reporting

#### SBIR Enrichment Reports

```python
# SBIR enrichment metrics
sbir_report = reporter.generate_module_report(
    module_name="sbir_enrichment",
    run_id=run_id,
    records_processed=len(enriched_awards),
    execution_time=enrichment_duration,
    data_hygiene=DataHygieneMetrics(
        total_records=len(enriched_awards),
        clean_records=len(enriched_awards[enriched_awards['enrichment_success'] == True]),
        dirty_records=len(enriched_awards[enriched_awards['enrichment_success'] == False]),
        validation_pass_rate=enrichment_success_rate
    ),
    changes_summary=ChangesSummary(
        records_modified=len(enriched_awards[enriched_awards['fields_enriched'] > 0]),
        fields_modified=total_fields_enriched,
        enrichment_coverage=enrichment_coverage_rate
    )
)
```

#### Patent Analysis Reports

```python
# Patent analysis metrics
patent_report = reporter.generate_module_report(
    module_name="patent_analysis",
    run_id=run_id,
    records_processed=len(validated_patents),
    execution_time=validation_duration,
    data_hygiene=DataHygieneMetrics(
        total_records=len(validated_patents),
        clean_records=len(validated_patents[validated_patents['validation_passed'] == True]),
        dirty_records=len(validated_patents[validated_patents['validation_passed'] == False]),
        validation_pass_rate=validation_pass_rate
    )
)
```

## Configuration

### Basic Configuration

```yaml
# config/base.yaml
statistical_reporting:
  # Output configuration
  output_directory: "reports/statistical"
  output_formats: ["html", "json", "markdown"]
  
  # Report settings
  retention_days: 30
  verbosity_level: "detailed"  # minimal, standard, detailed
  
  # Insight generation
  insights:
    enabled: true
    quality_threshold: 0.95
    performance_threshold: 0.80
    anomaly_detection: true
    
  # Visualization settings
  html:
    enable_plotly: true
    theme: "plotly_white"
    include_raw_data: false
```

### Environment Overrides

```bash
# Override output directory
export SBIR_ETL__STATISTICAL_REPORTING__OUTPUT_DIRECTORY="custom/reports"

# Disable insights
export SBIR_ETL__STATISTICAL_REPORTING__INSIGHTS__ENABLED=false

# Change quality threshold
export SBIR_ETL__STATISTICAL_REPORTING__INSIGHTS__QUALITY_THRESHOLD=0.90
```

## Report Structure

### HTML Reports

Interactive reports include:
- **Executive Summary**: Key metrics and insights at a glance
- **Data Quality Dashboard**: Clean/dirty ratios, validation results
- **Module Performance**: Individual pipeline stage analysis
- **Trend Analysis**: Historical comparison and regression detection
- **Interactive Charts**: Plotly visualizations with drill-down capabilities

### JSON Reports

Machine-readable structure:
```json
{
  "report_id": "run_20251030_143022_20251030_143500",
  "run_id": "run_20251030_143022",
  "generated_at": "2025-10-30T14:35:00Z",
  "pipeline_duration": 300.5,
  "total_records_processed": 150000,
  "data_hygiene": {
    "total_records": 150000,
    "clean_records": 142500,
    "dirty_records": 7500,
    "validation_pass_rate": 0.95
  },
  "module_reports": [...],
  "insights": [...],
  "metadata": {...}
}
```

### Markdown Summaries

PR-friendly format:
```markdown
## Pipeline Statistical Report

**Run ID**: run_20251030_143022  
**Duration**: 5m 0.5s  
**Records Processed**: 150,000

### Data Quality
- **Clean Records**: 142,500 (95.0%)
- **Validation Pass Rate**: 95.0% ✅

### Module Performance
- **SBIR Enrichment**: 50,000 records, 95% success rate
- **Patent Analysis**: 25,000 records, 98% validation pass rate
- **CET Classification**: 50,000 records, 92% coverage

### Insights
- ✅ All quality thresholds met
- ⚠️ SBIR enrichment rate below target (95% vs 97% target)
```

## CI/CD Integration

### GitHub Actions

Reports are automatically generated in CI workflows:

```yaml
# .github/workflows/ci.yml
- name: Generate Statistical Reports
  run: |
    python -c "
    from src.utils.statistical_reporter import StatisticalReporter
    reporter = StatisticalReporter()
    # Generate reports for CI run
    "

- name: Upload Report Artifacts
  uses: actions/upload-artifact@v3
  with:
    name: statistical-reports-${{ github.run_id }}
    path: reports/statistical/
    retention-days: 30
```

### PR Comments

Markdown summaries are automatically posted as PR comments when running in PR context, providing immediate feedback on pipeline quality and performance changes.

## Automated Insights

### Quality Recommendations

The system automatically generates recommendations based on metrics:

- **Threshold Violations**: Alerts when quality metrics fall below configured thresholds
- **Performance Anomalies**: Detects significant deviations from historical baselines
- **Actionable Steps**: Provides specific recommendations for addressing identified issues

### Example Insights

```python
# Quality threshold violation
InsightRecommendation(
    type="quality_threshold_violation",
    severity="ERROR",
    title="SBIR Enrichment Success Rate Below Threshold",
    description="Enrichment success rate (92%) below configured threshold (95%)",
    recommendation="Check API rate limits and network connectivity",
    affected_records=4000
)

# Performance anomaly
InsightRecommendation(
    type="performance_anomaly",
    severity="WARNING", 
    title="Patent Validation Duration Increased",
    description="Validation duration (180s) significantly higher than baseline (120s)",
    recommendation="Review data volume changes or resource constraints",
    affected_records=25000
)
```

## Best Practices

### Report Generation

1. **Generate reports after each pipeline stage** for granular analysis
2. **Include comprehensive metadata** for debugging and analysis
3. **Use consistent run IDs** across all modules for correlation
4. **Configure appropriate retention policies** to manage storage

### Quality Monitoring

1. **Set realistic thresholds** based on historical performance
2. **Monitor trends over time** rather than individual run metrics
3. **Investigate anomalies promptly** to prevent quality degradation
4. **Document threshold changes** and their rationale

### CI/CD Integration

1. **Upload reports as artifacts** for historical analysis
2. **Post summaries in PR comments** for immediate feedback
3. **Compare against baselines** to detect regressions
4. **Fail builds on critical quality violations** to maintain standards

## Troubleshooting

### Common Issues

**Missing Plotly Visualizations**:
- Install plotly: `pip install plotly`
- Or disable: `SBIR_ETL__STATISTICAL_REPORTING__HTML__ENABLE_PLOTLY=false`

**Large Report Files**:
- Reduce verbosity: `verbosity_level: "minimal"`
- Disable raw data: `include_raw_data: false`
- Increase retention: `retention_days: 7`

**Slow Report Generation**:
- Disable complex visualizations for large datasets
- Use sampling for visualization data
- Generate reports asynchronously

### Performance Optimization

For large datasets (>100K records):
- Use sampling for visualization data
- Generate reports in background processes
- Consider report caching for repeated access
- Optimize data aggregation queries

## Related Documentation

- **Specification**: `.kiro/specs/statistical_reporting/`
- **Implementation**: `src/utils/statistical_reporter.py`
- **Models**: `src/models/quality.py`
- **Configuration**: `config/base.yaml` (statistical_reporting section)
- **CI Integration**: `.github/workflows/ci.yml`