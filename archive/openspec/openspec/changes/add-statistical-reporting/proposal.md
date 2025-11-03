# Proposal: Add Statistical Reporting for Pipeline Runs

## Why

Currently, enrichment and analysis runs generate metrics internally but lack comprehensive, user-facing statistical reports. This makes it difficult to:

- Assess data quality and hygiene at a glance
- Understand what proportion of data is clean vs dirty
- Track changes made to the base dataset through enrichment/transformation
- Derive actionable insights from pipeline runs
- Compare runs over time in CI/PR contexts

Statistical reporting enables data-driven decisions, quality tracking, and transparent pipeline behavior.

## What Changes

- Create module-specific statistical reports for:
  - SBIR enrichment (match rates, enrichment sources, coverage)
  - Patent analysis (validation results, loading statistics)
  - Transition detection classifier (classification distribution, confidence scores)
  - CET (Critical & Emerging Technologies) classifier (tech category distribution, detection rates)
- Generate unified summary reports aggregating across all modules
- Integrate report generation into CI workflows:
  - Upload reports as GitHub Actions artifacts
  - Post markdown summaries as PR comments
  - Store historical reports for trend analysis
- Implement report formats:
  - HTML dashboards (leverage existing Plotly infrastructure)
  - JSON (machine-readable, for automation)
  - Markdown summaries (PR-friendly)
- Enhance existing `utils/` modules (no new service required)
- Add "data hygiene" metrics: clean vs dirty splits, validation pass rates, data quality scores
- Add "changes made" reports: before/after comparisons, enrichment coverage, field modification tracking
- Add insights generation: automated recommendations, anomaly detection, quality trend alerts

## Impact

### Affected Specs

- `data-validation`: Add statistical reporting requirements for validation results
- `data-enrichment`: Add enrichment coverage and quality reporting
- `pipeline-orchestration`: Add report generation as pipeline artifacts
- `runtime-environment`: Add CI integration for report uploads and PR comments

### Affected Code

- `src/utils/quality_dashboard.py`: Extend with module-specific report generators
- `src/utils/metrics.py`: Add report-specific metrics collection
- `src/models/quality.py`: Add report data models (StatisticalReport, ModuleReport, InsightRecommendation)
- `src/assets/`: Add report generation to enrichment, patent, transition, CET assets
- `.github/workflows/ci.yml`: Add report generation and artifact upload steps
- `.github/workflows/container-ci.yml`: Add report generation in container tests
- New: `src/utils/statistical_reporter.py`: Unified report orchestration

### Benefits

- Transparent pipeline behavior with detailed statistics
- Data quality tracking and trend analysis
- Easier debugging via clean/dirty data breakdowns
- Automated insights reduce manual analysis
- PR-level quality gates via markdown summaries

### Risks

- **Report generation overhead**: Could slow down CI runs
  - Mitigation: Generate reports asynchronously, cache intermediate results
- **Storage of historical reports**: May accumulate large artifacts
  - Mitigation: Implement retention policies (30 days), compress reports
- **Report complexity**: Too much information could overwhelm users
  - Mitigation: Hierarchical reports (summary → details), configurable verbosity

### Dependencies

- Existing: `plotly`, `pandas`, `pydantic`, `loguru`
- GitHub Actions: `actions/upload-artifact@v4`, PR comment actions
