# Implementation Plan

- [x] 1. Set up fiscal returns analysis configuration and data models
  - Create fiscal analysis configuration schema in `src/config/schemas.py`
  - Define core data models: `FiscalAnalysisConfig`, `EconomicShock`, `TaxImpactEstimate`, `FiscalReturnSummary`
  - Add fiscal analysis configuration section to `config/base.yaml`
  - _Requirements: 6.1, 6.2_
  - Implementation: `src/config/schemas.py::FiscalAnalysisConfig` (line 613), `src/models/fiscal_models.py`, `config/base.yaml::fiscal_analysis` (line 362)

- [x] 2. Implement data preparation and enrichment components
  - [x] 2.1 Create NAICS enrichment service for fiscal analysis
    - Extend existing enrichment patterns with fiscal-specific NAICS requirements
    - Implement hierarchical fallback chain: original → USAspending → SAM.gov → agency defaults → sector fallback
    - Add confidence scoring and quality tracking for NAICS coverage
    - _Requirements: 1.1, 1.2, 1.3, 5.1, 5.2_
    - Design & requirements: see `.kiro/specs/sbir-fiscal-returns-analysis/design.md` and `.kiro/specs/sbir-fiscal-returns-analysis/requirements.md` for the NAICS enrichment specification and mapped requirements.

  - [x] 2.2 Implement geographic resolution service
    - Standardize company locations to state-level for StateIO model compatibility
    - Integrate with existing company enrichment and address parsing
    - Add geographic coverage validation and quality gates
    - _Requirements: 1.1, 5.1_

  - [x] 2.3 Create inflation adjustment service
    - Implement BEA GDP deflator integration for monetary normalization
    - Support configurable base year adjustment with linear interpolation
    - Add quality flags for extrapolation and missing periods
    - _Requirements: 1.4, 6.1_

- [x] 3. Implement economic modeling components
  - [x] 3.1 Create NAICS-to-BEA sector mapper
    - Implement official crosswalk mapping with weighted allocations
    - Support proportional allocation across multiple BEA sectors
    - Add versioning and historical mapping support
    - _Requirements: 2.1, 2.2, 5.4_
    - Implementation: `src/enrichers/fiscal_bea_mapper.py`, `src/assets/fiscal_assets.py::bea_mapped_sbir_awards`

  - [x] 3.2 Implement economic shock aggregator
    - Aggregate SBIR awards into state-by-sector-by-fiscal-year economic shocks
    - Maintain award-to-shock traceability for audit purposes
    - Support chunked processing for large datasets
    - _Requirements: 2.3, 2.4, 5.3_
    - Implementation: `src/transformers/fiscal_shock_aggregator.py`, `src/assets/fiscal_assets.py::economic_shocks`

  - [x] 3.3 Create StateIO/USEEIO adapter using rpy2
    - Design abstract `EconomicModelInterface` for state-level input-output economic models
    - Implement `RStateIOAdapter` with rpy2 calling EPA's USEEIO/StateIO R packages
    - Add R dependency management (rpy2, EPA packages installation/configuration)
    - Implement result caching with versioned keys and automatic data conversion
    - Add pandas ↔ R data.frame conversion utilities
    - _Requirements: 2.5, 6.1_
    - Implementation: `src/transformers/economic_model_interface.py`, `src/transformers/r_stateio_adapter.py`, `src/utils/r_conversion.py`, `src/assets/fiscal_assets.py::economic_impacts`

- [x] 4. Implement tax calculation components
  - [x] 4.1 Create economic component calculator
    - Transform StateIO outputs into federal tax base components
    - Generate wage impacts, proprietor income, gross operating surplus estimates
    - Add component sum validation and reasonableness checks
    - _Requirements: 3.1, 3.2_
    - Implementation: `src/transformers/fiscal_component_calculator.py`

  - [x] 4.2 Implement federal tax estimator
    - Convert economic components to federal tax receipt estimates
    - Support individual income tax, payroll tax, corporate income tax, excise taxes
    - Use configurable effective tax rates and progressive rate structures
    - _Requirements: 3.2, 3.3_
    - Implementation: `src/transformers/fiscal_tax_estimator.py`

  - [x] 4.3 Create ROI calculator
    - Compute return on investment metrics for SBIR program evaluation
    - Calculate total ROI, payback period, net present value, benefit-cost ratio
    - Support multiple discount rates and time horizons
    - _Requirements: 3.4, 3.5_
    - Implementation: `src/transformers/fiscal_roi_calculator.py`

- [x] 5. Implement sensitivity analysis and uncertainty quantification
  - [x] 5.1 Create parameter sweep engine
    - Generate scenario combinations for uncertainty quantification
    - Support Monte Carlo sampling, Latin hypercube sampling, grid search
    - Enable distributed scenario execution and result aggregation
    - _Requirements: 4.1, 4.4, 6.4_
    - Implementation: `src/transformers/fiscal_parameter_sweep.py`

  - [x] 5.2 Implement uncertainty quantifier
    - Compute confidence intervals and uncertainty bands
    - Support bootstrap resampling and parametric confidence intervals
    - Generate min/mean/max estimates with sensitivity indices
    - _Requirements: 4.2, 4.3, 4.5_
    - Implementation: `src/transformers/fiscal_uncertainty_quantifier.py`

- [x] 6. Create Dagster assets for fiscal returns analysis pipeline
  - [x] 6.1 Implement fiscal data preparation assets
    - Create `fiscal_prepared_sbir_awards` asset with NAICS enrichment and geographic resolution
    - Create `inflation_adjusted_awards` asset with BEA deflator normalization
    - Add asset checks for NAICS coverage rates and geographic resolution success
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 5.1_
    - Implementation: `src/assets/fiscal_assets.py::fiscal_prepared_sbir_awards`, `inflation_adjusted_awards`

  - [x] 6.2 Implement economic modeling assets
    - [x] Create `bea_sector_mapped_awards` asset with NAICS-to-BEA sector mapping
    - [x] Create `economic_shocks` asset with state-by-sector-by-fiscal-year aggregation
    - [x] Create `economic_impacts` asset with StateIO model integration
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 6.3 Implement tax calculation assets
    - Create `tax_base_components` asset with economic component transformation
    - Create `federal_tax_estimates` asset with tax receipt calculations
    - Create `fiscal_return_summary` asset with ROI computation
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
    - Implementation: `src/assets/fiscal_assets.py::tax_base_components`, `federal_tax_estimates`, `fiscal_return_summary`

  - [x] 6.4 Implement sensitivity analysis assets
    - Create `sensitivity_scenarios` asset with parameter sweep generation
    - Create `uncertainty_analysis` asset with confidence interval computation
    - Create `fiscal_returns_report` asset with comprehensive analysis results
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
    - Implementation: `src/assets/fiscal_assets.py::sensitivity_scenarios`, `uncertainty_analysis`, `fiscal_returns_report`

- [x] 7. Add comprehensive quality gates and audit trails
  - [x] 7.1 Implement data quality asset checks
    - Add NAICS coverage rate validation with configurable thresholds
    - Add geographic resolution success rate checks
    - Add inflation adjustment quality validation
    - _Requirements: 5.1, 5.2, 1.5_
    - Implementation: `src/assets/fiscal_assets.py` (asset checks: `fiscal_naics_coverage_check`, `fiscal_geographic_resolution_check`, `inflation_adjustment_quality_check`)

  - [x] 7.2 Create audit trail and lineage tracking
    - Implement comprehensive logging of parameter values and transformation steps
    - Add data lineage tracking from source awards to final estimates
    - Create structured audit logs with assumption documentation
    - _Requirements: 5.3, 5.4, 5.5_
    - Implementation: `src/utils/fiscal_audit_trail.py`

- [x] 8. Integrate with existing pipeline infrastructure
  - [x] 8.1 Add fiscal returns job definition
    - Create `fiscal_returns_analysis_job` in `src/assets/jobs/`
    - Define asset dependencies and execution order
    - Add job to main Dagster definitions
    - _Requirements: 6.3, 6.5_
    - Implementation: `src/assets/jobs/fiscal_returns_job.py`, registered in `src/definitions.py`

  - [x] 8.2 Add performance monitoring and optimization
    - Integrate with existing performance monitoring framework
    - Add memory usage tracking and chunked processing support
    - Implement configurable performance thresholds and timeouts
    - _Requirements: 1.5, 6.5_
    - Implementation: All fiscal assets use `performance_monitor.monitor_block()`, config in `config/base.yaml::fiscal_analysis.performance`

- [ ]* 9. Create comprehensive test suite
  - [ ]* 9.1 Write unit tests for core calculation logic
    - Test NAICS enrichment and BEA sector mapping functions
    - Test inflation adjustment and economic shock aggregation
    - Test tax calculation and ROI computation methods
    - _Requirements: All requirements validation_

  - [ ]* 9.2 Write integration tests for asset pipeline
    - Test end-to-end pipeline execution with synthetic data
    - Test asset dependency resolution and quality gate enforcement
    - Test performance within configured thresholds
    - _Requirements: Pipeline integration validation_

  - [ ]* 9.3 Create validation tests against reference implementation
    - Reproduce results from R-based reference implementation
    - Validate sensitivity analysis and uncertainty quantification methods
    - Test boundary conditions and edge cases
    - _Requirements: Economic validation_