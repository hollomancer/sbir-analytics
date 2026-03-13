# Patent Cost and Spillover Analysis — Tasks

## Phase 1: Marginal Cost Per Patent

- [ ] 1.1 Create `src/tools/mission_b/patent_cost_analysis.py` with `PatentCostCalculator`
- [ ] 1.2 Compute total SBIR award amounts per firm from SBIR.gov data
- [ ] 1.3 Count linked patents per firm from patent-award linkage output
- [ ] 1.4 Compute marginal cost per patent (total awards / patent count) by firm and in aggregate
- [ ] 1.5 Stratify by agency (NIH, DOE, DOD, etc.) and compare to NASEM benchmarks
- [ ] 1.6 Add confidence intervals and sensitivity to entity resolution match rate

## Phase 2: Citation Network Builder

- [ ] 2.1 Create `src/tools/mission_b/citation_network.py` with `CitationNetworkBuilder`
- [ ] 2.2 Load USPTO citation data (citing_patent → cited_patent pairs)
- [ ] 2.3 Filter to citations involving SBIR-linked patents (as cited or citing)
- [ ] 2.4 Build directed citation graph (networkx or lightweight adjacency list)
- [ ] 2.5 Compute basic network metrics (in-degree, out-degree, betweenness for SBIR patents)

## Phase 3: Spillover Multiplier

- [ ] 3.1 Create `SpilloverCalculator` in `src/tools/mission_b/citation_network.py`
- [ ] 3.2 Classify citations: SBIR→SBIR, SBIR→non-SBIR, non-SBIR→SBIR
- [ ] 3.3 Compute spillover multiplier (non-SBIR citations to SBIR patents / SBIR patent count)
- [ ] 3.4 Replicate DOE 3x multiplier methodology and reconcile
- [ ] 3.5 Extend spillover computation across all agencies

## Phase 4: NASEM Benchmark Reconciliation

- [ ] 4.1 Create reconciliation report: NIH $1.5M marginal cost comparison
- [ ] 4.2 Create reconciliation report: DOE 3x spillover comparison
- [ ] 4.3 Document methodology differences and reconciliation narrative

## Phase 5: Testing and Integration

- [ ] 5.1 Create unit tests with synthetic patent-award linkage data
- [ ] 5.2 Create unit tests for citation network construction
- [ ] 5.3 Create integration test with sample USPTO data subset
- [ ] 5.4 Create Dagster asset wrappers
