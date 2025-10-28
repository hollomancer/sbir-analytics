# Data Loading - CET Classification Delta

## ADDED Requirements

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
