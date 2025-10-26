# Data Extraction - USPTO Patent Assignment Delta

## ADDED Requirements

### Requirement: USPTO Stata File Extraction

The system SHALL extract patent assignment data from USPTO Stata binary format (.dta) files with support for chunked streaming to manage memory usage for large datasets.

#### Scenario: Extract assignment records in chunks

- **WHEN** extracting assignment.dta (744MB, ~8M records)
- **THEN** the system reads the file in chunks of 10,000 records
- **AND** each chunk is yielded as a pandas DataFrame
- **AND** memory usage does not exceed 500MB during extraction
- **AND** extraction progress is logged with record counts and throughput metrics

#### Scenario: Handle multiple Stata format versions

- **WHEN** extracting files with different Stata format versions (Release 117 vs 118)
- **THEN** pandas automatically detects and parses the format correctly
- **AND** extraction succeeds for all provided USPTO files

#### Scenario: Extract all five core tables

- **WHEN** extracting the full USPTO dataset
- **THEN** the system extracts assignment.dta, assignee.dta, assignor.dta, documentid.dta, and assignment_conveyance.dta
- **AND** each table is extracted with all original columns preserved
- **AND** data types are correctly inferred (strings, dates, integers)

#### Scenario: Handle corrupt or incomplete files

- **WHEN** a Stata file is corrupt or truncated
- **THEN** the extractor logs a detailed error with the file path and byte offset
- **AND** extraction continues for remaining files
- **AND** the failed file is reported in the extraction summary

### Requirement: USPTO Data Validation

The system SHALL validate extracted USPTO data for schema compliance, referential integrity, and data quality thresholds before proceeding to transformation.

#### Scenario: Validate rf_id as primary key

- **WHEN** validating the assignment table
- **THEN** the system checks that rf_id is unique (no duplicates)
- **AND** rf_id is not null for any record
- **AND** validation fails if duplicate rf_id values are found

#### Scenario: Validate referential integrity across tables

- **WHEN** validating assignee, assignor, documentid, and assignment_conveyance tables
- **THEN** every rf_id in these tables exists in the assignment table
- **AND** validation reports the count of orphaned records (if any)
- **AND** orphaned records are output to data/validated/fail/ for inspection

#### Scenario: Validate date fields

- **WHEN** validating date columns (record_dt, exec_dt, ack_dt, appno_date, grant_date)
- **THEN** all dates are within the valid range (1790-present)
- **AND** invalid dates are logged with record IDs
- **AND** the validation pass rate is calculated and compared against threshold (≥95%)

#### Scenario: Check completeness thresholds

- **WHEN** validating required fields (rf_id, grant_doc_num, ee_name, or_name)
- **THEN** the system calculates the percentage of non-null values
- **AND** validation passes if completeness is ≥95% for required fields
- **AND** a detailed completeness report is generated for all fields
