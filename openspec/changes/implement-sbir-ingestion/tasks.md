# Implementation Tasks

## 1. Data Model Enhancement
- [ ] 1.1 Review SBIR data dictionary (docs/data-dictionaries/sbir_awards_data_dictionary.xlsx)
- [ ] 1.2 Analyze CSV structure and data types (42 columns, 533K records)
- [ ] 1.3 Update src/models/award.py with complete SbirAward model
  - [ ] 1.3.1 Company identification fields (Company, UEI, DUNS, Address1-2, City, State, Zip)
  - [ ] 1.3.2 Award details (Title, Abstract, Agency, Branch, Phase, Program)
  - [ ] 1.3.3 Financial fields (Award Amount, Award Year)
  - [ ] 1.3.4 Timeline fields (Proposal Award Date, Contract End Date, Solicitation dates)
  - [ ] 1.3.5 Tracking fields (Agency Tracking Number, Contract, Solicitation Number)
  - [ ] 1.3.6 Personnel fields (Contact Name/Title/Phone/Email, PI, RI)
  - [ ] 1.3.7 Business classification (HUBZone, Woman Owned, Socially/Economically Disadvantaged)
  - [ ] 1.3.8 Company metadata (Number Employees, Company Website)
- [x] 1.4 Add Pydantic validators for data type conversions and optional fields
- [ ] 1.5 Write unit tests for SbirAward model (tests/unit/test_sbir_award_model.py)

## 2. DuckDB-Based CSV Extractor Implementation
- [x] 2.1 Create src/extractors/sbir.py
- [x] 2.2 Implement SbirDuckDBExtractor class
  - [x] 2.2.1 Initialize DuckDB client (use existing src/utils/duckdb_client.py)
  - [x] 2.2.2 Import CSV to DuckDB table using duckdb_client.import_csv()
  - [x] 2.2.3 Verify import with table_exists() and get_table_info()
  - [x] 2.2.4 Implement query methods for filtered extraction
    - [x] extract_all() - Returns full dataset as DataFrame
    - [x] extract_by_year(year_start, year_end) - Filter by Award Year
    - [x] extract_by_agency(agencies) - Filter by Agency
    - [x] extract_by_phase(phases) - Filter by Phase
  - [x] 2.2.5 Implement chunked processing via fetch_df_chunk(batch_size)
  - [ ] 2.2.6 Column name mapping (handle quoted column names in SQL)
- [x] 2.3 Add extraction metadata tracking
  - [x] 2.3.1 File size and record count from DuckDB table stats
  - [x] 2.3.2 Extraction timestamp
  - [x] 2.3.3 Column validation (ensure all 42 expected columns present)
  - [x] 2.3.4 DuckDB table statistics (row count, memory usage)
- [x] 2.4 Implement SQL-based data quality checks
  - [x] 2.4.1 Count null values per column (SELECT COUNT(*) WHERE col IS NULL)
  - [x] 2.4.2 Identify duplicate Contract IDs with phase breakdown
  - [x] 2.4.3 Award amount statistics (min, max, avg, median)
- [x] 2.5 Implement error handling and logging
  - [x] 2.5.1 File not found errors
  - [x] 2.5.2 DuckDB import errors
  - [x] 2.5.3 SQL query errors
  - [x] 2.5.4 Progress logging for import and queries
- [ ] 2.6 Write unit tests for SbirDuckDBExtractor (tests/unit/test_sbir_extractor.py)
  - [ ] 2.6.1 Test CSV import to DuckDB
  - [ ] 2.6.2 Test filtered extraction queries
  - [ ] 2.6.3 Test chunked processing
  - [ ] 2.6.4 Test metadata collection

## 3. SBIR-Specific Validation Rules
- [x] 3.1 Create src/validators/sbir_awards.py module
- [x] 3.2 Implement required field validation
  - [x] 3.2.1 Company name (non-empty string)
  - [x] 3.2.2 Award Title (non-empty string)
  - [x] 3.2.3 Agency (non-empty string)
  - [x] 3.2.4 Phase (enum: "Phase I", "Phase II", "Phase III")
  - [x] 3.2.5 Program (enum: "SBIR", "STTR")
  - [x] 3.2.6 Award Year (integer, range 1983-2026)
  - [x] 3.2.7 Award Amount (float, range $1 - $10,000,000)
- [x] 3.3 Implement format validation
  - [x] 3.3.1 UEI format (12 alphanumeric if present)
  - [x] 3.3.2 DUNS format (9 digits if present)
  - [x] 3.3.3 Email format (Contact Email, PI Email)
  - [ ] 3.3.4 Phone number format
  - [x] 3.3.5 State code (2-letter US state codes)
  - [x] 3.3.6 ZIP code (5 or 9 digits)
- [x] 3.4 Implement business logic validation
  - [x] 3.4.1 Date consistency (Proposal Award Date ≤ Contract End Date)
  - [ ] 3.4.2 Award Year matches Proposal Award Date year
  - [ ] 3.4.3 Phase consistency with Program (SBIR/STTR)
- [x] 3.5 Implement validate_sbir_awards function
  - [x] 3.5.1 Batch validation for DataFrame
  - [x] 3.5.2 Generate QualityReport with issues and metrics
  - [x] 3.5.3 Configurable thresholds (completeness, pass rate)
- [ ] 3.6 Write unit tests for validation rules (tests/unit/test_sbir_validators.py)

## 4. Dagster SBIR Ingestion Assets
- [x] 4.1 Create src/assets/sbir_ingestion.py module
- [x] 4.2 Implement raw_sbir_awards asset
  - [x] 4.2.1 Initialize SbirDuckDBExtractor
  - [x] 4.2.2 Import CSV to DuckDB (log import time and row count)
  - [x] 4.2.3 Call extract_all() or filtered extraction if configured
  - [x] 4.2.4 Log extraction metadata (DuckDB stats, memory usage)
  - [x] 4.2.5 Return pandas DataFrame
  - [x] 4.2.6 Add asset description and group ("sbir_ingestion")
- [x] 4.3 Implement validated_sbir_awards asset
  - [x] 4.3.1 Depend on raw_sbir_awards
  - [x] 4.3.2 Call validate_sbir_awards
  - [x] 4.3.3 Filter to passing records
  - [x] 4.3.4 Log validation results
  - [x] 4.3.5 Return validated DataFrame
- [x] 4.4 Implement sbir_validation_report asset
  - [x] 4.4.1 Depend on raw_sbir_awards
  - [x] 4.4.2 Generate QualityReport
  - [x] 4.4.3 Write report to data/validated/sbir_validation_report.json
  - [x] 4.4.4 Return QualityReport object
- [x] 4.5 Implement sbir_data_quality_check asset check
  - [x] 4.5.1 Check validation pass rate ≥ 95%
  - [x] 4.5.2 Fail asset if threshold not met
  - [x] 4.5.3 Include quality metrics in check result
- [x] 4.6 Update src/definitions.py to include sbir_ingestion assets
- [ ] 4.7 Write integration tests (tests/integration/test_sbir_ingestion_assets.py)

## 5. Configuration Updates
- [x] 5.1 Update config/base.yaml
  - [x] 5.1.1 Add sbir_csv section with file path (data/raw/sbir/awards_data.csv)
  - [x] 5.1.2 Add DuckDB configuration
    - [x] database_path: ":memory:" (or path to persistent .duckdb file)
    - [x] table_name: "sbir_awards"
  - [x] 5.1.3 Add chunked processing config (batch_size: 10000)
  - [x] 5.1.4 Add SBIR-specific validation thresholds
    - [x] pass_rate_threshold: 0.95 (95% of records must pass validation)
    - [x] completeness_threshold (for individual fields)
    - [x] uniqueness_threshold (for duplicate detection)
- [ ] 5.2 Update config/dev.yaml if needed for local testing
  - [ ] 5.2.1 Optional: Use persistent DuckDB file for faster dev iterations
- [x] 5.3 Update src/config/schemas.py
  - [x] 5.3.1 Add SbirDuckDBConfig model with csv_path, duckdb_path, table_name, batch_size
  - [x] 5.3.2 Add SbirValidationConfig to DataQualityConfig with pass_rate_threshold
- [ ] 5.4 Write unit tests for config schemas (tests/unit/test_sbir_config.py)

## 6. Sample Data and Fixtures
- [ ] 6.1 Create sample SBIR CSV for testing (tests/fixtures/sbir_sample.csv)
  - [ ] 6.1.1 Include 100 representative records
  - [ ] 6.1.2 Include edge cases (missing UEI, old awards, max amounts)
  - [ ] 6.1.3 Include invalid records for validation testing
- [ ] 6.2 Document sample data structure in tests/fixtures/README.md

## 7. Documentation
- [ ] 7.1 Add SBIR ingestion section to README.md
  - [ ] 7.1.1 Data source description
  - [ ] 7.1.2 CSV structure and field counts
  - [ ] 7.1.3 Usage instructions
- [ ] 7.2 Create docs/sbir_ingestion.md with detailed documentation
  - [ ] 7.2.1 Field descriptions from data dictionary
  - [ ] 7.2.2 Validation rules reference
  - [ ] 7.2.3 Example queries and usage
- [x] 7.3 Add inline docstrings to all new modules
- [ ] 7.4 Update CONTRIBUTING.md if needed

## 8. Testing and Validation
- [ ] 8.1 Run unit tests for all new modules
  - [ ] 8.1.1 SbirAward model tests
  - [ ] 8.1.2 SbirCsvExtractor tests
  - [ ] 8.1.3 SBIR validator tests
  - [ ] 8.1.4 Config schema tests
- [ ] 8.2 Run integration tests
  - [ ] 8.2.1 Dagster asset tests with sample data
  - [ ] 8.2.2 End-to-end pipeline test (CSV → validated DataFrame)
- [ ] 8.3 Test with full dataset (533K records)
  - [ ] 8.3.1 Verify memory usage with chunked processing
  - [ ] 8.3.2 Measure execution time
  - [ ] 8.3.3 Verify validation metrics
- [ ] 8.4 Run code quality checks
  - [ ] 8.4.1 Black formatting
  - [ ] 8.4.2 Ruff linting
  - [ ] 8.4.3 MyPy type checking
- [ ] 8.5 Test Dagster UI
  - [ ] 8.5.1 Launch Dagster UI (dagster dev)
  - [ ] 8.5.2 Materialize raw_sbir_awards asset
  - [ ] 8.5.3 Materialize validated_sbir_awards asset
  - [ ] 8.5.4 Review validation report and quality check results
  - [ ] 8.5.5 Verify asset lineage graph

## 9. Performance Optimization
- [ ] 9.1 Profile CSV extraction with full dataset
- [ ] 9.2 Optimize chunked processing batch size
- [ ] 9.3 Profile validation performance
- [ ] 9.4 Add progress bars for long-running operations
- [ ] 9.5 Document performance benchmarks

## 10. Final Validation
- [ ] 10.1 Verify all tasks completed
- [ ] 10.2 Run full test suite with ≥85% coverage
- [ ] 10.3 Validate with openspec validate --strict
- [ ] 10.4 Review proposal.md and tasks.md for completeness
- [ ] 10.5 Create summary of implementation for documentation
