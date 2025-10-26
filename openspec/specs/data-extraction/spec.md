# data-extraction Specification

## Purpose
TBD - created by archiving change add-initial-architecture. Update Purpose after archive.
## Requirements
### Requirement: Multi-Source Data Extraction
The system SHALL support extracting data from multiple sources including CSV files, APIs, and database exports.

#### Scenario: CSV file extraction
- **WHEN** a CSV file path is provided
- **THEN** the system SHALL download or read the file
- **AND** the file SHALL be parsed into a structured format (e.g., pandas DataFrame)

#### Scenario: File download with retry
- **WHEN** a remote file download fails
- **THEN** the system SHALL retry with exponential backoff
- **AND** after max retries, the extraction SHALL fail with a clear error message

### Requirement: Raw Data Storage
The system SHALL store extracted raw data in a designated directory for reproducibility and debugging.

#### Scenario: Raw data persistence
- **WHEN** data is extracted
- **THEN** it SHALL be written to `data/raw/` directory
- **AND** the filename SHALL include a timestamp or source identifier
- **AND** the raw data SHALL be preserved for the duration of the pipeline run

### Requirement: Extraction Metadata
The system SHALL capture and log metadata about extraction including record count, source, and timestamp.

#### Scenario: Extraction logging
- **WHEN** extraction completes
- **THEN** the system SHALL log the source name, record count, and extraction timestamp
- **AND** any errors or warnings SHALL be logged with context

### Requirement: Chunked Processing Support
The system SHALL support chunked processing for large files that exceed memory limits.

#### Scenario: Large file chunked extraction
- **WHEN** a file exceeds a configured size threshold
- **THEN** the system SHALL process the file in chunks
- **AND** each chunk SHALL be validated and processed independently
- **AND** memory usage SHALL remain within acceptable limits

### Requirement: SBIR CSV Data Extraction with DuckDB
The system SHALL extract SBIR award data from CSV files using DuckDB for efficient columnar storage and SQL-based querying, following the SBIR.gov format with 42 columns and support for 500K+ records.

#### Scenario: SBIR CSV import to DuckDB
- **GIVEN** a CSV file at `data/raw/sbir/awards_data.csv`
- **WHEN** the SBIR extractor is invoked
- **THEN** the system SHALL import the CSV into a DuckDB table using DuckDBClient.import_csv()
- **AND** the import SHALL complete in < 5 seconds for 533K records
- **AND** the system SHALL verify all 42 columns are present
- **AND** the DuckDB table SHALL be named "sbir_awards"
- **AND** extraction metadata SHALL include import duration and row count

#### Scenario: Query-based extraction from DuckDB
- **GIVEN** SBIR CSV data imported to DuckDB table
- **WHEN** extract_all() is called
- **THEN** the system SHALL execute "SELECT * FROM sbir_awards"
- **AND** the system SHALL return a pandas DataFrame with all records
- **AND** memory usage SHALL be ~60% lower than direct CSV read (due to columnar storage)

#### Scenario: CSV column validation
- **GIVEN** a SBIR CSV file
- **WHEN** the file is opened
- **THEN** the system SHALL verify all 42 expected columns are present
- **AND** if columns are missing, the system SHALL fail with a clear error message listing missing columns
- **AND** if extra columns are present, the system SHALL log a warning but continue processing

#### Scenario: Data type conversion
- **GIVEN** raw CSV string data
- **WHEN** records are parsed
- **THEN** date fields (Proposal Award Date, Contract End Date, Solicitation dates) SHALL be parsed to datetime objects
- **AND** Award Amount SHALL be parsed to float
- **AND** Award Year and Solicitation Year SHALL be parsed to integers
- **AND** boolean fields (HUBZone Owned, Woman Owned, etc.) SHALL be parsed to boolean or None
- **AND** parsing errors SHALL be logged with row number and field name

#### Scenario: Missing value handling
- **GIVEN** CSV records with empty fields
- **WHEN** the extractor processes the data
- **THEN** empty strings SHALL be converted to None for optional fields
- **AND** required fields with empty values SHALL be flagged in extraction metadata
- **AND** the record SHALL still be extracted for downstream validation

#### Scenario: Filtered extraction with SQL
- **GIVEN** SBIR data imported to DuckDB
- **WHEN** extract_by_year(2020, 2025) is called
- **THEN** the system SHALL execute SQL: "SELECT * FROM sbir_awards WHERE \"Award Year\" BETWEEN 2020 AND 2025"
- **AND** only matching records SHALL be loaded into pandas
- **AND** extraction SHALL be faster than loading full dataset then filtering

#### Scenario: Large file chunked processing with DuckDB
- **GIVEN** DuckDB table with 533,598 records
- **WHEN** the extractor is configured with batch_size=10000
- **THEN** the system SHALL use fetch_df_chunk(10000) to iterate
- **AND** each chunk SHALL be yielded as a pandas DataFrame
- **AND** extraction SHALL log progress every chunk
- **AND** total memory usage SHALL remain under 1GB (vs 2GB with direct CSV read)

### Requirement: SBIR Data Model
The system SHALL provide a Pydantic model representing SBIR award structure with comprehensive field validation.

#### Scenario: SbirAward model instantiation
- **GIVEN** a dictionary of SBIR award data
- **WHEN** SbirAward.model_validate(data) is called
- **THEN** the model SHALL validate required fields (Company, Award Title, Agency, Phase, Program, Award Year, Award Amount)
- **AND** the model SHALL allow optional fields to be None
- **AND** validation errors SHALL include field names and constraints

#### Scenario: Field groups in model
- **GIVEN** an SbirAward model instance
- **THEN** it SHALL have company identification fields: company, uei, duns, address1, address2, city, state, zip, company_website, number_employees
- **AND** it SHALL have award details: award_title, abstract, agency, branch, phase, program, topic_code
- **AND** it SHALL have financial fields: award_amount, award_year
- **AND** it SHALL have timeline fields: proposal_award_date, contract_end_date, solicitation_close_date, proposal_receipt_date, date_of_notification
- **AND** it SHALL have tracking fields: agency_tracking_number, contract, solicitation_number, solicitation_year
- **AND** it SHALL have personnel fields: contact_name, contact_title, contact_phone, contact_email, pi_name, pi_title, pi_phone, pi_email, ri_name, ri_poc_name, ri_poc_phone
- **AND** it SHALL have business classification fields: hubzone_owned, socially_economically_disadvantaged, woman_owned

### Requirement: DuckDB-Based Data Quality Analysis
The system SHALL provide SQL-based data quality analysis capabilities using DuckDB for fast aggregations and pattern detection.

#### Scenario: Null value analysis
- **GIVEN** SBIR data in DuckDB
- **WHEN** analyze_missing_values() is called
- **THEN** the system SHALL execute SQL to count nulls per column
- **AND** results SHALL show columns with >10% null values
- **AND** analysis SHALL complete in < 1 second

#### Scenario: Duplicate detection with SQL
- **GIVEN** SBIR data in DuckDB
- **WHEN** analyze_duplicates() is called
- **THEN** the system SHALL execute: "SELECT Contract, COUNT(*) as count FROM sbir_awards GROUP BY Contract HAVING COUNT(*) > 1"
- **AND** results SHALL show Contract IDs with multiple records
- **AND** results SHALL include phase breakdown for each duplicate

#### Scenario: Award amount statistics
- **GIVEN** SBIR data in DuckDB
- **WHEN** analyze_award_amounts() is called
- **THEN** the system SHALL compute min, max, avg, median, percentiles using SQL
- **AND** statistics SHALL be grouped by Phase and Agency
- **AND** analysis SHALL complete in < 1 second for 533K records

### Requirement: Extraction Metadata for SBIR
The system SHALL capture detailed metadata about SBIR CSV extraction and DuckDB import for observability and quality tracking.

#### Scenario: SBIR extraction metadata with DuckDB stats
- **WHEN** SBIR CSV extraction completes
- **THEN** metadata SHALL include source file path
- **AND** metadata SHALL include file size in bytes
- **AND** metadata SHALL include total record count from DuckDB table
- **AND** metadata SHALL include column count and column names (42 columns)
- **AND** metadata SHALL include CSV import duration
- **AND** metadata SHALL include DuckDB table name
- **AND** metadata SHALL include DuckDB memory usage
- **AND** metadata SHALL include extraction start and end timestamps
- **AND** metadata SHALL include any warnings (missing columns, import errors)

#### Scenario: Column mapping documentation
- **GIVEN** SBIR CSV extraction
- **THEN** the extractor SHALL document the mapping between CSV column names and model field names
- **AND** this mapping SHALL be logged at INFO level on first extraction
- **AND** the mapping SHALL handle column name variations (quotes, spaces, case differences)

### Requirement: SBIR-Specific Validation
The system SHALL validate SBIR award data against business rules and data quality constraints.

#### Scenario: Required field validation
- **GIVEN** an extracted SBIR award
- **WHEN** validation is performed
- **THEN** Company SHALL be non-empty string
- **AND** Award Title SHALL be non-empty string
- **AND** Agency SHALL be non-empty string
- **AND** Phase SHALL be one of: "Phase I", "Phase II", "Phase III"
- **AND** Program SHALL be one of: "SBIR", "STTR"
- **AND** Award Year SHALL be integer between 1983 and 2026
- **AND** Award Amount SHALL be float between $1 and $10,000,000
- **AND** missing required fields SHALL generate QualityIssue with severity ERROR

#### Scenario: Format validation
- **GIVEN** an extracted SBIR award with optional identification fields
- **WHEN** format validation is performed
- **THEN** if UEI is present, it SHALL be 12 alphanumeric characters
- **AND** if DUNS is present, it SHALL be 9 digits
- **AND** if Contact Email is present, it SHALL match email format regex
- **AND** if PI Email is present, it SHALL match email format regex
- **AND** if State is present, it SHALL be valid 2-letter US state code
- **AND** if Zip is present, it SHALL be 5 digits or 9 digits (ZIP+4 format)
- **AND** format violations SHALL generate QualityIssue with severity WARNING

#### Scenario: Business logic validation
- **GIVEN** an SBIR award with date fields
- **WHEN** business logic validation is performed
- **THEN** if both Proposal Award Date and Contract End Date are present, Award Date SHALL be ≤ End Date
- **AND** if Award Year and Proposal Award Date are present, the year SHALL match
- **AND** logic violations SHALL generate QualityIssue with severity WARNING

#### Scenario: Validation summary report
- **GIVEN** a batch of 533,598 SBIR awards
- **WHEN** validation completes
- **THEN** a QualityReport SHALL be generated
- **AND** the report SHALL include total records processed
- **AND** the report SHALL include count of passing records
- **AND** the report SHALL include count of failing records
- **AND** the report SHALL include pass rate percentage
- **AND** the report SHALL include breakdown of issues by severity (ERROR, WARNING, INFO)
- **AND** the report SHALL include breakdown of issues by field name
- **AND** the report SHALL be written to data/validated/sbir_validation_report.json

### Requirement: Dagster SBIR Ingestion Assets
The system SHALL provide Dagster assets for orchestrating SBIR data extraction and validation.

#### Scenario: raw_sbir_awards asset
- **WHEN** raw_sbir_awards asset is materialized
- **THEN** it SHALL call SbirCsvExtractor with configured CSV path
- **AND** it SHALL log extraction metadata (record count, duration)
- **AND** it SHALL return pandas DataFrame with all raw records
- **AND** it SHALL be in asset group "sbir_ingestion"

#### Scenario: validated_sbir_awards asset
- **GIVEN** raw_sbir_awards asset is materialized
- **WHEN** validated_sbir_awards asset is materialized
- **THEN** it SHALL depend on raw_sbir_awards
- **AND** it SHALL call validate_sbir_awards with raw data
- **AND** it SHALL filter to only passing records
- **AND** it SHALL log validation summary (pass count, fail count, pass rate)
- **AND** it SHALL return DataFrame with validated records only

#### Scenario: sbir_validation_report asset
- **GIVEN** raw_sbir_awards asset is materialized
- **WHEN** sbir_validation_report asset is materialized
- **THEN** it SHALL depend on raw_sbir_awards
- **AND** it SHALL generate QualityReport
- **AND** it SHALL write report to data/validated/sbir_validation_report.json
- **AND** it SHALL return QualityReport object

#### Scenario: sbir_data_quality_check asset check
- **GIVEN** validated_sbir_awards asset is materialized
- **AND** pass_rate_threshold is configured in config/base.yaml (default: 0.95)
- **WHEN** the asset check runs
- **THEN** it SHALL read the threshold from data_quality.sbir_awards.pass_rate_threshold
- **AND** it SHALL verify validation pass rate ≥ threshold
- **AND** if pass rate < threshold, the check SHALL fail with descriptive message
- **AND** the check result SHALL include actual pass rate, configured threshold, and record counts in metadata
- **AND** the check SHALL prevent downstream assets from running if failed

### Requirement: Offline USAspending Dump Profiling
The system SHALL support staging and profiling the compressed USAspending Postgres subset directly from the removable media before it is ingested into DuckDB/Postgres.

#### Scenario: Stage removable-drive snapshot
- **WHEN** the "X10 Pro" drive containing `usaspending-db-subset_20251006.zip` is mounted at `/Volumes/X10 Pro`
- **THEN** the operator validates the archive **in place** (no local copy), recording size, SHA256 checksum, snapshot date, and canonical path in `reports/usaspending_subset_profile.md`
- **AND** the staging step fails with an actionable error if the drive is missing, read-only, or the checksum check fails.

#### Scenario: Profile dump without full restore
- **WHEN** the mounted archive is available at `/Volumes/X10 Pro/usaspending-db-subset_20251006.zip`
- **THEN** running `poetry run profile_usaspending_dump --input /Volumes/X10\ Pro/usaspending-db-subset_20251006.zip`
- **AND** the command streams the archive through `pg_restore --list` or DuckDB `postgres_scanner`
- **AND** outputs machine-readable table metadata (table name, row count estimate, primary key fields, key columns) plus a Markdown summary saved to `reports/usaspending_subset_profile.md`.

### Requirement: USAspending Snapshot Availability Gate
The system SHALL verify that a profiled USAspending snapshot is available before any ETL asset that depends on USAspending data executes.

#### Scenario: Gate enrichment asset on profiling metadata
- **WHEN** Dagster materializes an asset that needs USAspending data (e.g., `usaspending_awards_raw`)
- **THEN** it checks for a fresh profiling artifact (<30 days old) with the expected filename `usaspending-db-subset_20251006.zip` and path reference `/Volumes/X10 Pro/...`
- **AND** if the artifact is missing, stale, or references a different checksum, the asset fails fast with guidance to rerun the profiling command after staging the removable-drive snapshot.

