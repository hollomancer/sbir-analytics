# Neo4j Graph Database Patterns

## Graph Data Loading Patterns

The system implements comprehensive Neo4j loading patterns for SBIR, patent, and CET data with proper relationship modeling and performance optimization.

## Node Creation Patterns

### Upsert Semantics

- Use MERGE for idempotent node creation
- Support insert or update operations
- Handle duplicate prevention with unique constraints
- Maintain data consistency across multiple loads

### Batch Node Creation

```cypher
UNWIND $batch AS row
MERGE (c:Company {uei: row.uei})
SET c.name = row.name,
    c.address = row.address,
    c.city = row.city,
    c.state = row.state
```

### Node Types and Labels

- **Company**: SBIR award recipients with UEI/DUNS identifiers
- **Award**: SBIR/STTR awards with funding and phase information
- **Patent**: USPTO patents with grant numbers and metadata
- **PatentAssignment**: Patent ownership transfer events
- **PatentEntity**: Patent assignees and assignors
- **CETArea**: Critical and Emerging Technology categories

## Relationship Creation Patterns

### Temporal Relationships

Store time-based metadata on relationships:

```cypher
(award:Award)-[:AWARDED_TO {award_date: date("2023-01-15")}]->(company:Company)
(patent:Patent)-[:ASSIGNED_VIA {record_date: date("2023-06-20")}]->(assignment:PatentAssignment)
```

### Confidence-Based Relationships

Include confidence scores and evidence:

```cypher
(award:Award)-[:FUNDED {
  confidence: 0.95,
  method: "exact_patent_num",
  evidence: ["Patent number match", "Company name match"]
}]->(patent:Patent)
```

### Hierarchical Relationships

Support parent-child structures:

```cypher
(subcategory:CETArea)-[:SUBCATEGORY_OF]->(parent:CETArea)
```

## Index and Constraint Management

### Unique Constraints

```cypher
CREATE CONSTRAINT unique_company_uei ON (c:Company) ASSERT c.uei IS UNIQUE;
CREATE CONSTRAINT unique_award_id ON (a:Award) ASSERT a.award_id IS UNIQUE;
CREATE CONSTRAINT unique_patent_grant_num ON (p:Patent) ASSERT p.grant_doc_num IS UNIQUE;
CREATE CONSTRAINT unique_assignment_rf_id ON (pa:PatentAssignment) ASSERT pa.rf_id IS UNIQUE;
```

### Performance Indexes

```cypher
CREATE INDEX idx_company_name ON (c:Company) ON (c.name);
CREATE INDEX idx_award_date ON (a:Award) ON (a.award_date);
CREATE INDEX idx_patent_title ON (p:Patent) ON (p.title);
CREATE INDEX idx_assignment_date ON (pa:PatentAssignment) ON (pa.record_date);
```

### Full-Text Search Indexes

```cypher
CREATE FULLTEXT INDEX idx_company_name_fulltext ON (c:Company) FOR (c.name);
CREATE FULLTEXT INDEX idx_patent_title_fulltext ON (p:Patent) FOR (p.title);
```

## Transaction Management

### Batch Processing

- Process data in configurable batches (default: 1,000 records)
- Commit transactions per batch for memory management
- Handle transaction failures with rollback and retry

### Transaction Size Optimization

```python
def load_nodes_in_batches(data, batch_size=1000):
    for i in range(0, len(data), batch_size):
        batch = data[i:i + batch_size]
        with driver.session() as session:
            session.write_transaction(create_nodes_batch, batch)
```

### Error Handling

- Rollback transactions on constraint violations
- Log detailed error information
- Continue processing with remaining batches
- Report failed records for manual review

## CET Classification Integration

### Award-CET Relationships

```cypher
(award:Award)-[:APPLICABLE_TO {
  score: 85,
  classification: "High",
  primary: true,
  evidence: [{
    excerpt: "Advanced neural network algorithms",
    source: "abstract",
    rationale: "Contains AI keywords"
  }],
  classified_at: datetime("2025-10-26T12:00:00Z"),
  taxonomy_version: "NSTC-2025Q1"
}]->(cet:CETArea {cet_id: "artificial_intelligence"})
```

### Company Specialization

```cypher
(company:Company)-[:SPECIALIZES_IN {
  award_count: 5,
  total_funding: 2500000,
  avg_score: 78,
  dominant_phase: "II",
  first_award_date: date("2018-03-15"),
  last_award_date: date("2024-09-20"),
  specialization_score: 0.625
}]->(cet:CETArea)
```

## Patent Assignment Chain Modeling

### Assignment Relationships

```cypher
// Patent to Assignment
(patent:Patent)-[:ASSIGNED_VIA]->(assignment:PatentAssignment)

// Assignment to Entities
(assignment:PatentAssignment)-[:ASSIGNED_FROM {exec_date: date("1994-12-22")}]->(assignor:PatentEntity)
(assignment:PatentAssignment)-[:ASSIGNED_TO {record_date: date("1999-07-29")}]->(assignee:PatentEntity)

// Current Ownership
(company:Company)-[:OWNS {as_of_date: date("1999-07-29")}]->(patent:Patent)
```

### Assignment Chain Queries

```cypher
// Find complete ownership chain for a patent
MATCH (p:Patent {grant_doc_num: "5858003"})

-[:ASSIGNED_VIA]->(a:PatentAssignment)
-[:ASSIGNED_FROM]->(originator:PatentEntity)

,
(a)-[:ASSIGNED_TO]->(recipient:PatentEntity)
RETURN
  a.record_date AS assignment_date,
  originator.name AS from_entity,
  recipient.name AS to_entity,
  a.conveyance_type AS transaction_type
ORDER BY a.record_date ASC
```

## Performance Optimization

### Bulk Loading Strategies

- Use UNWIND for batch operations
- Create indexes before bulk loading
- Use MERGE for upsert operations
- Optimize query patterns for large datasets

### Query Optimization

- Use EXPLAIN and PROFILE for query analysis
- Optimize relationship traversals
- Use appropriate indexes for query patterns
- Limit result sets with pagination

Performance configuration and memory management details are covered in **[pipeline-orchestration.md](pipeline-orchestration.md)**.

## Safety Checklist (Before Large Loads)

- Create unique constraints first (Company.uei, Award.award_id, Patent.grant_doc_num).
- Ensure indexes needed by MERGE patterns exist prior to loading.
- Use UNWIND batches sized to avoid transaction timeouts (e.g., 1k–5k).
- Enable deadlock retries, keep transactions short, and commit per batch.
- Order operations: constraints → indexes → bulk load → additional indexes if needed.
- Validate sample batches end-to-end before full-scale execution.
- Monitor for constraint violations; capture and report failed records.

## Data Quality Constraints

### Node Property Validation

```cypher
CREATE CONSTRAINT award_amount_positive ON (a:Award) ASSERT a.award_amount >= 0;
CREATE CONSTRAINT patent_title_required ON (p:Patent) ASSERT p.title IS NOT NULL;
```

### Relationship Property Validation

- Confidence scores between 0.0 and 1.0
- Classification values from predefined set
- Date values within valid ranges
- Required properties not null

## Common Query Patterns

### Portfolio Analysis

```cypher
// Total funding by CET area
MATCH (a:Award)-[r:APPLICABLE_TO {primary: true}]->(cet:CETArea)
WHERE a.award_date >= date("2020-01-01")
RETURN
  cet.name AS technology_area,
  count(a) AS award_count,
  sum(a.award_amount) AS total_funding,
  avg(r.score) AS avg_confidence
ORDER BY total_funding DESC
```

### Technology Transition Analysis

```cypher
// Awards that led to patents in same CET area
MATCH (a:Award)-[:APPLICABLE_TO]->(award_cet:CETArea)
MATCH (a)-[:FUNDED]->(p:Patent)-[:APPLICABLE_TO]->(patent_cet:CETArea)
WHERE award_cet = patent_cet
RETURN
  award_cet.name AS technology_area,
  count(*) AS successful_transitions,
  avg(a.award_amount) AS avg_award_amount
ORDER BY successful_transitions DESC
```

### Company Specialization Analysis

```cypher
// Companies with highest specialization in AI
MATCH (c:Company)-[s:SPECIALIZES_IN]->(cet:CETArea {cet_id: "artificial_intelligence"})
WHERE s.award_count >= 3
RETURN
  c.name,
  s.award_count,
  s.total_funding,
  s.specialization_score
ORDER BY s.specialization_score DESC
LIMIT 20
```

## Incremental Update Patterns

### Upsert Existing Data

```cypher
// Update existing patents with new information
MERGE (p:Patent {grant_doc_num: $grant_doc_num})
SET p.title = $title,
    p.grant_date = $grant_date,
    p.updated_at = datetime()
```

### Append New Relationships

```cypher
// Add new patent assignments
MATCH (p:Patent {grant_doc_num: $grant_doc_num})
MERGE (pa:PatentAssignment {rf_id: $rf_id})
MERGE (p)-[:ASSIGNED_VIA]->(pa)
```

### Update Current Ownership

```cypher
// Update current patent ownership
MATCH (p:Patent {grant_doc_num: $grant_doc_num})
OPTIONAL MATCH (p)<-[old:OWNS]-()
DELETE old
WITH p
MATCH (c:Company {uei: $new_owner_uei})
CREATE (c)-[:OWNS {as_of_date: $assignment_date}]->(p)
```

## Monitoring and Maintenance

### Database Statistics

- Monitor node and relationship counts
- Track index usage and performance
- Monitor query execution times
- Alert on constraint violations

### Data Integrity Checks

- Validate relationship consistency
- Check for orphaned nodes
- Verify constraint compliance
- Monitor data quality metrics

### Performance Monitoring

- Query performance analysis
- Index effectiveness monitoring
- Memory usage tracking
- Transaction throughput measurement

## Related Documents

- **[configuration-patterns.md](configuration-patterns.md)** - Complete Neo4j configuration examples
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Loading performance optimization and memory management
- **[data-quality.md](data-quality.md)** - Data quality constraints and validation
- **[quick-reference.md](quick-reference.md)** - Neo4j patterns quick reference and common queries