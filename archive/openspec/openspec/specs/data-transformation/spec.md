# data-transformation Specification

## Purpose

TBD - created by archiving change add-initial-architecture. Update Purpose after archive.

## Requirements


### Requirement: Business Logic Application

The system SHALL apply business logic and transformations to prepare data for graph database loading.

#### Scenario: Data normalization

- **WHEN** data contains inconsistent formats (e.g., company names with varying capitalization)
- **THEN** the system SHALL normalize to a standard format
- **AND** the normalization rules SHALL be consistent across all records

#### Scenario: Calculated field generation

- **WHEN** derived fields are needed (e.g., award phase calculated from amount ranges)
- **THEN** the system SHALL calculate and populate those fields
- **AND** the calculation logic SHALL be deterministic and repeatable

### Requirement: Graph Entity Preparation

The system SHALL transform relational data into graph-ready entities with nodes and relationships.

#### Scenario: Node entity creation

- **WHEN** transforming awards data
- **THEN** the system SHALL create separate node entities for each node type (Company, Award, Researcher)
- **AND** each node SHALL have a unique identifier and required properties

#### Scenario: Relationship entity creation

- **WHEN** relationships exist between entities (e.g., Award → Company)
- **THEN** the system SHALL create relationship entities with source ID, target ID, and relationship type
- **AND** relationship properties SHALL be included where applicable

### Requirement: Data Type Coercion

The system SHALL coerce data types to formats compatible with Neo4j (e.g., dates to ISO strings, nested objects to JSON).

#### Scenario: Date format conversion

- **WHEN** date fields are present in various formats
- **THEN** dates SHALL be converted to ISO 8601 format strings
- **AND** invalid dates SHALL be logged and set to null

#### Scenario: Nested data handling

- **WHEN** nested or complex data structures are present
- **THEN** they SHALL be serialized to JSON strings or flattened as appropriate
- **AND** the transformation SHALL preserve data integrity

### Requirement: Referential Integrity Validation

The system SHALL validate referential integrity between entities before graph loading.

#### Scenario: Foreign key validation

- **WHEN** a relationship references an entity (e.g., Award references Company by ID)
- **THEN** the system SHALL verify that the referenced entity exists
- **AND** orphaned relationships SHALL be flagged as errors

#### Scenario: Referential integrity reporting

- **WHEN** referential integrity issues are found
- **THEN** the system SHALL generate a report with issue count and sample IDs
- **AND** the severity SHALL be configurable (block vs. warn)

### Requirement: Idempotent Transformations

The system SHALL ensure transformations are idempotent, producing the same output for the same input.

#### Scenario: Repeated transformation

- **WHEN** the same input data is transformed multiple times
- **THEN** the output SHALL be identical each time
- **AND** no hidden state or side effects SHALL affect the output

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

### Requirement: CET Award Classification

The system SHALL classify SBIR awards against 21 Critical and Emerging Technology (CET) areas using machine learning with evidence-based explainability.

#### Scenario: Classify award with high confidence

- **WHEN** processing an award with abstract="Advanced neural network development for autonomous vehicle perception..."
- **THEN** the system classifies the award with primary CET area="artificial_intelligence"
- **AND** score=85, classification="High"
- **AND** supporting CET areas include ["autonomous_systems", "advanced_communications"]
- **AND** evidence statements (up to 3) contain relevant sentences with keyword highlights

#### Scenario: Extract supporting evidence

- **WHEN** classifying an award against CET area "artificial_intelligence"
- **THEN** the system extracts up to 3 sentences containing CET keywords
- **AND** each evidence statement includes:
  - excerpt (≤50 words)
  - source_location ("abstract", "keywords", or "solicitation")
  - rationale_tag (e.g., "Contains: neural network, machine learning")

#### Scenario: Handle low-confidence classifications

- **WHEN** an award has unclear or multi-disciplinary technology focus (score <40)
- **THEN** the system assigns classification="Low"
- **AND** may assign primary CET area="uncategorized"
- **AND** logs the award for potential manual review

#### Scenario: Batch classification for efficiency

- **WHEN** classifying 10,000 awards
- **THEN** the system processes awards in batches of 1,000
- **AND** vectorizes text in batch for TF-IDF efficiency
- **AND** achieves throughput ≥1,000 awards/second
- **AND** average per-award latency ≤1 second

### Requirement: Company CET Aggregation

The system SHALL aggregate CET classifications from all awards to generate company-level CET specialization profiles.

#### Scenario: Calculate dominant CET area

- **WHEN** a company has received 5 AI awards (avg score 80), 2 Cybersecurity awards (avg score 65), 1 Quantum award (score 50)
- **THEN** the system identifies dominant CET area="artificial_intelligence"
- **AND** calculates specialization_score = 5 / 8 = 0.625 (62.5% concentration)

#### Scenario: Track CET evolution over time

- **WHEN** a company received Phase I AI awards in 2020, Phase II AI+Cybersecurity awards in 2022, Phase III Cybersecurity awards in 2024
- **THEN** the system tracks CET progression: AI → AI+Cybersecurity → Cybersecurity
- **AND** stores first_award_date and last_award_date per CET area
- **AND** identifies CET pivot or expansion patterns

#### Scenario: Calculate company-CET metrics

- **WHEN** aggregating company CET profile
- **THEN** the system calculates per-CET metrics:
  - award_count (number of awards in CET)
  - total_funding (sum of award amounts in CET)
  - avg_score (average CET classification score)
  - dominant_phase ("I", "II", "III", or "Mixed")

### Requirement: Patent CET Classification

The system SHALL classify patents based on title and assignee entity context to enable technology transition tracking.

#### Scenario: Classify patent from title

- **WHEN** classifying a patent with title="Systems and Methods for Quantum Error Correction in Superconducting Qubits"
- **THEN** the system classifies with primary CET area="quantum_computing"
- **AND** score ≥70 (high confidence)
- **AND** extracts evidence from title

#### Scenario: Validate with USPTO AI predictions

- **WHEN** classifying a patent with grant_doc_num="10000002"
- **AND** USPTO AI dataset has predict93_any_ai=1 (high confidence AI patent)
- **THEN** the system checks if CET classification aligns with USPTO prediction
- **AND** if CET area="artificial_intelligence" and score ≥70, validation status="ALIGNED"
- **AND** if CET area ≠ "artificial_intelligence" or score <70, validation status="MISALIGNED"
- **AND** logs validation metrics for model improvement

#### Scenario: Track technology transition alignment

- **WHEN** a patent originates from an SBIR award (Award → FUNDED → Patent)
- **THEN** the system compares award CET area with patent CET area
- **AND** calculates cet_alignment = (award_primary_cet == patent_primary_cet)
- **AND** tracks transition_score = max(award_score, patent_score) if aligned, else average of both
- **AND** enables queries for successful technology transitions

### Requirement: CET Confidence Scoring

The system SHALL provide multi-threshold confidence scoring (High/Medium/Low) based on calibrated probability estimates.

#### Scenario: Three-band confidence classification

- **WHEN** the ML model outputs probability=0.85 for CET area="artificial_intelligence"
- **THEN** the system converts to score=85
- **AND** classification="High" (score ≥70)

- **WHEN** probability=0.55
- **THEN** score=55, classification="Medium" (40 ≤ score <70)

- **WHEN** probability=0.30
- **THEN** score=30, classification="Low" (score <40)

#### Scenario: Calibrated probability scores

- **WHEN** training the CET classifier
- **THEN** the system applies sigmoid calibration with 3-fold cross-validation
- **AND** ensures probabilities are well-calibrated (reliability diagram within acceptable bounds)
- **AND** enables threshold adjustment without retraining

### Requirement: CET Taxonomy Versioning

The system SHALL support multiple CET taxonomy versions to enable longitudinal analysis and taxonomy evolution.

#### Scenario: Version all classifications

- **WHEN** classifying an award on 2025-10-26 using NSTC-2025Q1 taxonomy
- **THEN** the classification stores taxonomy_version="NSTC-2025Q1"
- **AND** classified_at=datetime("2025-10-26T12:00:00Z")

#### Scenario: Reclassify with new taxonomy

- **WHEN** NSTC releases updated taxonomy (NSTC-2025Q2) with new CET area "Synthetic Biology"
- **THEN** the system provides reclassification job
- **AND** preserves historical classifications with old taxonomy_version
- **AND** generates new classifications with taxonomy_version="NSTC-2025Q2"
- **AND** enables comparison across taxonomy versions

#### Scenario: Handle taxonomy changes

- **WHEN** a CET category is renamed (e.g., "Semiconductors" → "Semiconductors & Microelectronics")
- **THEN** the system tracks category lineage
- **AND** provides mapping from old to new category IDs
- **AND** updates visualizations and queries to use new names while preserving historical data
