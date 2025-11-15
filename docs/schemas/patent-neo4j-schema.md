# Neo4j Graph Schema for USPTO Patent Assignments

## Overview

This document specifies the Neo4j graph model for USPTO patent assignments, including node types, relationship types, properties, indexes, and integration with existing SBIR ETL entities (Awards, Companies).

### Design Principles:

- **Immutability**: Patent data is historical and immutable (append-only)
- **Temporal Relationships**: Preserve assignment timeline (who → when → whom)
- **Referential Clarity**: Clear links between patents, assignments, entities, and SBIR context
- **Query Efficiency**: Indexes on common search paths (patent number, company, timeline)
- **Audit Trail**: Store assignment chain history for forensic analysis

---

## 1. Node Types

### 1.1 Patent Node

Represents a patented invention, identified by USPTO patent numbers.

```cypher
(:Patent {
  # Identifiers (choose one as primary key)
  grant_doc_num: string,           # "10123456" (PRIMARY - links to SBIR)
  appno_doc_num: string,           # "2016-123456"
  pgpub_doc_num: string,           # "10,123,456"

  # Patent Metadata
  title: string,                   # Full patent title
  lang: string,                    # "ENGLISH", language code

  # Filing & Grant Timeline
  appno_date: datetime,            # Application filing date (1790+)
  pgpub_date: datetime,            # Publication/grant date

  # Attribution
  num_inventors: integer,          # Number of patent assignors
  num_assignees: integer,          # Number of current/final assignees

  # Source & Lineage
  source_table: string,            # "documentid" (audit trail)
  loaded_date: datetime,           # When patent was loaded into graph
  extracted_from_rf_id: string,    # Foreign key to USPTO reel/frame

  # Optional SBIR Integration
  sbir_funded: boolean,            # true if funded by SBIR award
  sbir_award_phase: string,        # "Phase I" / "Phase II" / "Phase III"
})
```

### Constraints:

- `grant_doc_num` should be UNIQUE (when present, ~70% of records)
- `title` must be non-null
- `appno_date` should be between 1790 and current year

### Indexes:

```cypher
CREATE INDEX idx_patent_grant_doc_num
  FOR (p:Patent) ON (p.grant_doc_num);

CREATE INDEX idx_patent_appno_doc_num
  FOR (p:Patent) ON (p.appno_doc_num);

CREATE INDEX idx_patent_title
  FOR (p:Patent) ON (p.title);

CREATE INDEX idx_patent_appno_date
  FOR (p:Patent) ON (p.appno_date);

CREATE FULLTEXT INDEX idx_patent_title_fulltext
  ON (p:Patent)
  FOR (p.title);
```

---

### 1.2 PatentAssignment Node

Represents a single assignment/transfer transaction. Links Patent to its participants.

```cypher
(:PatentAssignment {
  # Primary Identifier
  rf_id: integer,                  # Reel/Frame ID (1-to-1 with assignment.dta)
  reel_no: integer,                # USPTO reel number
  frame_no: integer,               # Position within reel

  # Transaction Details
  convey_type: string,             # "ASSIGNMENT", "LICENSE", "SECURITY_INTEREST", ...
  employer_assign: boolean,        # true if employer-initiated

  # Correspondence Information
  correspondent_name: string,      # Law firm or handler
  correspondent_address: string,   # Address line 1
  correspondent_city: string,      # Parsed city
  correspondent_state: string,     # Parsed state

  # Timeline
  exec_date: datetime,             # When assignment was executed (from assignor.exec_dt)
  recorded_date: datetime,         # Inferred: when USPTO recorded (from rf_id)

  # Metadata
  num_patents: integer,            # Number of patents in this assignment
  num_assignees: integer,          # Number of recipients
  num_assignors: integer,          # Number of originators

  # Source & Lineage
  source_table: string,            # "assignment" (audit trail)
  loaded_date: datetime,           # When record loaded into graph

  # Classification
  assignment_chain_depth: integer, # How many assignments this patent has undergone
})
```

### Constraints:

- `rf_id` must be UNIQUE (primary key from USPTO)
- `convey_type` must be from enum: ASSIGNMENT, LICENSE, SECURITY_INTEREST, MERGER, CORRECTION, etc.
- `exec_date` should be between 1790 and current year

### Indexes:

```cypher
CREATE INDEX idx_assignment_rf_id
  FOR (a:PatentAssignment) ON (a.rf_id);

CREATE INDEX idx_assignment_exec_date
  FOR (a:PatentAssignment) ON (a.exec_date);

CREATE INDEX idx_assignment_convey_type
  FOR (a:PatentAssignment) ON (a.convey_type);
```

---

### 1.3 PatentEntity Node

Represents any party involved in patent assignments (assignees, assignors). Can be companies, individuals, or institutions.

```cypher
(:PatentEntity {
  # Identifiers
  entity_id: string,               # UUID or hash of (name + address)
  name: string,                    # Company/individual name
  normalized_name: string,         # Uppercase, special chars removed

  # Address Information
  address: string,                 # Full address
  city: string,
  state: string,
  postcode: string,
  country: string,

  # Entity Classification
  entity_type: string,             # "ASSIGNEE" or "ASSIGNOR"
  entity_category: string,         # "COMPANY", "INDIVIDUAL", "UNIVERSITY", "GOVERNMENT"

  # Metrics
  num_assignments_as_assignee: integer,   # Acquisition count
  num_assignments_as_assignor: integer,   # Origination count
  num_patents_owned: integer,             # Current portfolio

  # SBIR Integration
  is_sbir_company: boolean,        # true if matches SBIR Award recipient
  sbir_uei: string,                # SAM.gov UEI if available
  sbir_company_id: string,         # Foreign key to sbir_company in SBIR database

  # Source & Lineage
  source_tables: [string],         # ["assignee"] or ["assignor"] or both
  loaded_date: datetime,

  # Metadata
  first_seen_date: datetime,       # Earliest assignment as this entity
  last_seen_date: datetime,        # Most recent assignment
})
```

### Constraints:

- `name` must be non-null
- `entity_type` must be "ASSIGNEE" or "ASSIGNOR"
- `entity_category` must be one of: COMPANY, INDIVIDUAL, UNIVERSITY, GOVERNMENT, OTHER
- `entity_id` should be UNIQUE (composite key of normalized name + country + postcode)

### Indexes:

```cypher
CREATE INDEX idx_entity_name
  FOR (e:PatentEntity) ON (e.name);

CREATE INDEX idx_entity_normalized_name
  FOR (e:PatentEntity) ON (e.normalized_name);

CREATE INDEX idx_entity_type
  FOR (e:PatentEntity) ON (e.entity_type);

CREATE INDEX idx_entity_sbir_company
  FOR (e:PatentEntity) ON (e.is_sbir_company);

CREATE FULLTEXT INDEX idx_entity_name_fulltext
  ON (e:PatentEntity)
  FOR (e.name);
```

---

## 2. Relationship Types

### 2.1 ASSIGNED_VIA Relationship

Links a Patent to a PatentAssignment transaction.

```cypher
(patent:Patent)-[r:ASSIGNED_VIA]->(assignment:PatentAssignment {
  # Timeline
  exec_date: datetime,             # When patent was part of this assignment
  recorded_date: datetime,         # When USPTO recorded

  # Context
  position_in_batch: integer,      # If multiple patents in one assignment
  total_in_batch: integer,         # Total count in batch

  # Metadata
  source_rf_id: integer,           # Reference to assignment.rf_id
})
```

**Cardinality**: One Patent can have MULTIPLE ASSIGNED_VIA relationships (assignment chain)

### Usage Pattern

```cypher
// Find all assignments for a patent
MATCH (p:Patent {grant_doc_num: "10123456"})-[r:ASSIGNED_VIA]->(a:PatentAssignment)
ORDER BY r.exec_date ASC
RETURN p, r, a
```

---

### 2.2 ASSIGNED_TO Relationship

Links a PatentAssignment to the recipient PatentEntity (assignee).

```cypher
(assignment:PatentAssignment)-[r:ASSIGNED_TO]->(recipient:PatentEntity {
  # Timeline
  effective_date: datetime,        # When recipient acquired rights

  # Rights Details
  convey_type: string,             # Inherited from assignment.convey_type

  # Metadata
  assignment_role: string,         # "PRIMARY_ASSIGNEE", "CO_ASSIGNEE", etc.
  source_ee_name: string,          # Original assignee name (audit)
})
```

**Cardinality**: One PatentAssignment can have MULTIPLE ASSIGNED_TO relationships (co-assignees)

### Usage Pattern

```cypher
// Find who owns a patent after assignment
MATCH (a:PatentAssignment)-[r:ASSIGNED_TO]->(e:PatentEntity)
WHERE a.rf_id = 12345678
RETURN e.name, r.effective_date, a.convey_type
```

---

### 2.3 ASSIGNED_FROM Relationship

Links a PatentAssignment to the originator PatentEntity (assignor/inventor).

```cypher
(assignment:PatentAssignment)-[r:ASSIGNED_FROM]->(originator:PatentEntity {
  # Timeline
  exec_date: datetime,             # When originator signed

  # Role
  originator_role: string,         # "INVENTOR", "EMPLOYER", "PRIOR_OWNER", etc.

  # Metadata
  source_or_name: string,          # Original assignor name (audit)
})
```

**Cardinality**: One PatentAssignment can have MULTIPLE ASSIGNED_FROM relationships (multiple inventors)

### Usage Pattern

```cypher
// Find original inventors of a patent
MATCH (p:Patent {grant_doc_num: "10123456"})-[:ASSIGNED_VIA]->(a:PatentAssignment)

-[:ASSIGNED_FROM]->(inv:PatentEntity)

WHERE a.exec_date = (
  SELECT MIN(a2.exec_date) FROM PatentAssignment a2
)
RETURN inv.name, inv.entity_category
```

---

### 2.4 GENERATED_FROM Relationship

Links a Patent to an SBIR Award (integration with SBIR pipeline).

**Note**: Previously documented as `FUNDED_BY`, now consolidated to `GENERATED_FROM` for consistency.

```cypher
(patent:Patent)-[r:GENERATED_FROM]->(award:Award {
  # Award Context
  award_id: string,
  award_year: integer,
  phase: string,                   # "Phase I", "Phase II"

  # Linkage Confidence
  linkage_method: string,          # "exact_grant_num", "fuzzy_match", "manual"
  confidence_score: float,         # 0.0-1.0

  # Timeline
  linked_date: datetime,           # When link was created
})
```

**Cardinality**: One Patent can have ONE GENERATED_FROM relationship (one source award)

**Constraint**: Patent.grant_doc_num should match or fuzzy-match Award.patent_number

### Usage Pattern

```cypher
// Find all SBIR-funded patents for a company
MATCH (a:Award)<-[:GENERATED_FROM]-(p:Patent)
MATCH (a)-[:RECIPIENT_OF]->(c:Organization {organization_type: "COMPANY"})
RETURN p.title, p.appno_date, a.amount
```

---

### 2.5 OWNS Relationship

Direct relationship from Company to Patent (current ownership).

```cypher
(company:Company)-[r:OWNS]->(patent:Patent {
  # Ownership Context
  acquisition_date: datetime,      # When company acquired rights
  acquisition_method: string,      # "SBIR_FUNDED", "ASSIGNMENT", "MERGER", etc.

  # Rights Type
  ownership_type: string,          # "FULL", "PARTIAL", "LICENSED"

  # Metadata
  confidence: float,               # 0.0-1.0 based on entity resolution
  source_entity_id: string,        # PatentEntity that was matched
})
```

**Cardinality**: One Company can OWN multiple Patents

**Derivation**: Computed from PatentEntity.sbir_company_id + ASSIGNED_TO chain

### Usage Pattern

```cypher
// Find patent portfolio of SBIR company
MATCH (c:Company {sbir_uei: "ABC123"})-[r:OWNS]->(p:Patent)
RETURN p.title, p.grant_doc_num, r.acquisition_date
ORDER BY r.acquisition_date DESC
```

---

### 2.6 CHAIN_OF Relationship

Links consecutive PatentAssignments in an ownership chain.

```cypher
(earlier:PatentAssignment)-[r:CHAIN_OF]->(later:PatentAssignment {
  # Timeline
  time_between: integer,           # Days between assignments

  # Chain Context
  chain_position: integer,         # Position in chain (0 = original)

  # Parties
  common_party: string,            # Name of entity appearing in both
})
```

**Cardinality**: Links assignments in temporal order

### Usage Pattern

```cypher
// Trace full assignment chain for patent
MATCH path = (p:Patent)-[:ASSIGNED_VIA]->(a1:PatentAssignment)

-[:CHAIN_OF*]->(an:PatentAssignment)

RETURN path
```

---

## 3. Existing Entity Integration

### 3.1 Award Integration

Existing SBIR schema node `Award`:

```cypher
(award:Award {
  award_id: string,
  award_number: string,
  program: string,                 # "SBIR", "STTR"
  phase: string,                   # "I", "II", "III"
  fiscal_year: integer,
  amount: decimal,
  company_id: string,              # Foreign key
  agency: string,
  ...
})
```

### New Relationship

```cypher
(patent:Patent)-[r:GENERATED_FROM]->(award:Award)
```

**New Fields on Award** (optional, for performance):

```cypher
award.patent_number: string         # Direct reference if known
award.num_patents: integer          # Count of linked patents
```

---

### 3.2 Company Integration

Existing SBIR schema node `Company`:

```cypher
(company:Company {
  company_id: string,
  legal_name: string,
  uei: string,                      # SAM.gov UEI
  cage_code: string,
  duns_number: string,
  headquarters_city: string,
  headquarters_state: string,
  ...
})
```

### New Relationship

```cypher
(company:Company)-[r:OWNS]->(patent:Patent)
```

### Enhanced PatentEntity

```cypher
(:PatentEntity {
  sbir_company_id: string,          # Points to Company node
  sbir_uei: string,                 # Cached from Company.uei
})
```

---

## 4. Complete Data Model Diagram

```text
                    ┌─────────────────────────────┐
                    │        :Patent              │
                    ├─────────────────────────────┤
                    │ grant_doc_num (PK)          │
                    │ title                       │
                    │ appno_date                  │
                    │ sbir_funded                 │
                    └──────────┬────────────────┬─┘
                              /│\              │
                             / │ \             │
                   [ASSIGNED_VIA] │      [FUNDED_BY]
                           /      │            │
                          /       │            ▼
          ┌────────────────────────────┐   ┌──────────┐
          │  :PatientAssignment        │   │  :Award  │
          ├────────────────────────────┤   └──────────┘
          │ rf_id (PK)                 │
          │ convey_type                │
          │ exec_date                  │
          └────┬────────────────────┬──┘
               │                    │
        [ASSIGNED_FROM]      [ASSIGNED_TO]
               │                    │
               ▼                    ▼
    ┌──────────────────────────────────────┐
    │   :PatentEntity                      │
    ├──────────────────────────────────────┤
    │ entity_id (PK)                       │
    │ name                                 │
    │ entity_type (ASSIGNEE|ASSIGNOR)      │
    │ entity_category                      │
    │ sbir_company_id (FK to :Company)     │
    │ sbir_uei                             │
    └──────────────┬───────────────────────┘
                   │
            [OWNS] │ (derived from chain)
                   │
                   ▼
            ┌────────────────┐
            │   :Company     │
            │ (existing SBIR │
            │   node)        │
            └────────────────┘
```

---

## 5. Query Patterns

### 5.1 Patent Ownership Chain

Find complete chain of ownership for a patent:

```cypher
MATCH (p:Patent {grant_doc_num: "10123456"})

-[:ASSIGNED_VIA]->(a:PatentAssignment)
-[:ASSIGNED_FROM]->(originator:PatentEntity)

,
(a)-[:ASSIGNED_TO]->(recipient:PatentEntity)
RETURN
  a.exec_date AS exec_date,
  originator.name AS from,
  recipient.name AS to,
  a.convey_type AS transaction_type
ORDER BY a.exec_date ASC
```

---

### 5.2 SBIR Company Patent Portfolio

Find all patents owned by an SBIR-funded company:

```cypher
MATCH (c:Company {sbir_uei: "ABC123"})-[:OWNS]->(p:Patent)
OPTIONAL MATCH (p)-[:FUNDED_BY]->(award:Award)
RETURN
  p.grant_doc_num,
  p.title,
  award.phase,
  count(DISTINCT p) OVER () AS portfolio_size
ORDER BY p.appno_date DESC
```

---

### 5.3 Patent-to-Award Linkage

Find patents potentially linked to SBIR awards:

```cypher
MATCH (p:Patent)-[:GENERATED_FROM]->(a:Award)
WHERE a.phase IN ["II", "Phase II"]
  AND a.fiscal_year >= 2015
RETURN
  p.grant_doc_num,
  p.title,
  a.award_number,
  a.amount
ORDER BY a.fiscal_year DESC
```

---

### 5.4 Company Acquisitions (via Patents)

Detect M&A activity through patent assignment transfers:

```cypher
MATCH (a1:PatentAssignment)-[:ASSIGNED_FROM]->(original:PatentEntity)
,
(a1)-[:ASSIGNED_TO]->(intermediary:PatentEntity)

-[:OWNS]->(c1:Company)
-[:OWNS]->(p:Patent)
-[:ASSIGNED_VIA]->(a2:PatentAssignment)
-[:ASSIGNED_TO]->(acquirer:PatentEntity)
-[:OWNS]->(c2:Company)

WHERE a1.exec_date < a2.exec_date
  AND a1.convey_type = "ASSIGNMENT"
RETURN
  c1.legal_name AS from_company,
  c2.legal_name AS to_company,
  count(DISTINCT p) AS patents_transferred,
  min(a2.exec_date) AS first_transfer_date,
  max(a2.exec_date) AS last_transfer_date
GROUP BY c1, c2
HAVING count(DISTINCT p) > 5  # At least 5 patents to flag as acquisition
```

---

### 5.5 Technology Assignment Timeline

Show assignment activity over time:

```cypher
MATCH (a:PatentAssignment)
RETURN
  date(a.exec_date) AS assignment_date,
  a.convey_type,
  count(DISTINCT a) AS assignment_count,
  sum(a.num_patents) AS total_patents
ORDER BY assignment_date DESC
```

---

## 6. Data Loading Strategy

### Phase 1: Load Assignments & Patents

1. Load `assignment.dta` → Create `:PatentAssignment` nodes
2. Load `documentid.dta` → Create `:Patent` nodes
3. Create `ASSIGNED_VIA` relationships (Patent → Assignment)
4. Create indexes (rf_id, grant_doc_num)

### Phase 2: Load Entities

1. Load `assignee.dta` → Create `:PatentEntity` nodes (entity_type = "ASSIGNEE")
2. Load `assignor.dta` → Create `:PatentEntity` nodes (entity_type = "ASSIGNOR")
3. Deduplicate entities by normalized_name + address
4. Create indexes (entity_id, normalized_name)

### Phase 3: Link Transactions to Entities

1. Create `ASSIGNED_TO` relationships (Assignment → PatentEntity)
2. Create `ASSIGNED_FROM` relationships (Assignment → PatentEntity)
3. Populate PatentAssignment.num_assignees, num_assignors

### Phase 4: SBIR Integration

1. Match `PatentEntity` to `Company` nodes (fuzzy name matching + UEI)
2. Create `OWNS` relationships (Company → Patent)
3. Link `Patent` to `Award` via grant_doc_num matching
4. Create `GENERATED_FROM` relationships (Patent → Award)

### Phase 5: Compute Metrics

1. Calculate `PatentEntity.num_assignments_as_*`
2. Calculate `PatentEntity.num_patents_owned`
3. Calculate `Patent.num_inventors`, `num_assignees`
4. Calculate `PatentAssignment.assignment_chain_depth`

---

## 7. Performance Considerations

### Indexes (Priority Order)

**Tier 1 - Essential** (create first):
- Patent.grant_doc_num (SBIR linkage)
- PatentAssignment.rf_id (uniqueness)
- PatentEntity.normalized_name (matching)

**Tier 2 - High Value** (create second):
- Patent.appno_date (timeline queries)
- PatentAssignment.exec_date (temporal analysis)
- PatentEntity.entity_type (filtering)

**Tier 3 - Optional** (create if needed):
- Patent.title (FULLTEXT for search)
- PatentEntity.name (FULLTEXT for search)
- PatentAssignment.convey_type (filtering)

### Query Optimization Tips

1. **Use temporal indexes** for date range queries
2. **Limit OPTIONAL MATCH chains** (can be expensive)
3. **Batch writes** by assignment (1K per transaction)
4. **Partition by year** for large timeline queries

---

## 8. Schema Constraints & Validation

### Constraints to Enforce

```cypher

## Uniqueness Constraints

CREATE CONSTRAINT unique_patent_grant_doc_num
  ON (p:Patent) ASSERT p.grant_doc_num IS UNIQUE;

CREATE CONSTRAINT unique_assignment_rf_id
  ON (a:PatentAssignment) ASSERT a.rf_id IS UNIQUE;

CREATE CONSTRAINT unique_entity_id
  ON (e:PatentEntity) ASSERT e.entity_id IS UNIQUE;

## Node Property Constraints (Neo4j 5.0+)

CREATE CONSTRAINT patent_title_required
  ON (p:Patent) ASSERT p.title IS NOT NULL;

CREATE CONSTRAINT assignment_convey_type_required
  ON (a:PatentAssignment) ASSERT a.convey_type IS NOT NULL;

CREATE CONSTRAINT entity_name_required
  ON (e:PatentEntity) ASSERT e.name IS NOT NULL;
```

---

## 9. Version & Change History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-26 | Initial schema design with 5 node types, 6 relationship types |
| - | - | Integrated with existing SBIR Award/Company nodes |
| - | - | Defined query patterns for patent chains, company ownership |

---

## 10. References

- USPTO Patent Assignment Data: https://www.uspto.gov/learning-and-resources/fee-schedules/patent-assignment-data
- Neo4j Documentation: https://neo4j.com/docs/
- SBIR ETL Schema: See `docs/schemas/sbir-graph-schema.md`
