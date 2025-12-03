# Implementation Plan

## Task Overview

This implementation plan tracks the remaining work for the company categorization feature. Most core functionality has been implemented, including data models, classification logic, enrichment functions, and Dagster assets. The remaining tasks focus on configuration, Neo4j loading, testing, and validation.

## Implementation Status Summary

**Completed:**
- ✅ Data models (`src/models/categorization.py`)
- ✅ Contract classifier (`src/transformers/company_categorization.py`)
- ✅ Company aggregator (`src/transformers/company_categorization.py`)
- ✅ USAspending contract retrieval (`src/enrichers/company_categorization.py`)
- ✅ Dagster asset (`src/assets/company_categorization.py`)
- ✅ Asset checks for quality validation

**Remaining:**
- Configuration schema and defaults
- Neo4j loader implementation
- Comprehensive testing
- High-volume validation
- Documentation

## Implementation Tasks

- [x] 1. Create data models for contract and company classifications
  - Create `ContractClassification` Pydantic model in `src/models/`
  - Create `CompanyClassification` Pydantic model in `src/models/`
  - Add field validators for classification values and confidence scores
  - Add model serialization methods for DataFrame conversion
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - _Status: Completed in `src/models/categorization.py`_

- [x] 2. Implement contract classifier module
  - [x] 2.1 Create `src/transformers/company_categorization.py` module
    - Implement `classify_contract()` function with PSC-based rules
    - Implement contract type override logic (CPFF, Cost-Type, T&M → Service)
    - Implement description inference logic (prototype, hardware, device → Product)
    - Implement SBIR phase adjustment logic (Phase I/II → R&D)
    - Return classification with method and confidence metadata
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
    - _Status: Completed with comprehensive classification logic_

  - [x] 2.2 Implement PSC classification rules
    - Add logic for numeric PSC → Product classification
    - Add logic for alphabetic PSC → Service classification
    - Add logic for PSC codes starting with A/B → R&D classification
    - _Requirements: 2.1, 2.2, 2.3_
    - _Status: Completed in `_classify_by_psc()` helper function_

  - [x] 2.3 Implement contract type and pricing rules
    - Add CPFF contract type → Service override
    - Add Cost-Type contract type → Service override
    - Add T&M pricing → Service override
    - Add FFP pricing → retain PSC classification
    - _Requirements: 2.4, 2.5_
    - _Status: Completed with helper functions for contract type detection_

  - [x] 2.4 Implement description-based inference
    - Add keyword detection for "prototype" → Product
    - Add keyword detection for "hardware" → Product
    - Add keyword detection for "device" → Product
    - Record inference method in classification metadata
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
    - _Status: Completed in `_check_product_keywords()` helper function_

  - [x] 2.5 Implement SBIR phase adjustment
    - Add Phase I classification → R&D (unless numeric PSC)
    - Add Phase II classification → R&D (unless numeric PSC)
    - Add Phase I/II with numeric PSC → Product
    - Add R&D classification → treat as Service for aggregation
    - Add Phase III → apply standard rules without adjustment
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
    - _Status: Completed with SBIR phase logic in `classify_contract()`_

- [x] 3. Implement company aggregator module
  - [x] 3.1 Create company aggregation function
    - Implement `aggregate_company_classification()` function
    - Calculate dollar-weighted Product percentage
    - Calculate dollar-weighted Service+R&D percentage
    - Apply 51% threshold for Product-leaning classification (updated from 60%)
    - Apply 51% threshold for Service-leaning classification (updated from 60%)
    - Apply Mixed classification for neither threshold met
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
    - _Status: Completed with 51% threshold and agency breakdown_

  - [x] 3.2 Implement confidence level assignment
    - Assign Low confidence for <2 awards
    - Assign Medium confidence for 2-5 awards
    - Assign High confidence for >5 awards
    - Record award count in classification metadata
    - Classify companies with <2 awards as Uncertain
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
    - _Status: Completed in `aggregate_company_classification()`_

  - [x] 3.3 Implement override rules
    - Detect companies with >6 PSC families → classify as Mixed
    - Record PSC family count in classification metadata
    - Preserve original calculated classification in metadata
    - Record all applicable override reasons
    - Skip other overrides for Uncertain companies
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
    - _Status: Completed with PSC family diversity override_

- [x] 4. Implement USAspending contract retrieval
  - [x] 4.1 Create contract retrieval function
    - Implement `retrieve_company_contracts()` function in `src/enrichers/company_categorization.py`
    - Query USAspending by UEI using existing `DuckDBUSAspendingExtractor`
    - Query USAspending by DUNS if UEI query returns no results
    - Query USAspending by CAGE if DUNS query returns no results
    - Extract required fields: PSC, contract_type, pricing, description, award_amount
    - _Requirements: 1.1, 1.2_
    - _Status: Completed with both DuckDB and API implementations_

  - [x] 4.2 Implement SBIR phase detection
    - Identify SBIR awards in USAspending results
    - Extract SBIR phase from award description or metadata
    - Record SBIR phase in contract record
    - _Requirements: 1.3_
    - _Status: Completed in `_extract_sbir_phase()` helper function_

  - [x] 4.3 Handle empty results
    - Return empty DataFrame for companies with no USAspending contracts
    - Log warning for companies with no contracts found
    - Classify companies with no contracts as Uncertain
    - _Requirements: 1.4, 1.5_
    - _Status: Completed with proper error handling and logging_

- [x] 5. Create Dagster asset for company categorization
  - [x] 5.1 Implement main categorization asset
    - Create `enriched_sbir_companies_with_categorization` asset in `src/assets/`
    - Depend on `validated_sbir_awards` asset
    - Load configuration from `get_config()`
    - Initialize `DuckDBUSAspendingExtractor` with database path
    - Extract unique companies from validated SBIR awards
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
    - _Status: Completed in `src/assets/company_categorization.py`_

  - [x] 5.2 Implement batch processing loop
    - Iterate through companies in batches
    - Retrieve USAspending contracts for each company
    - Classify individual contracts using `classify_contract()`
    - Aggregate classifications using `aggregate_company_classification()`
    - Collect results into DataFrame
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.2, 5.3, 5.4, 5.5_
    - _Status: Completed with progress logging_

  - [x] 5.3 Implement output generation
    - Generate Product percentage for each company
    - Generate Service percentage for each company
    - Generate final classification label for each company
    - Generate confidence level for each company
    - Generate classification metadata (award count, PSC families, overrides)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
    - _Status: Completed with comprehensive metadata_

- [x] 6. Create asset check for categorization quality
  - [x] 6.1 Implement completeness check
    - Create `company_categorization_completeness_check` asset check
    - Calculate percentage of Uncertain classifications
    - Verify Uncertain percentage is <20%
    - Record classification distribution in metadata
    - Return AssetCheckResult with pass/fail status
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
    - _Status: Completed with comprehensive quality checks_

  - [x] 6.2 Implement confidence distribution check
    - Calculate distribution of confidence levels (Low/Medium/High)
    - Verify High confidence classifications are >50%
    - Record confidence distribution in metadata
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
    - _Status: Completed as separate asset check_

- [ ] 7. Add configuration schema
  - [ ] 7.1 Create configuration model
    - Add `CompanyCategorization` config schema to `src/config/schemas.py`
    - Define threshold parameters (product_leaning_pct: 51, service_leaning_pct: 51, psc_family_diversity: 6)
    - Define confidence level parameters (low_max_awards: 2, medium_max_awards: 5)
    - Define processing parameters (batch_size: 100, parallel_workers: 4)
    - Define USAspending query parameters (table_name, timeout, retries)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ] 7.2 Add default configuration
    - Add `company_categorization` section to `config/base.yaml`
    - Set default thresholds (51% for product/service, 6 for PSC families)
    - Set default confidence levels (2 for low, 5 for medium)
    - Set default processing parameters (batch_size: 100, parallel_workers: 4)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 8. Implement Neo4j loader
  - [ ] 8.1 Create CompanyCategorizationLoader class
    - Create `CompanyCategorizationLoader` in `src/loaders/neo4j/`
    - Implement `load_categorizations()` method for batch loading
    - Update existing Company nodes with categorization properties
    - Handle missing companies gracefully (log warnings)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 8.2 Implement Neo4j schema updates
    - Add categorization properties to Company nodes (classification, product_pct, service_pct, confidence)
    - Add metadata properties (award_count, psc_family_count, total_dollars, override_reason)
    - Add agency_breakdown as JSON property
    - Create indexes for classification and confidence fields
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 8.3 Test Neo4j loading asset
    - Verify `neo4j_company_categorization` asset loads successfully
    - Verify asset check validates load success rate (>95%)
    - Test with sample data before full dataset
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 9. Create integration tests
  - [ ]* 9.1 Create test fixtures
    - Create sample SBIR companies with UEI/DUNS/CAGE identifiers
    - Create sample USAspending contracts with varied PSC codes
    - Create sample contracts with different contract types and pricing
    - Create sample contracts with product-indicating descriptions
    - Create sample SBIR Phase I/II contracts
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 9.2 Test contract classification
    - Test numeric PSC → Product classification
    - Test alphabetic PSC → Service classification
    - Test PSC A/B → R&D classification
    - Test contract type overrides (CPFF, T&M → Service)
    - Test description inference (prototype, hardware, device → Product)
    - Test SBIR phase adjustment (Phase I/II → R&D)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 9.3 Test company aggregation
    - Test 51% Product threshold → Product-leaning
    - Test 51% Service threshold → Service-leaning
    - Test neither threshold → Mixed
    - Test <2 contracts → Uncertain
    - Test >6 PSC families → Mixed override
    - Test confidence level assignment (Low/Medium/High)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 9.4 Test USAspending retrieval
    - Test UEI query returns contracts
    - Test DUNS fallback when UEI fails
    - Test CAGE fallback when DUNS fails
    - Test empty result handling
    - Test SBIR phase detection
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 9.5 Test end-to-end pipeline
    - Test full categorization pipeline with sample data
    - Verify output DataFrame structure and completeness
    - Verify classification distribution is reasonable
    - Verify metadata is populated correctly
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 9.6 Validate against high-volume SBIR companies
    - Load companies from `data/raw/sbir/over-100-awards-2005-2025-company_search_1763156580.csv`
    - Run categorization on all 200+ companies with 100+ awards each
    - Verify categorization completes successfully for all companies
    - Analyze classification distribution (Product/Service/Mixed/Uncertain percentages)
    - Spot-check 10-20 companies manually to validate classification accuracy
    - Generate validation report with classification statistics
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 10. Add documentation
  - [ ]* 10.1 Create module docstrings
    - Document `company_categorization.py` module purpose and usage
    - Document `classify_contract()` function with examples
    - Document `aggregate_company_classification()` function with examples
    - Document `retrieve_company_contracts()` function with examples
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.2, 5.3, 5.4, 5.5_
    - _Note: Comprehensive docstrings already exist in implementation_

  - [ ]* 10.2 Create usage guide
    - Document how to run categorization asset in Dagster UI
    - Document configuration options and defaults
    - Document output format and interpretation
    - Document troubleshooting common issues
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 10.3 Update data dictionary
    - Add company categorization fields to data dictionary
    - Document classification values and meanings
    - Document confidence levels and thresholds
    - Document metadata fields
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

## Implementation Notes

### Remaining Work Summary

**Priority 1 (Required for Production):**
1. Configuration schema (Task 7) - Externalize hardcoded thresholds
2. Neo4j loader (Task 8) - Enable graph database integration
3. High-volume validation (Task 9.6) - Validate with real data

**Priority 2 (Quality Assurance):**
4. Integration tests (Task 9.1-9.5) - Comprehensive test coverage
5. Documentation (Task 10.2-10.3) - Usage guides and data dictionary

### Execution Order for Remaining Tasks

1. **Configuration (Task 7)** - Add schema and defaults to externalize thresholds
2. **Neo4j Loader (Task 8)** - Implement loader class and test loading
3. **High-Volume Validation (Task 9.6)** - Validate with 200+ companies
4. **Integration Tests (Task 9.1-9.5)** - Comprehensive test suite
5. **Documentation (Task 10.2-10.3)** - Usage guides and data dictionary

### Key Implementation Details

**Classification Logic:**
- Uses 51% threshold (not 60% as originally planned) for Product/Service-leaning
- R&D contracts are treated as Service for aggregation purposes
- Fixed Price contracts with numeric PSC or product keywords → Product
- Cost Reimbursement and Labor Hours contracts → Service
- SBIR/STTR awards are excluded from categorization to focus on non-R&D revenue

**Enrichment Strategy:**
- Primary: DuckDB query by UEI/DUNS/CAGE
- Fallback: API with fuzzy name matching via autocomplete
- Intelligent name normalization for better matching
- Caching to reduce API calls

**Data Quality:**
- Asset checks enforce <20% Uncertain classifications
- Asset checks verify >50% High confidence classifications
- Confidence levels based on award count (Low: <2, Medium: 2-5, High: >5)
- PSC family diversity override (>6 families → Mixed)

### Testing Strategy

- Unit tests for classification logic (already partially implemented in `tests/validation/`)
- Integration tests for end-to-end pipeline
- High-volume validation with 200+ real companies
- Mock USAspending queries in unit tests
- Use real DuckDB connection in integration tests

### Performance Considerations

- Process companies sequentially (no batching currently implemented)
- DuckDB queries are fast for local database
- API fallback with rate limiting and caching
- Progress logging every 10 companies
- Connection cleanup in finally blocks

### Quality Gates

- Asset check: <20% Uncertain classifications
- Asset check: >50% High confidence classifications
- Neo4j load success rate: >95%
- All required fields present and non-null
- Confidence levels align with award counts

## Completion Criteria

The implementation is complete when:

1. All tasks are marked as complete
2. All tests pass (unit and integration)
3. Asset check passes with quality thresholds met
4. Documentation is complete and reviewed
5. Code is merged to main branch
6. Feature is deployed and validated in production

## Related Documents

- Requirements: `.kiro/specs/company-categorization/requirements.md`
- Design: `.kiro/specs/company-categorization/design.md`
- Pipeline Orchestration: `.kiro/steering/pipeline-orchestration.md`
- Configuration Patterns: `.kiro/steering/configuration-patterns.md`
