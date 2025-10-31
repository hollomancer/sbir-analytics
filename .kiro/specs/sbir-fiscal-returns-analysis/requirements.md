# Requirements Document

## Introduction

The SBIR Fiscal Returns Analysis feature enables computation of federal fiscal returns and return on investment (ROI) from SBIR program spending through economic multiplier analysis. This system reproduces and operationalizes the analysis from the sibling `sbir-fiscal-returns` R-based repository, focusing on estimating ROI to the U.S. Treasury via induced federal tax receipts from SBIR award spending.

## Glossary

- **Fiscal_Returns_System**: The SBIR Fiscal Returns Analysis system implemented as Dagster assets
- **SBIR_Award**: Small Business Innovation Research program award record with funding and recipient information
- **Economic_Multiplier**: Factor representing indirect and induced economic effects of direct spending
- **Tax_Receipt**: Federal tax revenue generated from economic activity (IIT, payroll, CIT, excise)
- **ROI_Calculation**: Return on investment computation comparing tax receipts to SBIR spending
- **Inflation_Adjustment**: Process of normalizing monetary values to a consistent base year
- **NAICS_Code**: North American Industry Classification System code identifying business sectors
- **BEA_IO_Sector**: Bureau of Economic Analysis Input-Output sector classification
- **StateIO_Model**: State-level input-output economic model for impact analysis
- **Fiscal_Year**: Government fiscal year period for analysis aggregation
- **Sensitivity_Band**: Range of estimates reflecting parameter uncertainty
- **Audit_Trail**: Documented record of assumptions, parameters, and data transformations

## Requirements

### Requirement 1

**User Story:** As a policy analyst, I want to compute federal fiscal returns from SBIR spending, so that I can evaluate the program's return on investment to the Treasury.

#### Acceptance Criteria

1. WHEN SBIR awards are processed, THE Fiscal_Returns_System SHALL resolve company identifiers and geographic locations
2. WHEN USAspending data is available, THE Fiscal_Returns_System SHALL enrich NAICS codes from external sources
3. IF NAICS enrichment fails, THEN THE Fiscal_Returns_System SHALL apply configured fallback mappings with quality flags
4. WHEN normalizing monetary values, THE Fiscal_Returns_System SHALL adjust amounts to the configured base year using BEA inflation indices
5. THE Fiscal_Returns_System SHALL produce tax impact estimates within configured performance thresholds

## NAICS Enrichment Specific Requirements

These requirements capture the functional and quality expectations for the NAICS enrichment component referenced in Requirement 1 and 5.

1. WHEN processing awards, THE NAICS enrichment service SHALL prefer NAICS values present on the original award record (origin=`original`) and preserve them with high confidence.
2. WHEN USAspending local data is available, THE service SHALL attempt award-level lookup in `data/raw/usaspending/` and use award-level NAICS (origin=`usaspending_award`) before recipient-level fallbacks.
3. WHEN award-level NAICS are not present, THE service SHALL attempt recipient-level NAICS lookup in USAspending and use origin=`usaspending_recipient`.
4. IF both award- and recipient-level sources fail, THE service SHALL apply SAM.gov or configured `agency_default` or `sector_fallback` mappings in that order, recording the chosen origin and confidence.
5. THE service SHALL assign a `naics_confidence` score (0.0-1.0) corresponding to the origin and tie-breaking logic, and include `naics_trace` for auditability.
6. THE service SHALL persist a compact index (Parquet/DuckDB) derived from `data/raw/usaspending/` at `data/processed/usaspending/naics_index.parquet` for repeatable, performant joins.
7. THE service SHALL emit quality metrics for coverage (`% awards with assigned NAICS`), fallback usage rates by origin, and counts of `multiple_candidates` or `missing` flags.
8. WHEN NAICS are missing, THE service SHALL not raise errors; instead flag the award with `naics_quality_flags` containing `missing` and allow downstream quality gates to decide blocking behavior.

These specific requirements map to higher-level acceptance criteria in Requirement 1 and Requirement 5 (data quality and audit trail expectations).

### Requirement 2

**User Story:** As an economist, I want to map SBIR awards to economic sectors and compute multiplier effects, so that I can estimate induced economic activity.

#### Acceptance Criteria

1. WHEN NAICS codes are available, THE Fiscal_Returns_System SHALL map classifications to BEA Input-Output sectors using configured crosswalks
2. WHERE weighted mappings exist, THE Fiscal_Returns_System SHALL apply proportional allocations across multiple BEA sectors
3. WHEN aggregating economic shocks, THE Fiscal_Returns_System SHALL compute state-by-IO-sector-by-fiscal-year totals
4. THE Fiscal_Returns_System SHALL preserve award lineage through all transformation stages
5. WHEN computing multiplier effects, THE Fiscal_Returns_System SHALL use StateIO model outputs or configured adapter interfaces

### Requirement 3

**User Story:** As a Treasury analyst, I want to estimate federal tax receipts from SBIR-induced economic activity, so that I can quantify fiscal returns to the government.

#### Acceptance Criteria

1. WHEN model components are computed, THE Fiscal_Returns_System SHALL generate wage, proprietor income, gross operating surplus, and tax and production impact estimates
2. WHEN mapping to tax bases, THE Fiscal_Returns_System SHALL transform economic components into federal tax categories using configured parameters
3. THE Fiscal_Returns_System SHALL compute individual income tax, payroll tax, corporate income tax, and excise tax estimates
4. THE Fiscal_Returns_System SHALL generate ROI calculations comparing total tax receipts to SBIR program costs
5. THE Fiscal_Returns_System SHALL compute payback period estimates for Treasury investment recovery

### Requirement 4

**User Story:** As a research director, I want sensitivity analysis and uncertainty quantification, so that I can understand the robustness of fiscal return estimates.

#### Acceptance Criteria

1. WHERE sensitivity parameters are configured, THE Fiscal_Returns_System SHALL generate parameter sweep scenarios
2. THE Fiscal_Returns_System SHALL produce minimum, mean, and maximum estimate bands for all tax impact calculations
3. WHEN publishing results, THE Fiscal_Returns_System SHALL include confidence intervals and uncertainty ranges
4. THE Fiscal_Returns_System SHALL document parameter assumptions and sensitivity test results
5. THE Fiscal_Returns_System SHALL flag high-uncertainty estimates exceeding configured thresholds

### Requirement 5

**User Story:** As a data quality manager, I want comprehensive audit trails and quality metrics, so that I can validate analysis reproducibility and identify data gaps.

#### Acceptance Criteria

1. THE Fiscal_Returns_System SHALL log NAICS coverage rates and enrichment success metrics
2. THE Fiscal_Returns_System SHALL document all fallback usage and assumption applications
3. WHEN processing awards, THE Fiscal_Returns_System SHALL track data lineage from source to final estimates
4. THE Fiscal_Returns_System SHALL generate structured audit logs with parameter values and transformation steps
5. THE Fiscal_Returns_System SHALL produce data quality reports identifying missing data and estimation leakages

### Requirement 6

**User Story:** As a system administrator, I want configurable and reproducible analysis execution, so that I can run consistent analyses across different scenarios and time periods.

#### Acceptance Criteria

1. THE Fiscal_Returns_System SHALL read analysis parameters from YAML configuration files
2. WHERE environment overrides are provided, THE Fiscal_Returns_System SHALL apply runtime parameter modifications
3. THE Fiscal_Returns_System SHALL produce deterministic outputs for identical input data and configuration
4. WHEN executing scenarios, THE Fiscal_Returns_System SHALL support parallel processing of parameter combinations
5. THE Fiscal_Returns_System SHALL complete baseline analysis within configured performance thresholds