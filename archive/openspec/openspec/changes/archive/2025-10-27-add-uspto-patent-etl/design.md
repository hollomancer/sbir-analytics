# USPTO Patent Assignment ETL - Technical Design

## Context

The USPTO provides patent assignment data in Stata binary format (.dta files) containing ~8-10M ownership transfer records. This data must be integrated into the existing SBIR ETL pipeline to enable analysis of:

- Patent ownership chains and commercialization pathways
- SBIR company innovation and IP portfolio development
- Technology transfer and licensing activity
- M&A activity detection through patent ownership changes

**Constraints:**
- Large dataset (6.3GB compressed, ~20-30M records after joins)
- Complex relational structure (5 tables linked via rf_id)
- Memory limitations (avoid loading entire dataset into RAM)
- Must integrate with existing Neo4j graph schema
- Monthly incremental updates required

**Stakeholders:**
- SBIR program analysts tracking technology transition outcomes
- Researchers studying innovation commercialization patterns
- Policy makers evaluating SBIR program effectiveness

## Goals / Non-Goals

### Goals
- Extract all USPTO patent assignment tables with full fidelity
- Transform and join assignment data into graph-ready format
- Load patent ownership chains into Neo4j with temporal relationships
- Link patents to SBIR companies via document numbers
- Support incremental updates for monthly USPTO releases
- Maintain ≥95% data quality throughout pipeline

### Non-Goals
- Patent full-text analysis or claims parsing (out of scope)
- Patent citation network construction (future enhancement)
- Real-time USPTO API integration (batch processing only)
- Historical patent data backfill beyond provided dataset
- International patent data (USPTO only)

## Decisions

### Decision 1: Chunked Streaming vs. Full Load

**Choice:** Chunked streaming with 10K records per chunk

**Rationale:**
- documentid.dta is 1.5GB, assignee.dta is 851MB - too large for full in-memory load
- pandas.read_stata() supports iterator mode with configurable chunk size
- 10K records/chunk balances memory usage (~100MB/chunk) vs. I/O overhead
- Allows parallel processing of chunks via Dagster partitions (future optimization)

**Alternatives Considered:**
- Full in-memory load: Rejected - exceeds memory constraints for large files
- 1K records/chunk: Too many I/O operations, slower throughput
- 100K records/chunk: Higher memory usage, less granular progress tracking

**Implementation:**
```python
def extract_uspto_file(filepath: Path, chunk_size: int = 10000) -> Iterator[pd.DataFrame]:
    """Extract USPTO Stata file in chunks."""
    iterator = pd.read_stata(filepath, iterator=True, chunksize=chunk_size)
    for chunk in iterator:
        yield chunk
```

### Decision 2: Neo4j Graph Schema Design

**Choice:** Star schema with Patent as central node

**Graph Model:**
```
(Company)-[:FOUNDED_BY]->(Person)
(Company)-[:RECEIVED]->(Award)
(Award)-[:FUNDED]->(Patent)  # New relationship
(Patent)-[:ASSIGNED_VIA]->(PatentAssignment)-[:ASSIGNED_TO]->(PatentEntity)
(Patent)-[:ASSIGNED_VIA]->(PatentAssignment)-[:ASSIGNED_FROM]->(PatentEntity)
```

**Node Types:**
- **Patent**: grant_doc_num (PK), title, application_date, grant_date, language
- **PatentAssignment**: rf_id (PK), reel_no, frame_no, record_date, conveyance_type
- **PatentEntity**: name (PK), entity_type (assignee/assignor), address fields

**Relationship Types:**
- **FUNDED**: Award → Patent (identifies SBIR-funded inventions)
- **ASSIGNED_VIA**: Patent → PatentAssignment (links patent to assignment record)
- **ASSIGNED_TO**: PatentAssignment → PatentEntity (recipient of rights)
- **ASSIGNED_FROM**: PatentAssignment → PatentEntity (originator of rights)

**Rationale:**
- Separates Patent (immutable IP) from PatentAssignment (ownership transfer events)
- Supports multiple assignments per patent (ownership chain)
- PatentEntity allows same entity to be assignor in one transaction, assignee in another
- Temporal properties on relationships enable time-series analysis
- Integrates with existing Company and Award nodes

**Alternatives Considered:**
- Direct Patent → Company relationships: Loses assignment chain history
- Assignee/Assignor as separate node types: Duplicate entities across types
- Flat denormalized Patent node: Loses temporal ownership changes

### Decision 3: Company Linkage Strategy

**Choice:** Multi-stage matching with confidence scoring

**Matching Stages:**
1. **Exact grant_doc_num match**: Link via USPTO patent number in SBIR records (confidence: 0.95)
2. **Company name + patent fuzzy match**: Link via company name similarity + patent number proximity (confidence: 0.70-0.85)
3. **Address-based matching**: Link via company address overlap with assignee address (confidence: 0.60-0.75)

**Rationale:**
- SBIR records sometimes include patent numbers in free-text fields
- Many SBIR companies have patents but inconsistent naming
- Address-based matching catches cases where company name changed
- Confidence scores enable filtering for high-quality links

**Alternatives Considered:**
- Exact match only: Misses 40-50% of linkable patents
- No confidence scoring: Can't filter low-quality matches
- Manual review of all matches: Not scalable for 8-10M records

**Implementation:**
```python
def link_patent_to_company(patent: Patent, companies: List[Company]) -> Optional[CompanyLink]:
    # Stage 1: Exact patent number match
    if patent.grant_doc_num in [a.patent_numbers for c in companies for a in c.awards]:
        return CompanyLink(company, confidence=0.95, method="exact_patent_num")

    # Stage 2: Fuzzy name + patent proximity
    matches = fuzzy_match_company_name(patent.assignee_name, companies, threshold=0.80)
    if matches and patent_number_proximity(patent, matches[0]) < 3:
        return CompanyLink(matches[0], confidence=0.80, method="fuzzy_name")

    # Stage 3: Address-based
    # ... implementation
```

### Decision 4: Incremental Update Strategy

**Choice:** Upsert-based incremental updates with change detection

**Strategy:**
- Extract only new assignments since last run (filter by record_dt)
- Upsert Patent nodes (MERGE on grant_doc_num)
- Append PatentAssignment nodes (new assignments only)
- Update Company ownership relationships (detect ownership changes)

**Rationale:**
- USPTO releases monthly updates (~100K new assignments)
- Full reload wastes 2-4 hours processing unchanged data
- MERGE operations handle both inserts and updates efficiently
- Change detection identifies ownership transfers for downstream analytics

**Alternatives Considered:**
- Full reload monthly: Too slow, unnecessary reprocessing
- Append-only without upsert: Creates duplicate Patent nodes
- Delta detection via timestamps: USPTO doesn't provide reliable change timestamps

**Implementation:**
```python
# Dagster asset with incremental materialization
@asset(partitions_def=monthly_partitions)
def incremental_uspto_assignments(context: AssetExecutionContext) -> pd.DataFrame:
    last_run_date = get_last_run_date(context)
    new_assignments = extract_assignments_since(last_run_date)
    return new_assignments
```

## Risks / Trade-offs

### Risk 1: Memory Exhaustion with Large Files
**Mitigation:**
- Use chunked streaming (10K records/chunk)
- Monitor memory usage with Dagster sensors
- Implement backpressure if memory exceeds threshold (pause extraction)

### Risk 2: Entity Name Ambiguity
**Impact:** Same company name appears with variations ("IBM", "IBM CORP", "INTERNATIONAL BUSINESS MACHINES")

**Mitigation:**
- Implement fuzzy name matching with configurable threshold (≥0.80 similarity)
- Store original names for audit trail
- Add manual review queue for low-confidence matches (<0.70)

### Risk 3: Neo4j Write Performance
**Impact:** Loading 8-10M patent assignments may take 3-5 hours

**Mitigation:**
- Batch write operations (1K nodes/transaction)
- Use UNWIND + MERGE for bulk inserts
- Create indexes before bulk load, disable during load, rebuild after
- Parallelize writes across multiple Dagster workers (future optimization)

**Trade-off:** Loading speed vs. transactional consistency. Batching improves throughput but limits rollback granularity.

### Risk 4: Incomplete Company Linkage
**Impact:** Only 50-70% of SBIR companies may link to patents

**Mitigation:**
- Set realistic expectations: Not all SBIR awards result in patents
- Provide confidence scores for filtering
- Add manual linkage interface for high-value companies
- Track linkage coverage metrics over time

## Migration Plan

### Phase 1: Development & Validation (Week 1-2)
1. Implement extractors, transformers, loaders with test fixtures
2. Run on 10K record sample to validate pipeline
3. Review data quality reports and adjust thresholds
4. Test Neo4j graph queries for patent ownership chains

### Phase 2: Staging Deployment (Week 3)
1. Load full USPTO dataset to staging Neo4j instance
2. Validate data quality metrics (completeness, referential integrity)
3. Benchmark loading performance (target: <4 hours)
4. Test incremental update with sample monthly release

### Phase 3: Production Deployment (Week 4)
1. Load full dataset to production Neo4j
2. Set up monthly incremental update schedule (via Dagster sensor)
3. Monitor data quality metrics and alert on regressions
4. Document graph schema and example queries

### Rollback Plan
- Keep raw Stata files as source of truth
- Version Dagster assets for reproducibility
- Neo4j backups before bulk loads
- Rollback via asset version revert + Neo4j restore

## Open Questions

1. **Q: Should we store raw conveyance text or only parsed structured fields?**
   - **A:** Store both - raw for audit, parsed for queries. Adds ~20% storage but enables verification.

2. **Q: How to handle assignments with multiple patents (documentid has multiple rows per rf_id)?**
   - **A:** Create separate Patent nodes, link each to same PatentAssignment node. Represents batch assignments.

3. **Q: Should we deduplicate PatentEntity nodes across assignments?**
   - **A:** Yes, MERGE on normalized name + address hash. Enables entity-centric queries.

4. **Q: What's the expected patent linkage rate for SBIR companies?**
   - **A:** Estimate 50-70% based on prior research. Phase I: ~30%, Phase II: ~60%, Phase III: ~80%.

5. **Q: Should we backfill historical monthly data or only process latest snapshot?**
   - **A:** Start with latest full snapshot. Add monthly incremental updates going forward. Historical backfill is future work.
