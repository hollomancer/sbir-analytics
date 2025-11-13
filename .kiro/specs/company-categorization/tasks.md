# Implementation Plan

## Task Overview

This implementation plan breaks down the company categorization feature into discrete, incremental coding tasks. Each task builds on previous work and integrates code into the existing SBIR analytics pipeline. The plan follows the five-stage ETL pattern (Extract → Validate → Enrich → Transform → Load) and integrates with Dagster asset orchestration.

## Implementation Tasks

- [ ] 1. Create data models for contract and company classifications
  - Create `ContractClassification` Pydantic model in `src/models/`
  - Create `CompanyClassification` Pydantic model in `src/models/`
  - Add field validators for classification values and confidence scores
  - Add model serialization methods for DataFrame conversion
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 2. Implement contract classifier module
  - [ ] 2.1 Create `src/transformers/company_categorization.py` module
    - Implement `classify_contract()` function with PSC-based rules
    - Implement contract type override logic (CPFF, Cost-Type, T&M → Service)
    - Implement description inference logic (prototype, hardware, device → Product)
    - Implement SBIR phase adjustment logic (Phase I/II → R&D)
    - Return classification with method and confidence metadata
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ] 2.2 Implement PSC classification rules
    - Add logic for numeric PSC → Product classification
    - Add logic for alphabetic PSC → Service classification
    - Add logic for PSC codes starting with A/B → R&D classification
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 2.3 Implement contract type and pricing rules
    - Add CPFF contract type → Service override
    - Add Cost-Type contract type → Service override
    - Add T&M pricing → Service override
    - Add FFP pricing → retain PSC classification
    - _Requirements: 2.4, 2.5_

  - [ ] 2.4 Implement description-based inference
    - Add keyword detection for "prototype" → Product
    - Add keyword detection for "hardware" → Product
    - Add keyword detection for "device" → Product
    - Record inference method in classification metadata
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 2.5 Implement SBIR phase adjustment
    - Add Phase I classification → R&D (unless numeric PSC)
    - Add Phase II classification → R&D (unless numeric PSC)
    - Add Phase I/II with numeric PSC → Product
    - Add R&D classification → treat as Service for aggregation
    - Add Phase III → apply standard rules without adjustment
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 3. Implement company aggregator module
  - [ ] 3.1 Create company aggregation function
    - Implement `aggregate_company_classification()` function
    - Calculate dollar-weighted Product percentage
    - Calculate dollar-weighted Service+R&D percentage
    - Apply 60% threshold for Product-leaning classification
    - Apply 60% threshold for Service-leaning classification
    - Apply Mixed classification for neither threshold met
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 3.2 Implement confidence level assignment
    - Assign Low confidence for <2 awards
    - Assign Medium confidence for 2-5 awards
    - Assign High confidence for >5 awards
    - Record award count in classification metadata
    - Classify companies with <2 awards as Uncertain
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ] 3.3 Implement override rules
    - Detect companies with >6 PSC families → classify as Mixed
    - Record PSC family count in classification metadata
    - Preserve original calculated classification in metadata
    - Record all applicable override reasons
    - Skip other overrides for Uncertain companies
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 4. Implement USAspending contract retrieval
  - [ ] 4.1 Create contract retrieval function
    - Implement `retrieve_company_contracts()` function in `src/enrichers/company_categorization.py`
    - Query USAspending by UEI using existing `DuckDBUSAspendingExtractor`
    - Query USAspending by DUNS if UEI query returns no results
    - Query USAspending by CAGE if DUNS query returns no results
    - Extract required fields: PSC, contract_type, pricing, description, award_amount
    - _Requirements: 1.1, 1.2_

  - [ ] 4.2 Implement SBIR phase detection
    - Identify SBIR awards in USAspending results
    - Extract SBIR phase from award description or metadata
    - Record SBIR phase in contract record
    - _Requirements: 1.3_

  - [ ] 4.3 Handle empty results
    - Return empty DataFrame for companies with no USAspending contracts
    - Log warning for companies with no contracts found
    - Classify companies with no contracts as Uncertain
    - _Requirements: 1.4, 1.5_

- [ ] 5. Create Dagster asset for company categorization
  - [ ] 5.1 Implement main categorization asset
    - Create `enriched_sbir_companies_with_categorization` asset in `src/assets/`
    - Depend on `validated_sbir_awards` asset
    - Load configuration from `get_config()`
    - Initialize `DuckDBUSAspendingExtractor` with database path
    - Extract unique companies from validated SBIR awards
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ] 5.2 Implement batch processing loop
    - Iterate through companies in batches
    - Retrieve USAspending contracts for each company
    - Classify individual contracts using `classify_contract()`
    - Aggregate classifications using `aggregate_company_classification()`
    - Collect results into DataFrame
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 5.3 Implement output generation
    - Generate Product percentage for each company
    - Generate Service percentage for each company
    - Generate final classification label for each company
    - Generate confidence level for each company
    - Generate classification metadata (award count, PSC families, overrides)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 6. Create asset check for categorization quality
  - [ ] 6.1 Implement completeness check
    - Create `company_categorization_completeness_check` asset check
    - Calculate percentage of Uncertain classifications
    - Verify Uncertain percentage is <20%
    - Record classification distribution in metadata
    - Return AssetCheckResult with pass/fail status
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 6.2 Implement confidence distribution check
    - Calculate distribution of confidence levels (Low/Medium/High)
    - Verify High confidence classifications are >50%
    - Record confidence distribution in metadata
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 7. Add configuration schema
  - [ ] 7.1 Create configuration model
    - Add `CompanyCategorization` config schema to `src/config/schemas.py`
    - Define threshold parameters (product_leaning_pct, service_leaning_pct, psc_family_diversity)
    - Define confidence level parameters (low_max_awards, medium_max_awards)
    - Define processing parameters (batch_size, parallel_workers)
    - Define USAspending query parameters (table_name, timeout, retries)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ] 7.2 Add default configuration
    - Add `company_categorization` section to `config/base.yaml`
    - Set default thresholds (60% for product/service, 6 for PSC families)
    - Set default confidence levels (2 for low, 5 for medium)
    - Set default processing parameters (batch_size: 100, parallel_workers: 4)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 8. Create integration tests
  - [ ]* 8.1 Create test fixtures
    - Create sample SBIR companies with UEI/DUNS/CAGE identifiers
    - Create sample USAspending contracts with varied PSC codes
    - Create sample contracts with different contract types and pricing
    - Create sample contracts with product-indicating descriptions
    - Create sample SBIR Phase I/II contracts
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 8.2 Test contract classification
    - Test numeric PSC → Product classification
    - Test alphabetic PSC → Service classification
    - Test PSC A/B → R&D classification
    - Test contract type overrides (CPFF, T&M → Service)
    - Test description inference (prototype, hardware, device → Product)
    - Test SBIR phase adjustment (Phase I/II → R&D)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 8.3 Test company aggregation
    - Test 60% Product threshold → Product-leaning
    - Test 60% Service threshold → Service-leaning
    - Test neither threshold → Mixed
    - Test <2 contracts → Uncertain
    - Test >6 PSC families → Mixed override
    - Test confidence level assignment (Low/Medium/High)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 8.4 Test USAspending retrieval
    - Test UEI query returns contracts
    - Test DUNS fallback when UEI fails
    - Test CAGE fallback when DUNS fails
    - Test empty result handling
    - Test SBIR phase detection
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 8.5 Test end-to-end pipeline
    - Test full categorization pipeline with sample data
    - Verify output DataFrame structure and completeness
    - Verify classification distribution is reasonable
    - Verify metadata is populated correctly
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 9. Add documentation
  - [ ]* 9.1 Create module docstrings
    - Document `company_categorization.py` module purpose and usage
    - Document `classify_contract()` function with examples
    - Document `aggregate_company_classification()` function with examples
    - Document `retrieve_company_contracts()` function with examples
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 9.2 Create usage guide
    - Document how to run categorization asset in Dagster UI
    - Document configuration options and defaults
    - Document output format and interpretation
    - Document troubleshooting common issues
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 9.3 Update data dictionary
    - Add company categorization fields to data dictionary
    - Document classification values and meanings
    - Document confidence levels and thresholds
    - Document metadata fields
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

## Implementation Notes

### Execution Order

1. Start with data models (Task 1) - establishes type contracts
2. Implement contract classifier (Task 2) - core classification logic
3. Implement company aggregator (Task 3) - portfolio-level logic
4. Implement USAspending retrieval (Task 4) - data access layer
5. Create Dagster asset (Task 5) - orchestration integration
6. Add asset checks (Task 6) - quality validation
7. Add configuration (Task 7) - parameterization
8. Create tests (Task 8) - validation
9. Add documentation (Task 9) - knowledge transfer

### Dependencies

- Task 2 depends on Task 1 (models)
- Task 3 depends on Task 1 (models)
- Task 4 depends on existing `DuckDBUSAspendingExtractor`
- Task 5 depends on Tasks 2, 3, 4 (all components)
- Task 6 depends on Task 5 (asset)
- Task 7 can be done in parallel with Tasks 2-4
- Task 8 depends on Tasks 1-7 (all implementation)
- Task 9 depends on Tasks 1-8 (complete implementation)

### Testing Strategy

- Write unit tests for each function as it's implemented
- Create integration tests after all components are complete
- Use pytest fixtures for sample data
- Mock USAspending queries in unit tests
- Use real DuckDB connection in integration tests

### Performance Considerations

- Process companies in batches of 100 to manage memory
- Use connection pooling for DuckDB queries
- Cache USAspending extractor instance
- Consider parallel processing for large datasets
- Monitor query performance and optimize as needed

### Quality Gates

- All unit tests must pass before integration testing
- Code coverage must be ≥80% for new modules
- Asset check must pass with <20% Uncertain classifications
- Classification distribution should be reasonable (no single category >80%)
- Processing time should be <4 hours for full SBIR dataset

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
