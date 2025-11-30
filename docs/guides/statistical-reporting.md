# Statistical Reporting Guide

## Overview

The Statistical Reporting System provides comprehensive, multi-format reports for SBIR ETL pipeline runs, enabling data-driven decisions, quality tracking, and transparent pipeline behavior.

### Current Implementation Status

- ✅ **Core Infrastructure**: Complete with `StatisticalReporter` class, data models, and configuration
- ✅ **Multi-format Output**: HTML (with Plotly), JSON, Markdown, and Executive dashboard generation
- ✅ **CI/CD Integration**: GitHub Actions artifact upload and PR comment generation
- 🚧 **Module Analyzers**: In development for SBIR enrichment, patent analysis, CET classification, transition detection
- 🚧 **Automated Insights**: Quality recommendations, anomaly detection, and success story identification

See `.kiro/specs/statistical_reporting/tasks.md` for detailed implementation progress.

## Key Concepts

### Report Types

**Statistical Report**: Comprehensive report aggregating all pipeline modules with data hygiene metrics, performance insights, and automated recommendations.

**Module Report**: Focused report for individual pipeline components (SBIR enrichment, patent analysis, CET classification, transition detection).

**Data Hygiene Metrics**: Measurements of data quality including clean/dirty data ratios, validation pass rates, and field-level completeness.

### Report Formats

- **HTML**: Interactive web-viewable reports with Plotly visualizations and drill-down capabilities
- **JSON**: Machine-readable reports for programmatic consumption and API integration
- **Markdown**: Concise summaries suitable for PR comments and documentation
- **Executive**: High-level dashboards with impact metrics and success stories for program managers

## Usage

### Basic Report Generation

```python
from datetime import datetime, timedelta
from src.utils.statistical_reporter import StatisticalReporter
from src.models.quality import DataHygieneMetrics, ChangesSummary

## Initialize reporter

reporter = StatisticalReporter()

## Generate module report

module_report = reporter.generate_module_report(
    module_name="sbir_enrichment",
    run_id="run_20251030_143022",
    stage="enrich",
    metrics_data={
        "records_in": 50000,
        "records_processed": 47500,
        "records_failed": 2500,
        "start_time": datetime.now() - timedelta(seconds=120),
        "end_time": datetime.now(),
        "quality_metrics": {"validation_pass_rate": 0.95}
    }
)

## Generate comprehensive reports for pipeline run

run_context = {
    "run_id": "run_20251030_143022",
    "pipeline_name": "sbir-analytics",
    "environment": "development",
    "modules": {
        "sbir_enrichment": {
            "stage": "enrich",
            "records_in": 50000,
            "records_processed": 47500,
            "records_failed": 2500
        }
    }
}

## Generate all report formats

report_collection = reporter.generate_reports(run_context)
print(f"Generated {len(report_collection.artifacts)} report artifacts")
for artifact in report_collection.artifacts:
    print(f"{artifact.format.value}: {artifact.file_path}")
```

### Module-Specific Reporting

#### SBIR Enrichment Reports

```python

## SBIR enrichment metrics

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

###Patent Analysis Reports

```python

## Patent analysis metrics

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

### Executive Reporting

#### Generating Executive Dashboards

```python
from src.utils.statistical_reporter import StatisticalReporter

## Initialize reporter with executive reporting enabled

reporter = StatisticalReporter()

## Generate executive summary with success stories

executive_report = reporter.generate_executive_summary(
    run_id="run_20251030_143022",
    pipeline_metrics=pipeline_metrics,
    include_success_stories=True,
    include_roi_analysis=True
)

## Generate executive dashboard

dashboard = reporter.generate_executive_dashboard(
    executive_report,
    focus_areas=["impact", "quality", "trends"]
)
```

###Success Story Identification

```python

## Identify high-impact transitions for success stories

success_stories = reporter.identify_success_stories(
    transition_results=transition_data,
    min_impact_threshold=0.8,
    include_patent_portfolios=True,
    include_multi_phase_funding=True
)

## Generate success story narratives

for story in success_stories:
    print(f"Company: {story.company_name}")
    print(f"Technology: {story.technology_area}")
    print(f"Impact Score: {story.impact_score}")
    print(f"Commercialization Path: {story.pathway_description}")
```

###Program Effectiveness Metrics

```python

## Calculate program effectiveness metrics

effectiveness_metrics = reporter.calculate_program_effectiveness(
    awards_data=awards_data,
    contracts_data=contracts_data,
    patents_data=patents_data
)

print(f"Funding ROI: {effectiveness_metrics.funding_roi}")
print(f"Commercialization Rate: {effectiveness_metrics.commercialization_rate}")
print(f"Technology Transfer Success: {effectiveness_metrics.tech_transfer_rate}")
```

## Configuration

### Basic Configuration

```yaml

## config/base.yaml

statistical_reporting:
  # Output configuration
  output_directory: "reports/statistical"
  output_formats: ["html", "json", "markdown", "executive"]

  # Report settings
  retention_days: 30
  verbosity_level: "detailed"  # minimal, standard, detailed

  # Insight generation
  insights:
    enabled: true
    quality_threshold: 0.95
    performance_threshold: 0.80
    anomaly_detection: true
    success_stories:
      enabled: true
      min_impact_threshold: 0.8

  # Executive reporting
  executive:
    include_success_stories: true
    include_roi_analysis: true
    include_comparative_benchmarks: true
    focus_areas: ["impact", "quality", "trends"]

  # Visualization settings
  html:
    enable_plotly: true
    theme: "plotly_white"
    include_raw_data: false
```

### Environment Overrides

```bash

## Override output directory

export SBIR_ETL__STATISTICAL_REPORTING__OUTPUT_DIRECTORY="custom/reports"

## Disable insights

export SBIR_ETL__STATISTICAL_REPORTING__INSIGHTS__ENABLED=false

## Change quality threshold

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

### Executive Dashboards

High-level stakeholder reports include:

- **Impact Metrics**: Total funding analyzed, companies tracked, patents linked
- **Success Stories**: High-impact technology transitions and commercialization examples
- **Program Effectiveness**: Funding ROI, commercialization rates, sector performance
- **Comparative Analysis**: Performance against program goals and benchmarks
- **Visualizations**: Executive-friendly charts suitable for presentations

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

## .github/workflows/ci.yml

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

## Quality threshold violation

InsightRecommendation(
    type="quality_threshold_violation",
    severity="ERROR",
    title="SBIR Enrichment Success Rate Below Threshold",
    description="Enrichment success rate (92%) below configured threshold (95%)",
    recommendation="Check API rate limits and network connectivity",
    affected_records=4000
)

## Performance anomaly

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

### Missing Plotly Visualizations

- Install plotly: `pip install plotly`
- Or disable: `SBIR_ETL__STATISTICAL_REPORTING__HTML__ENABLE_PLOTLY=false`

### Large Report Files

- Reduce verbosity: `verbosity_level: "minimal"`
- Disable raw data: `include_raw_data: false`
- Increase retention: `retention_days: 7`

### Slow Report Generation

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
- **Quality Assurance Guide**: [`quality-assurance.md`](quality-assurance.md)
- **Performance Monitoring**: [`../performance/index.md`
