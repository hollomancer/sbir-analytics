## ADDED Requirements

### Requirement: Neo4j Award–Patent Similarity Relationships (PaECTER)
The system SHALL load semantic similarity edges derived from PaECTER between Award and Patent nodes into Neo4j as an optional, configuration-gated step.

#### Scenario: Ingest top‑k thresholded pairs
- WHEN the similarity artifact at data/processed/paecter_award_patent_similarity.parquet is available
- THEN the loader SHALL read pairs with threshold_pass = true
- AND it SHALL create relationships from (Award)-[:SIMILAR_TO]->(Patent) for the top‑k pairs per award (as produced upstream)
- AND the relationship properties SHALL include at minimum: score (float), method = "paecter", model (string), revision (string), computed_at (timestamp), rank (int), last_updated (timestamp)

#### Scenario: Direction and idempotent MERGE
- WHEN creating the relationship
- THEN the direction SHALL be Award → Patent
- AND the loader SHALL MERGE using the tuple (award_id, patent_id, method="paecter") to ensure idempotency on re‑runs
- AND on MERGE match, properties SHALL be updated with the latest score, rank, computed_at, model, revision, and last_updated

#### Scenario: Do not ingest raw embeddings
- WHEN writing to Neo4j
- THEN the loader SHALL NOT store or transmit raw embedding vectors
- AND only relationship metadata (e.g., score, method, model, revision, computed_at, rank, last_updated) SHALL be persisted

---

### Requirement: Preconditions, Constraints, and Indexes
The loader SHALL validate required constraints and indexes and fail with a clear, actionable error if prerequisites are missing (unless disabled by configuration).

#### Scenario: Node uniqueness constraints exist
- WHEN the loader initializes
- THEN it SHALL verify unique constraints on Award(award_id) and Patent(patent_id)
- AND on missing constraints, the loader SHALL exit with ERROR severity and message explaining remediation (or optionally auto‑create when paecter.neo4j.auto_create_constraints=true)

#### Scenario: Relationship uniqueness semantics
- WHEN upserting similarity edges
- THEN uniqueness semantics SHALL be enforced by MERGE pattern (Award(award_id))-[:SIMILAR_TO {method:"paecter"}]->(Patent(patent_id))
- AND no additional unique constraints on relationship properties SHALL be required

---

### Requirement: Pruning and Freshness
The system SHALL support pruning of stale edges and marking of current edges to maintain a coherent, current view.

#### Scenario: Prune previous edges for method="paecter" (optional)
- WHEN paecter.neo4j.prune_previous=true
- THEN after loading the current run’s edges, the loader SHALL remove relationships with method="paecter" for awards present in the current input that were not re‑emitted in this run
- AND pruning SHALL be scoped to the set of award_ids in the current artifact to avoid removing edges for awards not processed

#### Scenario: Mark current edges (without delete)
- WHEN paecter.neo4j.mark_current=true
- THEN the loader SHALL set relationship property current=true for edges from this run and current=false for method="paecter" edges superseded by the current run for the same award
- AND this behavior SHALL be mutually exclusive with delete‑based pruning when both are enabled; delete‑based pruning SHALL take precedence

---

### Requirement: Missing Nodes and Referential Integrity
The loader SHALL handle missing Award or Patent nodes deterministically and report the issue.

#### Scenario: Skip on missing endpoints
- WHEN either Award(award_id) or Patent(patent_id) is not found
- THEN the relationship SHALL be skipped
- AND the skip SHALL be counted and reported with sample IDs
- AND if skip_rate > configured threshold (default 0.01), the loader SHALL fail with ERROR severity

---

### Requirement: Batching, Throughput, and Reliability
The loader SHALL write relationships in batches with configurable transaction size and robust retry behavior.

#### Scenario: Transaction batching and concurrency
- WHEN loading edges
- THEN the loader SHALL use a configurable transaction batch size (default 5,000 relationships/transaction)
- AND it MAY use limited concurrency (default 1; configurable via paecter.neo4j.max_concurrency) as long as ordering guarantees per award are preserved
- AND the loader SHALL implement retry on transient Neo4j errors with exponential backoff and a configurable retry limit

#### Scenario: Dry‑run and preview
- WHEN paecter.neo4j.dry_run=true
- THEN the loader SHALL validate inputs, compute counts, and print planned operations (create, update, prune)
- AND no writes SHALL be performed

---

### Requirement: Configuration and Gating
The loading of similarity edges SHALL be disabled by default and only run when explicitly enabled.

#### Scenario: Opt‑in edge write
- WHEN paecter.enable_neo4j_edges=true
- THEN the loader asset SHALL execute
- AND when false or unset, the asset SHALL be skipped and a no‑op result SHALL be recorded in logs/metadata

#### Scenario: Threshold adherence
- WHEN reading the similarity artifact
- THEN the loader SHALL ingest only rows with threshold_pass=true
- AND it SHALL not re‑evaluate similarity thresholds during load

---

### Requirement: Observability and Metrics
The loader SHALL emit detailed metrics and attach them to asset metadata and reports.

#### Scenario: Metrics and checks
- WHEN the load completes
- THEN the loader SHALL emit counts: total_input_rows, ingested, updated, pruned_deleted, skipped_missing_node, distinct_awards, distinct_patents
- AND durations for read, batch_write, prune, and total SHALL be recorded
- AND a checks JSON SHALL be written under the loader’s output path including ok flag and any reasons for failure

---

### Requirement: Neo4j Schema Compatibility
The similarity edges SHALL align with the existing graph schema conventions.

#### Scenario: Node labels and keys
- WHEN writing edges
- THEN nodes SHALL use labels Award(award_id) and Patent(patent_id) consistent with the project’s schema
- AND relationship type SHALL be SIMILAR_TO with properties: score:float, method:string="paecter", model:string, revision:string, computed_at:datetime, rank:int, current:boolean (when mark_current enabled), last_updated:datetime