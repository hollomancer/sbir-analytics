# Leverage Ratio Analysis — Tasks

## Phase 1: Core Ratio Computation

- [ ] 1.1 Create `src/tools/mission_b/leverage_ratio.py` with `LeverageRatioCalculator` class
- [ ] 1.2 Implement SBIR/STTR obligation separation using FPDS product-or-service codes and contract type flags
- [ ] 1.3 Implement firm-level ratio computation (non-SBIR obligations / SBIR obligations per vendor)
- [ ] 1.4 Implement aggregate ratio computation (sum non-SBIR / sum SBIR across all vendors)
- [ ] 1.5 Add entity resolution coverage reporting (match rate, unresolved vendors)

## Phase 2: Cohort Stratification

- [ ] 2.1 Create `CohortStratifier` in `src/tools/mission_b/leverage_ratio.py`
- [ ] 2.2 Implement award vintage stratification (group by first SBIR award year)
- [ ] 2.3 Implement firm size stratification (revenue/employee buckets from SAM.gov)
- [ ] 2.4 Implement technology area stratification using CET classifier output
- [ ] 2.5 Implement experienced vs. new firm classification (>1 prior SBIR award = experienced)
- [ ] 2.6 Implement time-series decomposition (ratio by fiscal year, trend detection)

## Phase 3: NASEM Reconciliation

- [ ] 3.1 Create `NASEMReconciler` class with benchmark constants (DOD 4:1, etc.)
- [ ] 3.2 Implement methodology comparison report (data sources, time periods, inclusion criteria)
- [ ] 3.3 Implement difference attribution analysis (what explains divergence from NASEM)
- [ ] 3.4 Generate reconciliation brief in markdown format

## Phase 4: Cross-Agency Extension

- [ ] 4.1 Create `AgencyComparator` for running ratio computation across agencies
- [ ] 4.2 Implement DOE leverage ratio (contracts + grants — DOE uses both)
- [ ] 4.3 Implement cross-agency comparison output (table + visualization data)

## Phase 5: Testing and Integration

- [ ] 5.1 Create unit tests for ratio computation with synthetic FPDS data
- [ ] 5.2 Create integration test with sample vendor universe
- [ ] 5.3 Create Dagster asset wrapper for pipeline execution
- [ ] 5.4 Add leverage ratio to CLI reporting commands
