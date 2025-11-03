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

### Requirement: CETArea Node Creation

The system SHALL create CETArea nodes in Neo4j representing the 21 Critical and Emerging Technology categories with taxonomy metadata.

#### Scenario: Create CETArea node

- **WHEN** loading CET taxonomy from config/cet/taxonomy.yaml
- **THEN** the system creates a CETArea node for "Artificial Intelligence" with properties:
  - cet_id: "artificial_intelligence" (unique identifier)
  - name: "Artificial Intelligence"
  - definition: "AI and machine learning technologies including..."
  - keywords: ["artificial intelligence", "machine learning", "neural networks", ...]
  - taxonomy_version: "NSTC-2025Q1"
  - parent_cet_id: null (top-level category)
  - status: "active"
  - effective_date: date("2025-01-01")
- **AND** uses MERGE on cet_id to avoid duplicates

#### Scenario: Create hierarchical CET categories

- **WHEN** loading "Quantum Sensing" with parent_cet_id="quantum_computing"
- **THEN** the system creates a CETArea node for "Quantum Sensing"
- **AND** creates a SUBCATEGORY_OF relationship: (quantum_sensing)-[:SUBCATEGORY_OF]->(quantum_computing)
- **AND** enables hierarchical queries (find all subcategories of Quantum Computing)

#### Scenario: Create indexes for CET nodes

- **WHEN** the first CET loading batch begins
- **THEN** the system creates a unique index on CETArea.cet_id
- **AND** subsequent MERGE operations use the index for performance
- **AND** validates that all 21 expected CET categories are loaded

### Requirement: Award-CET APPLICABLE_TO Relationships

The system SHALL create APPLICABLE_TO relationships from Awards to CETArea nodes with classification metadata and evidence.

#### Scenario: Create primary CET relationship

- **WHEN** loading an award classified with primary CET area="artificial_intelligence", score=85
- **THEN** the system creates: (award:Award)-[:APPLICABLE_TO]->(ai:CETArea {cet_id: "artificial_intelligence"})
- **AND** the relationship has properties:
  - score: 85
  - classification: "High"
  - primary: true
  - evidence: [{excerpt: "Advanced neural network...", source: "abstract", rationale: "Contains: neural network, AI"}]
  - classified_at: datetime("2025-10-26T12:00:00Z")
  - taxonomy_version: "NSTC-2025Q1"

#### Scenario: Create supporting CET relationships

- **WHEN** an award has supporting CET areas ["autonomous_systems" (score=62), "cybersecurity" (score=58)]
- **THEN** the system creates 2 additional APPLICABLE_TO relationships
- **AND** each has primary=false
- **AND** each has its own score, classification, and evidence
- **AND** total relationships per award: 1 primary + up to 3 supporting

#### Scenario: Handle awards with no clear CET match

- **WHEN** an award is classified with primary CET area="uncategorized", score=30, classification="Low"
- **THEN** the system still creates the APPLICABLE_TO relationship
- **AND** includes low-confidence metadata for potential manual review
- **AND** enables filtering out low-confidence classifications in queries

#### Scenario: Batch write APPLICABLE_TO relationships

- **WHEN** loading 10,000 award classifications
- **THEN** the system groups writes into batches of 1,000 relationships per transaction
- **AND** uses UNWIND + MERGE for efficient bulk inserts
- **AND** commits each batch before proceeding to next
- **AND** logs progress every 10,000 relationships

### Requirement: Company-CET SPECIALIZES_IN Relationships

The system SHALL create SPECIALIZES_IN relationships from Companies to CETArea nodes with aggregated company-level metrics.

#### Scenario: Create company specialization relationship

- **WHEN** a company has 5 AI awards totaling $2.5M with avg score 78
- **THEN** the system creates: (company:Company)-[:SPECIALIZES_IN]->(ai:CETArea)
- **AND** the relationship has properties:
  - award_count: 5
  - total_funding: 2500000
  - avg_score: 78
  - dominant_phase: "II" (if most awards are Phase II)
  - first_award_date: date("2018-03-15")
  - last_award_date: date("2024-09-20")
  - specialization_score: 0.625 (if company has 8 total awards, 5/8 in AI)

#### Scenario: Handle multi-CET companies

- **WHEN** a company has awards in 3 CET areas: AI (5 awards), Cybersecurity (2), Quantum (1)
- **THEN** the system creates 3 SPECIALIZES_IN relationships
- **AND** AI relationship has highest award_count and specialization_score
- **AND** enables queries for companies by CET specialization threshold

#### Scenario: Update company CET profiles incrementally

- **WHEN** new awards are added for existing company
- **THEN** the system updates SPECIALIZES_IN relationship properties
- **AND** recalculates award_count, total_funding, avg_score
- **AND** updates last_award_date if new award is more recent
- **AND** uses MERGE + SET for upsert behavior

### Requirement: Patent-CET APPLICABLE_TO Relationships

The system SHALL create APPLICABLE_TO relationships from Patents to CETArea nodes with USPTO validation metadata when available.

#### Scenario: Create patent CET relationship

- **WHEN** loading a patent classified with CET area="quantum_computing", score=72
- **THEN** the system creates: (patent:Patent)-[:APPLICABLE_TO]->(quantum:CETArea)
- **AND** the relationship has properties:
  - score: 72
  - classification: "High"
  - classified_at: datetime("2025-10-26T12:00:00Z")
  - taxonomy_version: "NSTC-2025Q1"

#### Scenario: Include USPTO AI validation metadata

- **WHEN** a patent with grant_doc_num="10000002" has USPTO AI prediction predict93_any_ai=1, ai_score_any_ai=0.999646
- **THEN** the APPLICABLE_TO relationship to "artificial_intelligence" CET includes:
  - uspto_ai_score: 0.999646
  - uspto_confidence_threshold: "93"
  - uspto_validation_status: "ALIGNED" (if our CET score ≥70)

#### Scenario: Track technology transition in graph

- **WHEN** an award (CET="artificial_intelligence") funds a patent (CET="artificial_intelligence")
- **THEN** both Award and Patent have APPLICABLE_TO relationships to same CETArea
- **AND** the existing (Award)-[:FUNDED]->(Patent) relationship enables transition queries
- **AND** query can find: MATCH (a:Award)-[:APPLICABLE_TO]->(cet:CETArea)<-[:APPLICABLE_TO]-(p:Patent) WHERE (a)-[:FUNDED]->(p)

### Requirement: CET Portfolio Queries

The system SHALL enable efficient Cypher queries for CET-based portfolio analysis through appropriate indexes and graph patterns.

#### Scenario: Query awards by CET area

- **WHEN** querying for all high-confidence AI awards
- **THEN** the system executes:

  ```cypher
  MATCH (a:Award)-[r:APPLICABLE_TO {primary: true}]->(cet:CETArea {cet_id: "artificial_intelligence"})
  WHERE r.score >= 70
  RETURN a.award_id, a.firm_name, r.score, r.classification
  ORDER BY r.score DESC
  LIMIT 100
  ```

- **AND** query executes in <1 second using index on CETArea.cet_id

#### Scenario: Aggregate funding by CET area

- **WHEN** calculating total SBIR funding per CET area
- **THEN** the system executes:

  ```cypher
  MATCH (a:Award)-[r:APPLICABLE_TO {primary: true}]->(cet:CETArea)
  WHERE a.award_date >= date("2020-01-01")
  RETURN
    cet.name AS technology_area,
    count(a) AS award_count,
    sum(a.award_amount) AS total_funding,
    avg(r.score) AS avg_confidence
  ORDER BY total_funding DESC
  ```

#### Scenario: Find companies specializing in CET area

- **WHEN** querying for top companies in Quantum Computing
- **THEN** the system executes:

  ```cypher
  MATCH (c:Company)-[s:SPECIALIZES_IN]->(cet:CETArea {cet_id: "quantum_computing"})
  WHERE s.award_count >= 3
  RETURN
    c.name,
    s.award_count,
    s.total_funding,
    s.avg_score,
    s.dominant_phase
  ORDER BY s.total_funding DESC
  LIMIT 50
  ```

#### Scenario: Track technology transition success

- **WHEN** analyzing technology transition from awards to patents
- **THEN** the system executes:

  ```cypher
  MATCH (a:Award)-[:APPLICABLE_TO]->(award_cet:CETArea)
  MATCH (a)-[:FUNDED]->(p:Patent)-[:APPLICABLE_TO]->(patent_cet:CETArea)
  RETURN
    award_cet.name AS award_technology,
    patent_cet.name AS patent_technology,
    count(*) AS transition_count,
    sum(CASE WHEN award_cet = patent_cet THEN 1 ELSE 0 END) AS aligned_transitions,
    sum(CASE WHEN award_cet = patent_cet THEN 1 ELSE 0 END) * 1.0 / count(*) AS alignment_rate
  GROUP BY award_cet, patent_cet
  ORDER BY transition_count DESC
  ```

### Requirement: CET Data Quality Constraints

The system SHALL enforce data quality constraints on CET nodes and relationships to maintain graph integrity.

#### Scenario: Validate CET node count

- **WHEN** loading CET taxonomy
- **THEN** the system validates exactly 21 CETArea nodes exist (one per category)
- **AND** fails if any expected category is missing
- **AND** logs warning if unexpected categories are found

#### Scenario: Validate relationship properties

- **WHEN** creating APPLICABLE_TO relationship
- **THEN** the system validates:
  - score is between 0 and 100
  - classification is one of ["High", "Medium", "Low"]
  - primary is boolean
  - classified_at is valid datetime
  - taxonomy_version is not null
- **AND** rejects relationships with invalid properties

#### Scenario: Validate evidence structure

- **WHEN** storing evidence array on APPLICABLE_TO relationship
- **THEN** the system validates each evidence statement has:
  - excerpt (non-empty string, ≤50 words)
  - source_location (one of ["abstract", "keywords", "solicitation", "reviewer_notes"])
  - rationale_tag (non-empty string)
- **AND** limits evidence array to ≤3 statements

