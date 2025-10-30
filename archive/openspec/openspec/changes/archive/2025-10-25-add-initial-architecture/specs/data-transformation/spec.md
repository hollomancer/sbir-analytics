# Data Transformation Specification

## ADDED Requirements

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
