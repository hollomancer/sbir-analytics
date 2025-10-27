# Data Transformation - USPTO Patent Assignment Delta

## ADDED Requirements

### Requirement: Patent Assignment Table Joins

The system SHALL join the five USPTO relational tables (assignment, assignee, assignor, documentid, assignment_conveyance) into a unified patent assignment dataset using rf_id as the linking key.

#### Scenario: Join all tables via rf_id

- **WHEN** transforming validated USPTO data
- **THEN** the system performs LEFT JOIN from assignment table to all related tables on rf_id
- **AND** one assignment record may have multiple assignees, assignors, and document IDs
- **AND** the resulting dataset includes all columns from all five tables

#### Scenario: Handle one-to-many relationships

- **WHEN** an assignment (rf_id=12345) has 3 assignees and 2 patents
- **THEN** the transformation creates 6 records (3 assignees × 2 patents)
- **AND** each record contains the full assignment metadata
- **AND** downstream loaders can aggregate by rf_id or grant_doc_num as needed

#### Scenario: Preserve null values in optional fields

- **WHEN** an assignment has no acknowledgment date (ack_dt is null)
- **THEN** the transformation preserves the null value
- **AND** downstream queries can filter on null vs. non-null dates

### Requirement: Entity Name Normalization

The system SHALL normalize assignee and assignor entity names to facilitate matching and deduplication.

#### Scenario: Normalize name formatting

- **WHEN** transforming assignee name "  IBM Corp.  " (with whitespace and punctuation)
- **THEN** the system trims leading/trailing whitespace
- **AND** converts to uppercase: "IBM CORP"
- **AND** removes non-alphanumeric characters except spaces: "IBM CORP"
- **AND** stores both original and normalized names

#### Scenario: Handle name variations

- **WHEN** transforming assignee names "IBM", "IBM CORP", "INTERNATIONAL BUSINESS MACHINES CORPORATION"
- **THEN** the system normalizes all to standard format
- **AND** calculates a name hash for deduplication
- **AND** stores mappings for entity resolution

#### Scenario: Preserve empty names for validation

- **WHEN** an assignee name is empty or null
- **THEN** the transformation preserves the empty value
- **AND** logs a data quality warning with the rf_id
- **AND** the record is flagged for manual review

### Requirement: Address Parsing and Standardization

The system SHALL parse and standardize address fields (address_1, address_2, city, state, postcode, country) into structured components.

#### Scenario: Extract city, state, country from address fields

- **WHEN** transforming assignee address "55 SHATTUCK STREET BOSTON, MA 02115"
- **THEN** the system extracts city="BOSTON", state="MA", postcode="02115"
- **AND** the full address is preserved in a combined field
- **AND** structured fields enable geographic queries

#### Scenario: Standardize country codes

- **WHEN** transforming country field "NOT PROVIDED" or empty
- **THEN** the system maps to null or "UNKNOWN"
- **AND** valid country names are mapped to ISO 3166 codes (US, CA, GB)

#### Scenario: Handle multi-line addresses

- **WHEN** an address spans address_1, address_2, address_3 fields
- **THEN** the system concatenates all non-null address lines
- **AND** preserves original line breaks for display
- **AND** extracts city/state/postcode from the last line

### Requirement: Conveyance Type Parsing

The system SHALL parse the free-text conveyance_text field to extract structured assignment type information.

#### Scenario: Classify assignment types

- **WHEN** convey_text contains "ASSIGNMENT OF ASSIGNORS INTEREST"
- **THEN** the system extracts conveyance_type = "assignment"
- **WHEN** convey_text contains "LICENSE AGREEMENT"
- **THEN** conveyance_type = "license"
- **WHEN** convey_text contains "SECURITY AGREEMENT"
- **THEN** conveyance_type = "security_interest"

#### Scenario: Extract assignment details from text

- **WHEN** convey_text contains "SEE DOCUMENT FOR DETAILS"
- **THEN** the system flags the record for potential document retrieval
- **AND** includes a has_details boolean field
- **AND** preserves the full text for manual inspection

### Requirement: Company-Patent Linkage

The system SHALL link USPTO patents to SBIR companies using multi-stage matching with confidence scoring.

#### Scenario: Exact patent number match

- **WHEN** an SBIR award record contains grant_doc_num="5858003"
- **AND** a Patent in USPTO data has grant_doc_num="5858003"
- **THEN** the system creates a link with confidence=0.95 and method="exact_patent_num"

#### Scenario: Fuzzy company name match

- **WHEN** an assignee name "CHILDRENS MEDICAL CENTER CORPORATION" matches an SBIR company "Children's Medical Center Corp" with similarity=0.85
- **THEN** the system creates a link with confidence=0.85 and method="fuzzy_name"
- **AND** stores the similarity score for filtering

#### Scenario: No match found

- **WHEN** a patent has no matching SBIR company above the threshold (≥0.70)
- **THEN** the system does not create a link
- **AND** the patent is still loaded to Neo4j for future matching
- **AND** unlinked patents are tracked in metrics

#### Scenario: Aggregate linkage metrics

- **WHEN** transformation completes
- **THEN** the system calculates linkage rate = (linked_patents / total_patents)
- **AND** reports linkage rate by confidence bucket (<0.70, 0.70-0.85, ≥0.85)
- **AND** logs companies with no linked patents for review
