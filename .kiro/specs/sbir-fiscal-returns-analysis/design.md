# SBIR Fiscal Returns Analysis - Design Document

## Overview

The SBIR Fiscal Returns Analysis system operationalizes economic impact analysis to compute federal fiscal returns and ROI from SBIR program spending. This system implements a comprehensive pipeline that transforms SBIR award data through economic multiplier analysis to estimate induced federal tax receipts, providing quantitative assessment of the program's return on investment to the U.S. Treasury.

The design follows the existing ETL pipeline architecture using Dagster assets, integrating with the current SBIR data infrastructure while adding specialized economic modeling capabilities. The system reproduces and extends analysis from the sibling `sbir-fiscal-returns` R-based repository, implementing it as production-ready Python assets with comprehensive quality gates and audit trails.

## Architecture

### System Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   SBIR Awards   │───▶│  Data Prep &    │───▶│  Economic       │───▶│  Tax Impact     │
│   (Existing)    │    │  Enrichment     │    │  Modeling       │    │  Calculation    │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │                        │
                              ▼                        ▼                        ▼
                       ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
                       │  NAICS/BEA      │    │  StateIO Model  │    │  ROI Analysis   │
                       │  Mapping        │    │  Integration    │    │  & Reporting    │
                       └─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Asset Group Organization

The system is organized into four primary Dagster asset groups:

1. **fiscal_data_prep**: Data preparation, enrichment, and NAICS mapping
2. **economic_modeling**: BEA sector mapping and multiplier calculations
3. **tax_calculation**: Tax impact estimation and ROI computation
4. **sensitivity_analysis**: Uncertainty quantification and scenario analysis

### Integration Points

- **Upstream Dependencies**: Leverages existing `validated_sbir_awards` and `enriched_sbir_awards` assets
- **External Data Sources**: BEA inflation indices, NAICS-to-BEA crosswalks, StateIO model outputs
- **Configuration System**: Extends existing YAML configuration with fiscal analysis parameters
- **Quality Framework**: Integrates with existing data quality gates and asset checks

## Components and Interfaces

### Core Data Models

#### FiscalAnalysisConfig
```python
@dataclass
class FiscalAnalysisConfig:
    base_year: int = 2023
    inflation_source: str = "bea_gdp_deflator"
    naics_crosswalk_version: str = "2022"
    stateio_model_version: str = "v2.1"
    tax_parameters: TaxParameterConfig
    sensitivity_parameters: SensitivityConfig
```

#### EconomicShock
```python
@dataclass
class EconomicShock:
    state: str
    bea_sector: str
    fiscal_year: int
    shock_amount: Decimal
    award_ids: List[str]
    confidence: float
```

#### TaxImpactEstimate
```python
@dataclass
class TaxImpactEstimate:
    shock_id: str
    individual_income_tax: Decimal
    payroll_tax: Decimal
    corporate_income_tax: Decimal
    excise_tax: Decimal
    total_tax_receipt: Decimal
    confidence_interval: Tuple[Decimal, Decimal]
    methodology: str
```

### Data Preparation Components

#### NAICS Enrichment Service
- **Purpose**: Enhance SBIR awards with NAICS codes using hierarchical enrichment
- **Fallback Strategy**: Original data → USAspending → SAM.gov → Agency defaults → Sector fallback
- **Quality Tracking**: Coverage rates, confidence scores, fallback usage metrics
- **Integration**: Extends existing enrichment patterns with fiscal-specific requirements

#### Geographic Resolution Service
- **Purpose**: Standardize company locations to state-level for StateIO model compatibility
- **Data Sources**: Existing company enrichment, address parsing, state mapping
- **Quality Gates**: Geographic coverage thresholds, address validation rules

#### Inflation Adjustment Service
- **Purpose**: Normalize award amounts to consistent base year using BEA deflators
- **Data Sources**: BEA GDP deflator series, configurable inflation indices
- **Methodology**: Linear interpolation for missing periods, quality flags for extrapolation

### Economic Modeling Components

#### NAICS-to-BEA Sector Mapper
- **Purpose**: Map NAICS codes to BEA Input-Output sectors using official crosswalks
- **Weighted Mapping**: Support proportional allocation across multiple BEA sectors
- **Versioning**: Track crosswalk versions, support historical mappings
- **Quality Control**: Validation against BEA sector definitions, coverage reporting

#### Economic Shock Aggregator
- **Purpose**: Aggregate SBIR awards into state-by-sector-by-fiscal-year economic shocks
- **Aggregation Logic**: Sum inflation-adjusted amounts by geographic and sectoral dimensions
- **Lineage Tracking**: Maintain award-to-shock traceability for audit purposes
- **Performance**: Chunked processing for large datasets, configurable aggregation windows

#### StateIO Model Interface
- **Purpose**: Abstract interface for state-level input-output economic models
- **Adapter Pattern**: Support multiple model implementations (IMPLAN, RIMS II, custom)
- **Model Outputs**: Wage impacts, proprietor income, gross operating surplus, tax/production impacts
- **Caching**: Model result caching for performance, versioned cache invalidation

### Tax Calculation Components

#### Economic Component Calculator
- **Purpose**: Transform StateIO outputs into federal tax base components
- **Components**: Wage income, proprietor income, corporate profits, consumption expenditures
- **Methodology**: Configurable transformation parameters, sensitivity to model assumptions
- **Quality Gates**: Component sum validation, reasonableness checks

#### Federal Tax Estimator
- **Purpose**: Convert economic components to federal tax receipt estimates
- **Tax Types**: Individual income tax, payroll tax, corporate income tax, excise taxes
- **Parameters**: Configurable effective tax rates, progressive rate structures
- **Temporal Handling**: Multi-year impact modeling, present value calculations

#### ROI Calculator
- **Purpose**: Compute return on investment metrics for SBIR program evaluation
- **Metrics**: Total ROI, payback period, net present value, benefit-cost ratio
- **Scenarios**: Multiple discount rates, time horizons, sensitivity parameters
- **Reporting**: Structured output for policy analysis, confidence intervals

### Sensitivity Analysis Components

#### Parameter Sweep Engine
- **Purpose**: Generate scenario combinations for uncertainty quantification
- **Parameters**: Tax rates, multipliers, model assumptions, temporal parameters
- **Sampling**: Monte Carlo sampling, Latin hypercube sampling, grid search
- **Parallelization**: Distributed scenario execution, result aggregation

#### Uncertainty Quantifier
- **Purpose**: Compute confidence intervals and uncertainty bands
- **Methods**: Bootstrap resampling, parametric confidence intervals, percentile methods
- **Outputs**: Min/mean/max estimates, confidence intervals, sensitivity indices
- **Quality Flags**: High-uncertainty identification, robustness indicators

## Data Models

### Input Data Structures

#### Enriched SBIR Award
```python
@dataclass
class EnrichedSbirAward:
    award_id: str
    company_uei: str
    company_name: str
    company_state: str
    award_amount: Decimal
    award_date: date
    fiscal_year: int
    naics_code: Optional[str]
    naics_confidence: float
    naics_source: str
    phase: str
    agency: str
```

#### BEA Sector Mapping
```python
@dataclass
class BeaSectorMapping:
    naics_code: str
    bea_sector_code: str
    bea_sector_name: str
    allocation_weight: float
    crosswalk_version: str
    effective_date: date
```

### Intermediate Data Structures

#### Normalized Award
```python
@dataclass
class NormalizedAward:
    award_id: str
    company_uei: str
    state: str
    bea_sector: str
    fiscal_year: int
    inflation_adjusted_amount: Decimal
    base_year: int
    inflation_factor: float
    quality_flags: List[str]
```

#### Economic Impact
```python
@dataclass
class EconomicImpact:
    shock_id: str
    state: str
    bea_sector: str
    fiscal_year: int
    direct_impact: Decimal
    indirect_impact: Decimal
    induced_impact: Decimal
    total_impact: Decimal
    wage_impact: Decimal
    proprietor_income_impact: Decimal
    gross_operating_surplus: Decimal
    tax_production_impact: Decimal
    model_version: str
```

### Output Data Structures

#### Fiscal Return Summary
```python
@dataclass
class FiscalReturnSummary:
    analysis_id: str
    total_sbir_investment: Decimal
    total_tax_receipts: Decimal
    net_fiscal_return: Decimal
    roi_ratio: float
    payback_period_years: Optional[float]
    confidence_interval_low: Decimal
    confidence_interval_high: Decimal
    analysis_date: datetime
    base_year: int
    methodology_version: str
```

## Error Handling

### Error Classification

#### Data Quality Errors
- **Missing NAICS Coverage**: Awards without sector classification
- **Geographic Resolution Failures**: Unresolvable company locations
- **Inflation Data Gaps**: Missing deflator values for award periods
- **Severity**: WARNING (continue with fallbacks) or ERROR (block processing)

#### Model Integration Errors
- **StateIO Model Failures**: Model execution errors, invalid parameters
- **Crosswalk Inconsistencies**: NAICS-BEA mapping conflicts, version mismatches
- **Parameter Validation**: Invalid tax rates, multiplier bounds violations
- **Severity**: ERROR (block affected calculations, continue others)

#### Calculation Errors
- **Numerical Overflow**: Large aggregation results, precision loss
- **Negative Tax Estimates**: Invalid model outputs, parameter conflicts
- **Convergence Failures**: Iterative calculation non-convergence
- **Severity**: ERROR (flag affected estimates, continue processing)

### Error Recovery Strategies

#### Graceful Degradation
- **Partial Results**: Continue analysis with available data, flag incomplete coverage
- **Fallback Parameters**: Use conservative estimates when preferred parameters unavailable
- **Quality Flags**: Comprehensive flagging of assumptions and data limitations

#### Retry Logic
- **Transient Failures**: Exponential backoff for external model calls
- **Batch Processing**: Retry failed batches independently
- **Circuit Breaker**: Disable failing components after threshold breaches

#### Error Reporting
- **Structured Logging**: Detailed error context, affected data ranges
- **Quality Metrics**: Error rates by component, data coverage statistics
- **User Notifications**: Clear error messages with remediation guidance

## Testing Strategy

### Unit Testing

#### Component Testing
- **Data Preparation**: NAICS enrichment, inflation adjustment, geographic resolution
- **Economic Modeling**: Sector mapping, shock aggregation, multiplier calculations
- **Tax Calculation**: Component transformation, tax estimation, ROI computation
- **Coverage Target**: ≥90% code coverage for core calculation logic

#### Mock Strategies
- **External Models**: Mock StateIO model responses with realistic test data
- **API Services**: Mock BEA data services, inflation index APIs
- **Configuration**: Parameterized test configurations for different scenarios

### Integration Testing

#### Pipeline Testing
- **End-to-End**: Complete pipeline execution with synthetic SBIR data
- **Asset Dependencies**: Verify correct asset dependency resolution
- **Quality Gates**: Test quality check enforcement and blocking behavior
- **Performance**: Validate processing within configured time thresholds

#### Data Integration
- **Real Data Subsets**: Test with actual SBIR award samples
- **External Data**: Validate integration with BEA crosswalks, inflation data
- **Model Integration**: Test StateIO model adapter with real model instances

### Validation Testing

#### Economic Validation
- **Known Results**: Reproduce results from R-based reference implementation
- **Sensitivity Analysis**: Validate uncertainty quantification methods
- **Boundary Conditions**: Test extreme parameter values, edge cases
- **Cross-Validation**: Compare results across different model configurations

#### Quality Validation
- **Audit Trail**: Verify complete lineage tracking from awards to estimates
- **Reproducibility**: Confirm identical results for identical inputs
- **Configuration Sensitivity**: Test parameter override behavior
- **Error Handling**: Validate graceful degradation under various failure modes

### Performance Testing

#### Scalability Testing
- **Large Datasets**: Test with full SBIR award history (~533K awards)
- **Memory Usage**: Monitor memory consumption during processing
- **Parallel Processing**: Validate concurrent scenario execution
- **Throughput**: Measure processing rates for different pipeline stages

#### Benchmark Testing
- **Baseline Performance**: Establish performance baselines for regression detection
- **Optimization Validation**: Verify performance improvements from optimizations
- **Resource Utilization**: Monitor CPU, memory, and I/O usage patterns
- **Bottleneck Identification**: Profile pipeline stages for optimization opportunities

## Design Decisions and Rationales

### Asset-Based Architecture
**Decision**: Implement as Dagster assets integrated with existing pipeline
**Rationale**: Leverages existing infrastructure, provides dependency management, enables incremental processing, and maintains consistency with project architecture

### Hierarchical NAICS Enrichment
**Decision**: Extend existing enrichment patterns with fiscal-specific requirements
**Rationale**: Reuses proven enrichment infrastructure, maintains data quality standards, and provides audit trails for sector classification decisions

### StateIO Model Abstraction
**Decision**: Create adapter interface for multiple economic models
**Rationale**: Enables model comparison, supports different institutional preferences, allows for model evolution, and provides fallback options

### Inflation Adjustment Integration
**Decision**: Normalize all monetary values to consistent base year
**Rationale**: Ensures temporal comparability, follows economic analysis best practices, and enables multi-year trend analysis

### Comprehensive Sensitivity Analysis
**Decision**: Implement full uncertainty quantification with parameter sweeps
**Rationale**: Addresses policy analysis requirements, provides robustness assessment, and supports evidence-based decision making

### Quality-First Design
**Decision**: Integrate comprehensive quality gates and audit trails
**Rationale**: Ensures analysis reproducibility, supports regulatory compliance, and maintains scientific rigor for policy applications

### Configuration-Driven Parameters
**Decision**: Externalize all analysis parameters to YAML configuration
**Rationale**: Enables scenario analysis, supports different institutional requirements, and allows for parameter evolution without code changes