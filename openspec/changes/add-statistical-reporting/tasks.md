# Implementation Tasks

## 1. Data Models for Reporting
- [ ] 1.1 Add `StatisticalReport` model to `src/models/quality.py`
- [ ] 1.2 Add `ModuleReport` model (base class for module-specific reports)
- [ ] 1.3 Add `InsightRecommendation` model for automated insights
- [ ] 1.4 Add `DataHygieneMetrics` model (clean/dirty splits, quality scores)
- [ ] 1.5 Add `ChangesSummary` model (before/after comparisons)

## 2. Statistical Reporter Utility
- [ ] 2.1 Create `src/utils/statistical_reporter.py`
- [ ] 2.2 Implement `StatisticalReporter` class with report generation methods
- [ ] 2.3 Add HTML report generation (reusing Plotly infrastructure)
- [ ] 2.4 Add JSON report generation (machine-readable)
- [ ] 2.5 Add Markdown summary generation (PR-friendly)
- [ ] 2.6 Add unified report aggregation across modules

## 3. Module-Specific Report Generators
- [ ] 3.1 SBIR Enrichment Reporter:
  - [ ] 3.1.1 Match rate statistics (exact, fuzzy, unmatched)
  - [ ] 3.1.2 Enrichment source breakdown (USAspending, SAM.gov, etc.)
  - [ ] 3.1.3 Coverage metrics by field
  - [ ] 3.1.4 Before/after comparison (fields enriched)
- [ ] 3.2 Patent Analysis Reporter:
  - [ ] 3.2.1 Validation results (pass/fail rates)
  - [ ] 3.2.2 Loading statistics (nodes created, relationships)
  - [ ] 3.2.3 Data quality scores
- [ ] 3.3 Transition Classifier Reporter:
  - [ ] 3.3.1 Classification distribution (transition types)
  - [ ] 3.3.2 Confidence score distribution
  - [ ] 3.3.3 Detection rate statistics
- [ ] 3.4 CET Classifier Reporter:
  - [ ] 3.4.1 Technology category distribution
  - [ ] 3.4.2 Detection rates by category
  - [ ] 3.4.3 Coverage metrics

## 4. Data Hygiene Metrics
- [ ] 4.1 Implement clean vs dirty data split calculation
- [ ] 4.2 Add validation pass rate tracking
- [ ] 4.3 Add data quality score aggregation
- [ ] 4.4 Add field-level quality metrics
- [ ] 4.5 Add threshold compliance checks

## 5. Changes Made Tracking
- [ ] 5.1 Implement before/after dataset comparison
- [ ] 5.2 Track enrichment coverage (% records enriched)
- [ ] 5.3 Track field modification counts
- [ ] 5.4 Generate field-level change summaries
- [ ] 5.5 Add change impact metrics

## 6. Insights Generation
- [ ] 6.1 Implement automated quality recommendations
- [ ] 6.2 Add anomaly detection (quality drops, outliers)
- [ ] 6.3 Add quality trend analysis (improving/degrading)
- [ ] 6.4 Add threshold violation alerts
- [ ] 6.5 Generate actionable next steps

## 7. Integration with Dagster Assets
- [ ] 7.1 Update `sbir_usaspending_enrichment` asset to generate reports
- [ ] 7.2 Update patent loading assets to generate reports
- [ ] 7.3 Update transition classifier assets to generate reports
- [ ] 7.4 Update CET classifier assets to generate reports
- [ ] 7.5 Add report metadata to asset materializations

## 8. CI Workflow Integration
- [ ] 8.1 Update `.github/workflows/ci.yml`:
  - [ ] 8.1.1 Add report generation step after tests
  - [ ] 8.1.2 Upload reports as artifacts
  - [ ] 8.1.3 Generate markdown summary
  - [ ] 8.1.4 Post summary as PR comment (if PR context)
- [ ] 8.2 Update `.github/workflows/container-ci.yml`:
  - [ ] 8.2.1 Generate reports in container test runs
  - [ ] 8.2.2 Upload container test reports as artifacts
- [ ] 8.3 Add report retention policy (30 days)

## 9. Extend Quality Dashboard
- [ ] 9.1 Update `src/utils/quality_dashboard.py`:
  - [ ] 9.1.1 Add module-specific dashboard sections
  - [ ] 9.1.2 Add data hygiene visualizations
  - [ ] 9.1.3 Add changes made visualizations
  - [ ] 9.1.4 Add insights panel
- [ ] 9.2 Add unified dashboard aggregating all modules

## 10. Configuration
- [ ] 10.1 Add report configuration to `config/base.yaml`:
  - [ ] 10.1.1 Report output formats (html, json, markdown)
  - [ ] 10.1.2 Report verbosity levels
  - [ ] 10.1.3 Insight thresholds
- [ ] 10.2 Add report output directory configuration

## 11. Documentation
- [ ] 11.1 Document report structure and contents in README
- [ ] 11.2 Add examples of generated reports
- [ ] 11.3 Document CI artifact locations
- [ ] 11.4 Add report interpretation guide

## 12. Testing
- [ ] 12.1 Unit tests for report generators
- [ ] 12.2 Integration tests for CI report generation
- [ ] 12.3 Test report artifact uploads
- [ ] 12.4 Test PR comment generation
- [ ] 12.5 Validate report formats (HTML, JSON, Markdown)

## 13. Validation
- [ ] 13.1 Run `openspec validate add-statistical-reporting --strict`
- [ ] 13.2 Fix any validation errors
- [ ] 13.3 Confirm all tasks completed
