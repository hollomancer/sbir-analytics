# Patent Cost and Spillover Analysis — Tasks

> **Status (2026-07-02):** Not started. USPTO extraction and patent-award linkage exist (`packages/sbir-analytics/sbir_analytics/assets/uspto/`), but the cost and citation-network analytical layer is not implemented.

## Phase 1: Marginal Cost Per Patent

- [ ] 1.1 Create `packages/sbir-analytics/sbir_analytics/tools/mission_b/patent_cost_analysis.py` with `PatentCostCalculator`
- [ ] 1.2 Compute total SBIR award amounts per firm from SBIR.gov data
- [ ] 1.3 Count linked patents per firm from patent-award linkage output
- [ ] 1.4 Compute marginal cost per patent (total awards / patent count) by firm and in aggregate
- [ ] 1.5 Stratify by agency (NIH, DOE, DOD, etc.) and compare marginal cost only to the NIH benchmark
- [ ] 1.6 Add confidence intervals and sensitivity to entity resolution match rate

## Phase 2: Citation Network Builder

- [ ] 2.1 Create `packages/sbir-analytics/sbir_analytics/tools/mission_b/citation_network.py` with `CitationNetworkBuilder`
- [ ] 2.2 Load USPTO citation data (citing_patent → cited_patent pairs)
- [ ] 2.3 Filter to citations involving SBIR-linked patents (as cited or citing)
- [ ] 2.4 Build directed citation graph (networkx or lightweight adjacency list)
- [ ] 2.5 Compute basic network metrics (in-degree, out-degree, betweenness for SBIR patents)

## Phase 3: Citation-Network Diffusion

- [ ] 3.1 Create `CitationDiffusionCalculator` in `packages/sbir-analytics/sbir_analytics/tools/mission_b/citation_network.py`
- [ ] 3.2 Classify citations: SBIR→SBIR, SBIR→non-SBIR, non-SBIR→SBIR
- [ ] 3.3 Compute inbound non-SBIR citations per SBIR-linked patent
- [ ] 3.4 Record the citation-window cutoff and lag limitations in every output
- [ ] 3.5 Extend the descriptive measure across agencies and suppress undersized cells

## Phase 4: Benchmark Reconciliation

- [ ] 4.1 Create reconciliation report: NIH $1.5M marginal cost comparison
- [ ] 4.2 Label citation-network diffusion separately and prohibit comparison with the Myers-Lanahan estimates
- [ ] 4.3 Document methodology differences and reconciliation narrative

## Phase 5: Testing and Integration

- [ ] 5.1 Create unit tests with synthetic patent-award linkage data
- [ ] 5.2 Create unit tests for citation network construction
- [ ] 5.3 Create integration test with sample USPTO data subset
- [ ] 5.4 Create Dagster asset wrappers
