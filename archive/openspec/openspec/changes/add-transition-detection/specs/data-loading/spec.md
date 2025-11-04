# Data Loading - Transition Detection Delta

## ADDED Requirements

### Requirement: Transition Node Creation

The system SHALL create Transition nodes in Neo4j representing detected commercialization events with scoring metadata.

#### Scenario: Create Transition node with evidence

- **WHEN** loading a transition with likelihood_score=0.87, confidence="High"
- **THEN** the system creates a Transition node with properties:
  - transition_id: UUID (unique identifier)
  - detection_date: datetime("2025-10-26T12:00:00Z")
  - likelihood_score: 0.87
  - confidence: "High"
  - detection_version: "1.0" (algorithm version)
- **AND** uses MERGE on transition_id to avoid duplicates

#### Scenario: Create index on transition_id

- **WHEN** the first transition loading batch begins
- **THEN** the system creates a unique index on Transition.transition_id
- **AND** creates indexes on Transition.confidence, Transition.likelihood_score
- **AND** subsequent MERGE operations use indexes for performance

### Requirement: Award-Transition Relationships

The system SHALL create TRANSITIONED_TO relationships from Awards to Transitions with complete evidence bundles.

#### Scenario: Create TRANSITIONED_TO relationship with evidence

- **WHEN** loading a transition detection for award "ABC-2020-001"
- **THEN** the system creates: (Award {award_id: "ABC-2020-001"})-[:TRANSITIONED_TO]->(Transition)
- **AND** the relationship has properties:
  - likelihood_score: 0.87
  - confidence: "High"
  - evidence: {JSON evidence bundle ~2KB}
  - detection_date: datetime()
  - vendor_match_method: "uei_exact"
  - vendor_match_confidence: 0.99
- **AND** evidence bundle includes all scoring components

#### Scenario: Handle multiple transitions per award

- **WHEN** an award transitions to 3 different contracts (multiple detections)
- **THEN** the system creates 3 TRANSITIONED_TO relationships
- **AND** each has its own Transition node and evidence
- **AND** enables tracking of multiple commercialization pathways

### Requirement: Transition-Contract Relationships

The system SHALL create RESULTED_IN relationships from Transitions to Contract nodes.

#### Scenario: Link transition to contract

- **WHEN** a transition results from contract PIID="ABC123456"  # pragma: allowlist secret
- **THEN** the system creates: (Transition)-[:RESULTED_IN]->(Contract {piid: "ABC123456"})  # pragma: allowlist secret
- **AND** relationship properties include:
  - contract_start_date: date("2021-09-15")
  - contract_amount: 2500000
  - competition_type: "SOLE SOURCE"
  - agency: "DOD"

#### Scenario: Create Contract nodes for new contracts

- **WHEN** loading a contract that doesn't exist in Neo4j yet
- **THEN** the system creates a Contract node with properties:
  - piid: "ABC123456" (unique identifier)
  - agency: "DOD"
  - start_date: date("2021-09-15")
  - amount: 2500000
  - competition_type: "SOLE SOURCE"
  - parent_piid: null (or parent contract if IDV)
- **AND** uses MERGE on piid to avoid duplicates

### Requirement: Patent-Backed Transition Relationships

The system SHALL create ENABLED_BY relationships from Transitions to Patents when patent signals exist.

#### Scenario: Link patent-backed transition

- **WHEN** a transition includes patent signals
- **AND** patents ["5858003", "6123456"] were filed before the contract
- **THEN** the system creates: (Transition)-[:ENABLED_BY]->(Patent {grant_doc_num: "5858003"})
- **AND** (Transition)-[:ENABLED_BY]->(Patent {grant_doc_num: "6123456"})
- **AND** each relationship has properties:
  - patent_filing_lag_days: 114
  - patent_topic_similarity: 0.82
  - filed_before_contract: true
  - signal_score: 0.05

#### Scenario: Identify technology transfer via patents

- **WHEN** a patent assignee differs from SBIR award recipient
- **THEN** the ENABLED_BY relationship includes:
  - technology_transfer: true
  - assignee_name: "TechCorp Inc" (different from SBIR recipient)
  - transfer_type: "licensing" (inferred)

### Requirement: CET Area Transition Relationships

The system SHALL create INVOLVES_TECHNOLOGY relationships from Transitions to CETArea nodes to enable technology-specific analytics.

#### Scenario: Link transition to CET area

- **WHEN** an award with primary_cet_id="artificial_intelligence" transitions
- **THEN** the system creates: (Transition)-[:INVOLVES_TECHNOLOGY]->(CETArea {cet_id: "artificial_intelligence"})
- **AND** relationship properties include:
  - award_cet_score: 85 (award's CET classification score)
  - cet_alignment: true (if contract also AI-related)

#### Scenario: Track transitions without CET

- **WHEN** an award has no CET classification (optional module not enabled)
- **THEN** the system creates the transition without INVOLVES_TECHNOLOGY relationship
- **AND** gracefully handles missing CET data

### Requirement: Company Transition Profile Nodes

The system SHALL create TransitionProfile nodes aggregating company-level transition metrics.

#### Scenario: Create company transition profile

- **WHEN** aggregating transitions for company "Acme Corp"
- **AND** company has 12 awards with 8 transitions
- **THEN** the system creates a TransitionProfile node with properties:
  - company_id: "COMPANY-001"
  - total_awards: 12
  - total_transitions: 8
  - success_rate: 0.67 (8/12)
  - avg_likelihood_score: 0.79
  - avg_time_to_transition_days: 402
  - sustained_commercialization: true (≥2 transitions)
- **AND** creates: (Company)-[:ACHIEVED]->(TransitionProfile)

#### Scenario: Identify high-performing companies

- **WHEN** filtering companies by transition profile
- **WHERE** success_rate ≥ 0.60 AND total_transitions ≥ 5
- **THEN** the query returns companies with sustained commercialization capability
- **AND** enables benchmarking and best practice analysis

### Requirement: Transition Pathway Queries

The system SHALL enable efficient Cypher queries for transition pathway analysis through appropriate indexes and graph patterns.

#### Scenario: Query award transition pathways

- **WHEN** querying for high-confidence AI transitions with patents
- **THEN** the system executes:

  ```cypher
  MATCH path = (a:Award)-[:APPLICABLE_TO]->(cet:CETArea {name: "Artificial Intelligence"}),
               (a)-[:TRANSITIONED_TO {confidence: "High"}]->(t:Transition),
               (t)-[:ENABLED_BY]->(p:Patent),
               (t)-[:RESULTED_IN]->(c:Contract)
  RETURN
      a.award_id,
      a.firm_name,
      p.grant_doc_num,
      c.piid,
      c.amount as contract_value
  ORDER BY contract_value DESC
  ```

- **AND** query executes in <2 seconds using indexes

#### Scenario: Calculate transition rate by CET area

- **WHEN** analyzing transition effectiveness by technology
- **THEN** the system executes:

  ```cypher
  MATCH (a:Award)-[:APPLICABLE_TO]->(cet:CETArea)
  OPTIONAL MATCH (a)-[:TRANSITIONED_TO]->(t:Transition {confidence: "High"})
  WITH cet, count(DISTINCT a) as total_awards, count(DISTINCT t) as transitions
  RETURN
      cet.name as technology_area,
      total_awards,
      transitions,
      transitions * 100.0 / total_awards as transition_rate_pct
  ORDER BY transition_rate_pct DESC
  ```

#### Scenario: Identify patent-backed transition patterns

- **WHEN** analyzing role of patents in commercialization
- **THEN** the system executes:

  ```cypher
  MATCH (a:Award)-[:TRANSITIONED_TO]->(t:Transition)
  OPTIONAL MATCH (t)-[:ENABLED_BY]->(p:Patent)
  WITH count(DISTINCT t) as total_transitions,
       count(DISTINCT p) as patent_backed_transitions
  RETURN
      total_transitions,
      patent_backed_transitions,
      patent_backed_transitions * 100.0 / total_transitions as patent_backed_rate_pct
  ```

### Requirement: Bulk Loading Performance

The system SHALL optimize Neo4j write operations for bulk transition loading with transactional batching.

#### Scenario: Batch write transitions

- **WHEN** loading 173,897 transition detections
- **THEN** the system groups writes into batches of 1,000 transitions per transaction
- **AND** uses UNWIND + MERGE for efficient bulk inserts
- **AND** commits each batch before proceeding to next

#### Scenario: Create indexes before bulk load

- **WHEN** the loading pipeline starts
- **THEN** the system creates indexes on:
  - Transition.transition_id (unique)
  - Transition.confidence
  - Transition.likelihood_score
  - Contract.piid (unique)
  - TransitionProfile.company_id
- **AND** indexes are enabled during load for MERGE operations

#### Scenario: Log loading progress

- **WHEN** loading transitions in batches
- **THEN** the system logs progress every 10,000 records
- **AND** calculates throughput in records/second
- **AND** estimates time remaining based on current throughput
- **AND** reports final load time and success rate (target: ≥99%)

### Requirement: Incremental Transition Updates

The system SHALL support incremental loading of new transitions without duplicating existing data.

#### Scenario: Upsert existing transitions

- **WHEN** re-running detection with updated algorithm
- **AND** transition_id already exists in Neo4j
- **THEN** the system uses MERGE to update the Transition node
- **AND** updates likelihood_score if algorithm changed
- **AND** preserves original detection_date
- **AND** adds update_date timestamp

#### Scenario: Append new transitions

- **WHEN** loading new contract data (monthly updates)
- **AND** new transitions are detected
- **THEN** the system creates new Transition nodes
- **AND** links to existing Award and new Contract nodes
- **AND** updates company TransitionProfile metrics

#### Scenario: Handle deleted contracts

- **WHEN** a contract is removed from source data (data quality issue)
- **THEN** the system marks the Transition as invalid
- **AND** adds invalidation_reason property
- **AND** does not delete historical transition record (audit trail)

### Requirement: Data Quality Constraints

The system SHALL enforce data quality constraints on transition nodes and relationships.

#### Scenario: Validate transition properties

- **WHEN** creating Transition node
- **THEN** the system validates:
  - transition_id is UUID
  - likelihood_score is between 0.0 and 1.0
  - confidence is one of ["High", "Likely", "Possible"]
  - detection_date is valid datetime
  - detection_version is not null
- **AND** rejects nodes with invalid properties

#### Scenario: Validate evidence bundle structure

- **WHEN** storing evidence bundle on TRANSITIONED_TO relationship
- **THEN** the system validates JSON structure includes:
  - Required fields: sbir_award_id, contract_piid, likelihood_score
  - Signal fields: agency_signals, timing_signals
  - Metadata fields: detection_date, detection_version
- **AND** limits evidence bundle size to ≤5KB
- **AND** rejects malformed evidence bundles

#### Scenario: Validate relationship counts

- **WHEN** loading transitions for a fiscal year
- **THEN** the system validates:
  - Every Transition has exactly 1 TRANSITIONED_TO (from Award)
  - Every Transition has exactly 1 RESULTED_IN (to Contract)
  - Every Transition has 0-10 ENABLED_BY (to Patents)
  - Every Transition has 0-1 INVOLVES_TECHNOLOGY (to CETArea)
- **AND** logs warnings for anomalies
