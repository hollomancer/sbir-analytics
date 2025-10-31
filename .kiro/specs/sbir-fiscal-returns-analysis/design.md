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
#### NAICS Enrichment Service — Detailed Design

- Purpose: Enrich SBIR awards and recipient records with NAICS codes using a deterministic, auditable fallback chain that preferentially uses local USAspending data under `data/raw/usaspending/`.
- Produce a canonical `naics_assigned` for each award (and optionally per-recipient), plus metadata (origin, confidence, quality flags, trace) for downstream quality gates and auditing.

Contract (inputs / outputs / errors)
- Input: iterable of award records (pandas.DataFrame or iterable of dicts) containing:
    - `award_id` (string/int)
    - `recipient_unique_id` or `recipient_name` (optional)
    - `existing_naics` (optional)
    - `fiscal_year`, `award_date`, `agency` (optional but useful)
- Output: enriched award records with new fields:
    - `naics_assigned` (string, nullable) — normalized NAICS (prefer 6-digit padded)
    - `naics_origin` (string enum)
    - `naics_confidence` (float 0.0-1.0)
    - `naics_quality_flags` (list[string] or comma-separated string)
    - `naics_trace` (json) — list of candidate sources and reasoning
- Errors: the service should not raise on missing NAICS; instead set `naics_assigned = None` and add `missing` quality flag. Exceptions are reserved for I/O or corrupted index files.

Data sources & formats
- Primary local source: SBIR awards dataset (the pipeline's input). Can be supplied as a DataFrame.
- Fallback source (on-disk): `data/raw/usaspending/usaspending-db-subset_20251006.zip` (assumed to contain CSVs or extractable tables). Implementation will:
    - Inspect the zip to find files matching patterns: `*award*.csv`, `*recipient*.csv`, `*naics*.csv`.
    - Extract/scan relevant columns (`award_id`, `recipient_id`, `naics`, `naics_code`, `NAICS` etc.).
    - Build an index mapping `award_identifier -> naics` and `recipient_identifier -> naics`.
- Optional sources: SAM.gov, internal agency defaults, sector-level fallbacks. These will be integrated where available.

Fallback chain (ordered)
1. `original` — NAICS present on the input award record and marked verified.
2. `usaspending_award` — award-level NAICS from USAspending matched by award identifiers.
3. `usaspending_recipient` — recipient-level NAICS from USAspending matched by recipient unique id or cleaned recipient name.
4. `sam` — SAM.gov NAICS if available (via existing enrichment in the repo).
5. `agency_default` — default NAICS mapped from the awarding agency/department.
6. `sector_fallback` — coarse sector → representative NAICS mapping (low confidence).
7. `unknown` — no NAICS found; `naics_assigned = None` and `naics_quality_flags` includes `missing`.

Confidence scoring (recommended)
- `original`: base 0.98 (verified assignments near 1.0)
- `usaspending_award`: base 0.85; +0.05 if award year matches and NAICS is 6-digit exact
- `usaspending_recipient`: base 0.7; +0.1 if recipient id match exact and recipient active in award year
- `sam`: base 0.6
- `agency_default`: base 0.4
- `sector_fallback`: base 0.2
- On ties or multiple candidates: reduce confidence by 0.1 and add `multiple_candidates` flag

Quality flags (non-exclusive)
- `missing` — no NAICS found
- `partial_match` — code shorter than 6 digits or truncated
- `historical_mismatch` — NAICS candidate from a different fiscal year (possible churn)
- `extrapolated` — derived from sector or agency defaults
- `multiple_candidates` — ambiguous; recommendations saved in `naics_trace`

Normalization rules
- NAICS codes normalized to strings of 2-6 digits; prefer storing 6-digit where available. Keep original formatting in `naics_trace`.
- Strip non-numeric characters and leading zeros as appropriate; do not drop meaningful leading zeros if present in strings.

Storage/schema
- Enrichment output columns (add to awards table/DataFrame):
    - `naics_assigned` (VARCHAR/str, NULLABLE)
    - `naics_origin` (VARCHAR)
    - `naics_confidence` (FLOAT)
    - `naics_quality_flags` (JSON / TEXT list)
    - `naics_trace` (JSON) — optional, contains ordered candidates
- Persist a local index built from USAspending at `data/processed/usaspending/naics_index.parquet` for fast joins.

API surface (Python)
- Module: `src/enrichers/naics_enricher.py`
- Primary class: `NAICSEnricher`
    - `__init__(self, config: NAICSEnricherConfig)` — config includes `usaspending_path`, `cache_path`, thresholds
    - `load_usaspending_index(self) -> None` — builds or loads persisted index mapping award/recipient -> naics candidates
    - `enrich_awards(self, df: pd.DataFrame, chunk_size: int = 100_000) -> pd.DataFrame` — vectorized enrichment
    - `enrich_record(self, record: Mapping) -> Mapping` — single-record API, useful for debugging
    - `explain(self, award_id: str) -> dict` — returns `naics_trace` and selection rationale
- Config knobs:
    - `usaspending_path` (str): path to zip or extracted folder
    - `cache_path` (str|None): path to persisted index parquet
    - `prefer_original` (bool)
    - `confidence_map` (dict): overrides for base scores
    - `chunk_size`, `n_workers`

Performance & implementation notes
- Use DuckDB or Parquet for indexing large USAspending CSVs and fast joins. Creating a compact Parquet index of only identifier -> naics is recommended.
- For initial implementation use pandas with chunked processing and an in-memory dict/index for small subsets.
- Persist extracted index to `data/processed/usaspending/naics_index.parquet` to avoid repeated zip scans.
- Keep the enricher idempotent: do not overwrite higher-confidence assignments unless `force=True`.

Testing plan
- Unit tests (fast):
    - `test_enrich_with_original_naics` — original NAICS preserved
    - `test_fallback_to_usaspending_award` — award-level fallback works
    - `test_recipient_match` — recipient-level fallback
    - `test_missing_naics_flagging` — missing NAICS handled gracefully
    - `test_confidence_and_trace` — correct confidence and trace structure
- Integration test (small fixture zip): create a tiny CSV set mimicking USAspending files under `tests/fixtures/usaspending_small/` and run end-to-end `enrich_awards`.

Operational assumptions
- The provided zip `data/raw/usaspending/usaspending-db-subset_20251006.zip` contains useful NAICS-bearing files. If the zip is a Postgres dump rather than CSVs, the implementation will either:
    - attempt to locate CSVs inside the zip, or
    - require the user to extract the relevant tables to CSV/Parquet, or
    - use DuckDB to read SQL dump if feasible.
- No external network calls required.

Next steps (implementation)
1. Inspect `data/raw/usaspending/usaspending-db-subset_20251006.zip` and record file layout.
2. Implement `NAICSEnricher` skeleton and `load_usaspending_index()` to build Parquet index.
3. Implement `enrich_awards()` with fallback chain and confidence scoring.
4. Add unit tests and the small integration fixture.
5. Wire the enricher into the `fiscal_prepared_sbir_awards` asset.


Change log
- 2025-10-31: Initial NAICS enrichment detailed design added.

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