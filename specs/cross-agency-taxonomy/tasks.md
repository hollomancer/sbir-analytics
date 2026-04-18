# Cross-Agency Technology Taxonomy — Tasks

## Phase 1: Full Corpus Classification

- [ ] 1.1 Verify SBIR.gov award corpus completeness and freshness (count by agency, date range)
- [ ] 1.2 Create batch classification runner using CET keyword classifier on full corpus
- [ ] 1.3 Store classification results as Parquet with award_id, agency, cet_area, confidence columns
- [ ] 1.4 Compute classification coverage metrics (% of awards classified, multi-label distribution)

## Phase 2: Agency-Level Analysis

- [ ] 2.1 Create `src/tools/mission_a/cross_agency_taxonomy.py` with `AgencyTaxonomyAnalyzer`
- [ ] 2.2 Compute per-agency technology allocation (% of awards per CET area)
- [ ] 2.3 Compute cross-agency overlap matrix (Jaccard similarity of technology portfolios)
- [ ] 2.4 Identify concentration risk (HHI or single-agency dominance per technology area)
- [ ] 2.5 Compute temporal trends (technology mix by agency by fiscal year)

## Phase 3: Output and Visualization

- [ ] 3.1 Generate cross-agency allocation table (agencies x CET areas, with cell values)
- [ ] 3.2 Generate heatmap data (JSON/CSV format suitable for visualization)
- [ ] 3.3 Generate markdown summary report with key findings
- [ ] 3.4 Add reporting script (`scripts/report_taxonomy.py`)

## Phase 4: Testing

- [ ] 4.1 Create unit tests with synthetic multi-agency award data
- [ ] 4.2 Create integration test with sample SBIR.gov corpus subset
- [ ] 4.3 Create Dagster asset wrapper for scheduled taxonomy refresh
