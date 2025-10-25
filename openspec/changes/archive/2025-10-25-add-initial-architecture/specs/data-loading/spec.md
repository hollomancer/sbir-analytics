# Data Loading Specification

## ADDED Requirements

### Requirement: Neo4j Node Creation
The system SHALL create Neo4j nodes for each entity type with proper labels and properties.

#### Scenario: Node creation with properties
- **WHEN** a node entity is loaded
- **THEN** a Neo4j node SHALL be created with the appropriate label (e.g., :Company, :Award)
- **AND** all entity properties SHALL be set on the node

#### Scenario: Batch node creation
- **WHEN** multiple nodes of the same type are loaded
- **THEN** nodes SHALL be created in batches for performance
- **AND** the batch size SHALL be configurable

### Requirement: Neo4j Relationship Creation
The system SHALL create relationships between nodes based on relationship entities.

#### Scenario: Relationship creation
- **WHEN** a relationship entity is loaded
- **THEN** a Neo4j relationship SHALL be created between the source and target nodes
- **AND** the relationship type SHALL match the entity's relationship type
- **AND** relationship properties SHALL be set

#### Scenario: Missing node handling
- **WHEN** a relationship references a non-existent node
- **THEN** the loader SHALL log an error
- **AND** the relationship SHALL NOT be created
- **AND** the missing node ID SHALL be reported

### Requirement: Index and Constraint Management
The system SHALL create and maintain indexes and constraints on Neo4j for data integrity and query performance.

#### Scenario: Unique constraint creation
- **WHEN** loading begins
- **THEN** unique constraints SHALL be created on primary key properties (e.g., Company.uei, Award.award_id)
- **AND** constraint violations SHALL block duplicate node creation

#### Scenario: Index creation for performance
- **WHEN** loading begins
- **THEN** indexes SHALL be created on frequently queried properties
- **AND** the indexes SHALL improve query performance

### Requirement: Upsert Semantics
The system SHALL support upsert (insert or update) semantics for idempotent loading.

#### Scenario: New node insertion
- **WHEN** a node does not exist in Neo4j
- **THEN** it SHALL be created with all properties

#### Scenario: Existing node update
- **WHEN** a node already exists (matched by unique key)
- **THEN** its properties SHALL be updated with new values
- **AND** the operation SHALL be idempotent (repeated loads produce same result)

### Requirement: Transaction Management
The system SHALL use Neo4j transactions to ensure data consistency and enable rollback on errors.

#### Scenario: Batch transaction commit
- **WHEN** a batch of nodes/relationships is loaded successfully
- **THEN** the transaction SHALL be committed
- **AND** the data SHALL be persisted to Neo4j

#### Scenario: Transaction rollback on error
- **WHEN** an error occurs during loading (e.g., constraint violation)
- **THEN** the transaction SHALL be rolled back
- **AND** no partial data SHALL be persisted
- **AND** the error SHALL be logged with details

### Requirement: Load Metrics Tracking
The system SHALL track and report loading metrics including nodes created, relationships created, and load duration.

#### Scenario: Load metrics collection
- **WHEN** loading completes
- **THEN** metrics SHALL include total nodes created/updated by type
- **AND** total relationships created by type
- **AND** load duration and throughput (records/second)
- **AND** the metrics SHALL be logged and available for monitoring
