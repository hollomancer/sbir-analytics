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

Organizations are keyed by the authoritative `organization_id` (e.g.
`org_company_<id>`); `uei` is a regular indexed property, so MERGE on it would
mint duplicates.

```cypher
UNWIND $batch AS row
MERGE (o:Organization {organization_id: row.organization_id})
SET o.organization_type = "COMPANY",
    o.uei = row.uei,
    o.name = row.name,
    o.address = row.address,
    o.city = row.city,
    o.state = row.state
```

### Node Types and Labels

- **Organization** (companies): SBIR award recipients with UEI/DUNS identifiers (`organization_type: "COMPANY"`), keyed by `organization_id`
- **FinancialTransaction**: SBIR/STTR awards (`transaction_type: "AWARD"`) with funding and phase information, keyed by `transaction_id`
- **Patent**: USPTO patents with grant numbers and metadata
- **PatentAssignment**: Patent ownership transfer events
- **Organization / Individual**: Patent assignees and assignors (unified entity labels)
- **CETArea**: Critical and Emerging Technology categories

## Relationship Creation Patterns

### Temporal Relationships

Store time-based metadata on relationships:

```cypher
(award:FinancialTransaction {transaction_type: "AWARD", transaction_date: date("2023-01-15")})-[:RECIPIENT_OF]->(org:Organization)
(patent:Patent)-[:ASSIGNED_VIA {record_date: date("2023-06-20")}]->(assignment:PatentAssignment)
```

### Confidence-Based Relationships

Include confidence scores and evidence:

```cypher
(award:FinancialTransaction {transaction_type: "AWARD"})-[:FUNDED {
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
CREATE CONSTRAINT IF NOT EXISTS FOR (o:Organization) REQUIRE o.organization_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (ft:FinancialTransaction) REQUIRE ft.transaction_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (p:Patent) REQUIRE p.grant_doc_num IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (pa:PatentAssignment) REQUIRE pa.rf_id IS UNIQUE;
```

### Performance Indexes

```cypher
CREATE INDEX organization_name IF NOT EXISTS FOR (o:Organization) ON (o.name);
CREATE INDEX financial_transaction_date IF NOT EXISTS FOR (ft:FinancialTransaction) ON (ft.transaction_date);
CREATE INDEX patent_title IF NOT EXISTS FOR (p:Patent) ON (p.title);
CREATE INDEX assignment_date IF NOT EXISTS FOR (pa:PatentAssignment) ON (pa.record_date);
```

### Full-Text Search Indexes

```cypher
CREATE FULLTEXT INDEX organization_name_fulltext IF NOT EXISTS FOR (o:Organization) ON EACH [o.name];
CREATE FULLTEXT INDEX patent_title_fulltext IF NOT EXISTS FOR (p:Patent) ON EACH [p.title];
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
(award:FinancialTransaction {transaction_type: "AWARD"})-[:APPLICABLE_TO {
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
(company:Organization)-[:SPECIALIZES_IN {
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
(assignment:PatentAssignment)-[:ASSIGNED_FROM {exec_date: date("1994-12-22")}]->(assignor:Organization)
(assignment:PatentAssignment)-[:ASSIGNED_TO {record_date: date("1999-07-29")}]->(assignee:Organization)

// Current Ownership
(company:Organization)-[:OWNS {as_of_date: date("1999-07-29")}]->(patent:Patent)
```

### Assignment Chain Queries

```cypher
// Find complete ownership chain for a patent
MATCH (p:Patent {grant_doc_num: "5858003"})

-[:ASSIGNED_VIA]->(a:PatentAssignment)
-[:ASSIGNED_FROM]->(originator:Organization)

,
(a)-[:ASSIGNED_TO]->(recipient:Organization)
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

- Create unique constraints first (Organization.organization_id, FinancialTransaction.transaction_id, Patent.grant_doc_num).
- Ensure indexes needed by MERGE patterns exist prior to loading.
- Use UNWIND batches sized to avoid transaction timeouts (e.g., 1k–5k).
- Enable deadlock retries, keep transactions short, and commit per batch.
- Order operations: constraints → indexes → bulk load → additional indexes if needed.
- Validate sample batches end-to-end before full-scale execution.
- Monitor for constraint violations; capture and report failed records.

## Data Quality Constraints

### Node Property Validation

```cypher
CREATE CONSTRAINT award_amount_positive ON (ft:FinancialTransaction) ASSERT ft.amount >= 0;
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
MATCH (a:FinancialTransaction {transaction_type: "AWARD"})-[r:APPLICABLE_TO {primary: true}]->(cet:CETArea)
WHERE a.transaction_date >= date("2020-01-01")
RETURN
  cet.name AS technology_area,
  count(a) AS award_count,
  sum(a.amount) AS total_funding,
  avg(r.score) AS avg_confidence
ORDER BY total_funding DESC
```

### Technology Transition Analysis

```cypher
// Awards that led to patents in same CET area
MATCH (a:FinancialTransaction {transaction_type: "AWARD"})-[:APPLICABLE_TO]->(award_cet:CETArea)
MATCH (a)-[:FUNDED]->(p:Patent)-[:APPLICABLE_TO]->(patent_cet:CETArea)
WHERE award_cet = patent_cet
RETURN
  award_cet.name AS technology_area,
  count(*) AS successful_transitions,
  avg(a.amount) AS avg_award_amount
ORDER BY successful_transitions DESC
```

### Company Specialization Analysis

```cypher
// Companies with highest specialization in AI
MATCH (c:Organization {organization_type: "COMPANY"})-[s:SPECIALIZES_IN]->(cet:CETArea {cet_id: "artificial_intelligence"})
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
MATCH (c:Organization {uei: $new_owner_uei})
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

- **[configuration.md](../configuration.md)** - Complete Neo4j configuration examples
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Loading performance optimization and memory management
- **[data-quality.md](data-quality.md)** - Data quality constraints and validation
- **[quick-reference.md](quick-reference.md)** - Neo4j patterns quick reference and common queries
