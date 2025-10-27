# data-loading Specification

## Purpose
TBD - created by archiving change add-initial-architecture. Update Purpose after archive.
## Requirements
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

### Requirement: Patent Node Creation

The system SHALL create Patent nodes in Neo4j with unique grant document numbers and associated metadata.

#### Scenario: Create Patent node from USPTO data

- **WHEN** loading a patent with grant_doc_num="5858003", title="SYSTEMS AND METHODS FOR PROMOTING TISSUE GROWTH"
- **THEN** the system creates a Patent node with properties:
  - grant_doc_num: "5858003" (primary key)
  - title: "SYSTEMS AND METHODS FOR PROMOTING TISSUE GROWTH"
  - application_date: 1994-10-20
  - grant_date: 1999-01-12
  - language: "en"
- **AND** the node is created using MERGE to avoid duplicates

#### Scenario: Handle patents with missing titles

- **WHEN** loading a patent with grant_doc_num but null title
- **THEN** the system creates the Patent node with title=null
- **AND** logs a data quality warning
- **AND** the patent can still be linked to assignments

#### Scenario: Create index on grant_doc_num

- **WHEN** the first patent loading batch begins
- **THEN** the system creates a unique index on Patent.grant_doc_num
- **AND** subsequent MERGE operations use the index for performance
- **AND** constraint violations (duplicate grant numbers) are logged

### Requirement: PatentAssignment Node Creation

The system SHALL create PatentAssignment nodes representing ownership transfer events with temporal metadata.

#### Scenario: Create PatentAssignment node

- **WHEN** loading an assignment with rf_id=12800340, conveyance_type="assignment", record_dt=1999-07-29
- **THEN** the system creates a PatentAssignment node with properties:
  - rf_id: "12800340" (primary key)
  - reel_no: "1280"
  - frame_no: "340"
  - conveyance_type: "assignment"
  - record_date: 1999-07-29
  - conveyance_text: "ASSIGNMENT OF ASSIGNORS INTEREST..."
  - page_count: 2

#### Scenario: Handle batch assignments (multiple patents per rf_id)

- **WHEN** an assignment (rf_id=36250888) covers 5 different patents
- **THEN** the system creates one PatentAssignment node
- **AND** creates ASSIGNED_VIA relationships from all 5 Patent nodes to the same PatentAssignment
- **AND** the relationship count matches the document count

### Requirement: PatentEntity Node Creation

The system SHALL create PatentEntity nodes for assignees and assignors with deduplicated entity resolution.

#### Scenario: Create assignee entity node

- **WHEN** loading an assignee "CHILDREN'S MEDICAL CENTER CORPORATION" at "55 SHATTUCK STREET BOSTON, MA 02115"
- **THEN** the system creates a PatentEntity node with:
  - name: "CHILDREN'S MEDICAL CENTER CORPORATION" (normalized)
  - entity_hash: hash(normalized_name + address) (for deduplication)
  - address_line_1: "55 SHATTUCK STREET BOSTON, MA 02115"
  - city: "BOSTON"
  - state: "MA"
  - postcode: "02115"
- **AND** uses MERGE on entity_hash to deduplicate

#### Scenario: Create assignor entity node

- **WHEN** loading an assignor "ATALA, ANTHONY" with exec_dt=1994-12-22
- **THEN** the system creates a PatentEntity node
- **AND** the execution date is stored on the relationship, not the node
- **AND** the same person appearing in multiple assignments is deduplicated

#### Scenario: Handle entity name variations

- **WHEN** loading assignees "IBM", "IBM CORP", "IBM CORPORATION"
- **THEN** the system normalizes all to "IBM CORP"
- **AND** creates a single PatentEntity node (deduplicated by entity_hash)
- **AND** stores original name variations in a list property for audit

### Requirement: Patent Assignment Relationships

The system SHALL create directed relationships representing patent ownership transfers with temporal properties.

#### Scenario: Create ASSIGNED_VIA relationship

- **WHEN** linking a Patent (grant_doc_num="5858003") to a PatentAssignment (rf_id=12800340)
- **THEN** the system creates: (Patent)-[:ASSIGNED_VIA]->(PatentAssignment)
- **AND** the relationship has no additional properties (metadata is on nodes)

#### Scenario: Create ASSIGNED_FROM relationship

- **WHEN** linking an assignor "ATALA, ANTHONY" to a PatentAssignment
- **THEN** the system creates: (PatentAssignment)-[:ASSIGNED_FROM {exec_date: "1994-12-22"}]->(PatentEntity)
- **AND** the exec_date property captures when the assignor executed the transfer

#### Scenario: Create ASSIGNED_TO relationship

- **WHEN** linking an assignee "CHILDREN'S MEDICAL CENTER CORPORATION" to a PatentAssignment
- **THEN** the system creates: (PatentAssignment)-[:ASSIGNED_TO {record_date: "1999-07-29"}]->(PatentEntity)
- **AND** the record_date property captures when ownership was officially recorded

#### Scenario: Handle multiple assignees per assignment

- **WHEN** an assignment has 3 assignees
- **THEN** the system creates 3 ASSIGNED_TO relationships from the same PatentAssignment to 3 different PatentEntity nodes
- **AND** each relationship preserves the individual assignee's metadata

### Requirement: SBIR-Patent Linkage Relationships

The system SHALL create relationships linking SBIR Awards to Patents when company matches are found.

#### Scenario: Create FUNDED relationship with high confidence

- **WHEN** a Patent is matched to an Award with confidence ≥0.85
- **THEN** the system creates: (Award)-[:FUNDED {confidence: 0.95, method: "exact_patent_num"}]->(Patent)
- **AND** the relationship is created using MERGE to avoid duplicates

#### Scenario: Create OWNS relationship for current ownership

- **WHEN** a Patent's most recent assignment links to a Company
- **THEN** the system creates: (Company)-[:OWNS {as_of_date: "1999-07-29"}]->(Patent)
- **AND** the as_of_date reflects the latest assignment record_date
- **AND** old OWNS relationships are removed (replaced by new ownership)

#### Scenario: Skip low-confidence links

- **WHEN** a Patent-Company match has confidence <0.70
- **THEN** the system does not create a FUNDED relationship
- **AND** the potential match is logged for manual review
- **AND** linkage metrics track the skip rate

### Requirement: Bulk Loading Performance

The system SHALL optimize Neo4j write operations for bulk patent assignment loading with transactional batching.

#### Scenario: Batch writes in transactions

- **WHEN** loading 8 million patent assignments
- **THEN** the system groups writes into batches of 1,000 records per transaction
- **AND** uses UNWIND + MERGE for efficient bulk inserts
- **AND** commits each batch before proceeding to the next

#### Scenario: Create indexes before bulk load

- **WHEN** the loading pipeline starts
- **THEN** the system creates indexes on Patent.grant_doc_num, PatentAssignment.rf_id, PatentEntity.entity_hash
- **AND** indexes are enabled during load for MERGE operations
- **AND** index creation completes before first write batch

#### Scenario: Log loading progress and throughput

- **WHEN** loading patents in batches
- **THEN** the system logs progress every 10,000 records
- **AND** calculates throughput in records/second
- **AND** estimates time remaining based on current throughput
- **AND** reports final load time and success rate (target: ≥99%)

### Requirement: Incremental Update Support

The system SHALL support incremental loading of monthly USPTO updates without duplicating existing data.

#### Scenario: Upsert existing patents

- **WHEN** loading a monthly update containing grant_doc_num="5858003" (already exists)
- **THEN** the system uses MERGE to update the Patent node with any new properties
- **AND** does not create duplicate Patent nodes

#### Scenario: Append new assignments

- **WHEN** loading new PatentAssignment records (rf_id not yet in Neo4j)
- **THEN** the system creates new PatentAssignment nodes
- **AND** links them to existing or new Patent nodes
- **AND** creates ASSIGNED_TO/ASSIGNED_FROM relationships

#### Scenario: Update company ownership

- **WHEN** a Patent has a new assignment in the monthly update
- **THEN** the system removes old (Company)-[:OWNS]->(Patent) relationships
- **AND** creates new OWNS relationships reflecting current ownership
- **AND** preserves historical assignment chain via PatentAssignment nodes

